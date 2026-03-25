# ========================
# FILE: src/model_ln.py
# LN QUINIELA V3 + MID -> NOCHE
# ========================

from dataclasses import dataclass
from typing import List, Tuple, Dict, Optional
from collections import defaultdict, Counter
import math


@dataclass
class ModelOutput:
    top3: List[str]
    top12: List[str]
    best_signal: float
    best_a11: int
    ok_alert: bool
    debug: Dict


# =========================================================
# Helpers
# =========================================================

def _z2(x: str) -> str:
    s = str(x).strip()
    digits = "".join(ch for ch in s if ch.isdigit())
    return digits.zfill(2) if digits else "00"


def _all_numbers() -> List[str]:
    return [f"{i:02d}" for i in range(100)]


def _decade(num: str) -> int:
    return int(num) // 10


def _adaptive_window(draws: List[Tuple[str, str, str]], requested_window: Optional[int] = None) -> int:
    """
    Ventana adaptativa:
    - Usa la diversidad reciente para decidir entre memoria corta/media.
    - Si runner manda window_n, se usa como techo.
    """
    n = len(draws)
    if n <= 60:
        return n

    recent = draws[-40:]
    flat_recent = [_z2(x) for triple in recent for x in triple]
    unique_recent = len(set(flat_recent))

    if unique_recent <= 55:
        base = 200
    elif unique_recent <= 70:
        base = 170
    else:
        base = 140

    if requested_window is not None:
        base = min(base, requested_window)

    return min(n, base)


def _weighted_frequency(data: List[Tuple[str, str, str]], decay: float = 0.985) -> Dict[str, float]:
    """
    Frecuencia ponderada: lo reciente pesa más.
    """
    scores = defaultdict(float)
    window = len(data)

    for i, triple in enumerate(data):
        weight = decay ** (window - 1 - i)
        for num in triple:
            scores[_z2(num)] += weight

    return scores


def _recent_counts(data: List[Tuple[str, str, str]], last_n: int) -> Counter:
    c = Counter()
    for triple in data[-last_n:]:
        for num in triple:
            c[_z2(num)] += 1
    return c


def _last_seen_gap(data: List[Tuple[str, str, str]]) -> Dict[str, int]:
    """
    Cuántos sorteos han pasado desde la última aparición.
    """
    gaps = {n: len(data) for n in _all_numbers()}

    for idx in range(len(data) - 1, -1, -1):
        triple = data[idx]
        for num in triple:
            num = _z2(num)
            if gaps[num] == len(data):
                gaps[num] = len(data) - 1 - idx

    return gaps


def _decade_pressure(data: List[Tuple[str, str, str]], last_n: int = 25) -> Dict[int, int]:
    dcount = defaultdict(int)
    for triple in data[-last_n:]:
        for num in triple:
            dcount[_decade(_z2(num))] += 1
    return dcount


def _conditional_mid_bonus(num: str, mid_today: Optional[Tuple[str, str, str]]) -> float:
    """
    Dependencia MID -> NOCHE:
    - cercanía numérica
    - misma terminación
    - misma decena
    - espejo simple (+50)
    """
    if not mid_today:
        return 0.0

    bonus = 0.0
    n = int(_z2(num))

    for m in mid_today:
        m_int = int(_z2(m))

        # cercanía directa
        if abs(n - m_int) <= 2:
            bonus += 0.20

        # misma terminación
        if n % 10 == m_int % 10:
            bonus += 0.15

        # misma decena
        if n // 10 == m_int // 10:
            bonus += 0.10

        # espejo simple
        if n == (m_int + 50) % 100:
            bonus += 0.08

    return bonus


# =========================================================
# Main model
# =========================================================

