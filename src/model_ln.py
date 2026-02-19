from collections import defaultdict
from dataclasses import dataclass
from typing import Dict, List, Tuple
import math

@dataclass
class ModelOutput:
    top3: List[str]
    top12: List[str]
    debug: Dict
    best_signal: float
    best_a11: int
    ok_alert: bool

def _z2(x: str) -> str:
    s = str(x).strip()
    digits = "".join(ch for ch in s if ch.isdigit())
    return digits.zfill(2) if digits else ""

def _exp_weights(n: int, half_life: float = 30.0) -> List[float]:
    lam = math.log(2) / half_life
    ws = [math.exp(lam * i) for i in range(n)]
    s = sum(ws)
    return [w / s for w in ws]

def rank_numbers_from_draws(draws: List[Tuple[str, str, str]], window_n: int = 120) -> ModelOutput:
    """
    draws: lista (n1,n2,n3) en orden cronológico (antiguo -> reciente)
    retorna ModelOutput (nunca None)
    """
    if len(draws) < 50:
        raise ValueError(f"Historial insuficiente para rankear: {len(draws)} filas (mínimo 50).")

    last = draws[-window_n:] if len(draws) >= window_n else draws[:]
    n = len(last)

    weights = _exp_weights(n, half_life=30.0)

    freq = defaultdict(float)
    last_seen = {f"{i:02d}": None for i in range(100)}

    for idx, (a, b, c) in enumerate(last):
        a, b, c = _z2(a), _z2(b), _z2(c)
        for x in (a, b, c):
            freq[x] += weights[idx]
            last_seen[x] = idx

    short = last[-20:] if n >= 20 else last
    short_count = defaultdict(int)
    for a, b, c in short:
        for x in (_z2(a), _z2(b), _z2(c)):
            short_count[x] += 1

    def atraso(x: str) -> int:
        if last_seen[x] is None:
            return n
        return (n - 1) - last_seen[x]

    def atraso_bonus(x: str) -> float:
        d = atraso(x)
        lam = 0.12
        return 1.0 - math.exp(-lam * d)

    scores: Dict[str, float] = {}
    denom_short = max(1, len(short) * 3)

    for i in range(100):
        x = f"{i:02d}"
        s = (
            0.60 * freq.get(x, 0.0) +
            0.25 * atraso_bonus(x) +
            0.15 * (short_count.get(x, 0) / denom_short)
        )
        scores[x] = s

    ranked = sorted(scores.keys(), key=lambda k: scores[k], reverse=True)
    top12 = ranked[:12]
    top3 = ranked[:3]

    best_signal = float(scores[top12[0]])
    best_a11 = sum(1 for x in top12 if atraso(x) >= 11)

    ok_alert = best_signal >= 0.020  # ajustable

    debug = {
        "window_used": n,
        "top_score": best_signal,
        "top12_bottom_score": float(scores[top12[-1]]),
        "best_a11": best_a11,
    }

    return ModelOutput(
        top3=top3,
        top12=top12,
        debug=debug,
        best_signal=best_signal,
        best_a11=best_a11,
        ok_alert=ok_alert,
    )