def rank_numbers_from_draws(
    draws: List[Tuple[str, str, str]],
    window_n: Optional[int] = None,
    mid_today: Optional[Tuple[str, str, str]] = None
) -> ModelOutput:
    """
    draws: lista [(n1,n2,n3), ...]
    window_n: compatibilidad con runner
    mid_today: se usa solo para Noche cuando runner lo pasa
    """

    if not draws or len(draws) < 50:
        raise ValueError("Historial insuficiente para modelo LN.")

    draws = [(_z2(a), _z2(b), _z2(c)) for a, b, c in draws]

    # ventana adaptativa
    window_used = _adaptive_window(draws, requested_window=window_n)
    data = draws[-window_used:]

    # componentes
    wf = _weighted_frequency(data, decay=0.985)
    mom12 = _recent_counts(data, last_n=12)
    mom20 = _recent_counts(data, last_n=20)
    recent8 = _recent_counts(data, last_n=8)
    recent3 = _recent_counts(data, last_n=3)
    gaps = _last_seen_gap(data)
    decade_counts = _decade_pressure(data, last_n=25)

    decade_avg = sum(decade_counts.values()) / max(1, len(decade_counts)) if decade_counts else 0.0
    avg_gap = sum(gaps.values()) / len(gaps)

    scores: Dict[str, float] = {}

    for num in _all_numbers():
        weighted_freq = wf.get(num, 0.0)
        short_momentum = mom12.get(num, 0) * 0.22 + mom20.get(num, 0) * 0.10

        gap = gaps.get(num, window_used)
        gap_boost = math.log1p(gap) * 0.18
        if gap > avg_gap:
            gap_boost *= 1.10

        overheat_penalty = 0.0
        if recent8.get(num, 0) >= 3:
            overheat_penalty += 0.55
        elif recent8.get(num, 0) == 2:
            overheat_penalty += 0.25

        if recent3.get(num, 0) >= 1:
            overheat_penalty += 0.18

        d = _decade(num)
        dec_count = decade_counts.get(d, 0)
        decade_boost = 0.0
        if dec_count < decade_avg:
            decade_boost = 0.10

        # ✅ MID -> NOCHE activo
        cond_bonus = _conditional_mid_bonus(num, mid_today)

        final_score = (
            0.40 * weighted_freq +
            0.20 * short_momentum +
            0.15 * gap_boost +
            0.05 * decade_boost +
            0.20 * cond_bonus
            - 0.20 * overheat_penalty
        )

        scores[num] = final_score

    ranked = sorted(scores.items(), key=lambda x: x[1], reverse=True)
    top12 = [n for n, _ in ranked[:12]]

    # =====================================================
    # Re-ranking Top3
    # =====================================================
    top3_candidates = top12[:8]
    last_draw = set(data[-1])

    top3_scores = {}
    for num in top3_candidates:
        base = scores[num]

        novelty = 0.18 if num not in last_draw else -0.12
        gap_short = min(gaps.get(num, window_used), 12) / 12.0
        heat = recent8.get(num, 0)
        heat_penalty = 0.18 * max(0, heat - 1)

        same_decade_in_top12 = sum(1 for x in top12 if _decade(x) == _decade(num))
        decade_diversity = -0.06 * max(0, same_decade_in_top12 - 2)

        # pequeño extra por condicional MID en Top3
        cond_top3 = _conditional_mid_bonus(num, mid_today) * 0.30

        top3_scores[num] = base + novelty + 0.22 * gap_short - heat_penalty + decade_diversity + cond_top3

    top3_ranked = sorted(top3_scores.items(), key=lambda x: x[1], reverse=True)
    raw_top3 = [n for n, _ in top3_ranked[:3]]

    # anti repetir exacto el último sorteo
    if set(raw_top3) == last_draw and len(top12) > 3:
        replacement = next((x for x in top12 if x not in raw_top3), top12[3])
        raw_top3 = raw_top3[:2] + [replacement]

    # evitar 3 números de misma decena si hay alternativa
    decades_top3 = [_decade(x) for x in raw_top3]
    if len(set(decades_top3)) == 1:
        replacement = next((x for x in top12[3:] if _decade(x) != decades_top3[0]), None)
        if replacement:
            raw_top3 = raw_top3[:2] + [replacement]

    top3 = raw_top3

    best_signal = float(ranked[0][1])
    best_a11 = sum(1 for n in top12[:6] if gaps.get(n, window_used) >= 6)

    top5_avg = sum(v for _, v in ranked[:5]) / 5.0
    top12_avg = sum(v for _, v in ranked[:12]) / 12.0
    separation = top5_avg - top12_avg

    # alerta calibrada
    ok_alert = separation > 0.08

    avg_recent_heat = sum(recent8.values()) / max(1, len(recent8))
    if avg_recent_heat >= 1.7:
        regime = "MOMENTUM"
    elif avg_gap >= window_used * 0.45:
        regime = "MEAN_REVERSION"
    elif mid_today:
        regime = "CONDITIONAL_EDGE"
    else:
        regime = "MIXED"

    debug = {
        "window_used": window_used,
        "regime": regime,
        "unique_numbers": len([n for n, v in scores.items() if v > 0]),
        "top5_avg": round(top5_avg, 6),
        "top12_avg": round(top12_avg, 6),
        "separation": round(separation, 6),
        "mid_today": ",".join(mid_today) if mid_today else "",
    }

    return ModelOutput(
        top3=top3,
        top12=top12,
        best_signal=round(best_signal, 6),
        best_a11=best_a11,
        ok_alert=ok_alert,
        debug=debug,
    )
