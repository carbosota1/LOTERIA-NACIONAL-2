# ========================
# FILE: src/model_ln.py
# LN QUINIELA V2
# ========================

from dataclasses import dataclass
from typing import List, Tuple, Dict
import math
from collections import defaultdict


@dataclass
class ModelOutput:
    top3: List[str]
    top12: List[str]
    best_signal: float
    best_a11: int
    ok_alert: bool
    debug: Dict


# =========================
# CORE MODEL
# =========================

def rank_numbers_from_draws(draws: List[Tuple[str, str, str]]) -> ModelOutput:
    """
    draws: lista [(n1,n2,n3), ...]
    Compatible con tu runner actual.
    """

    if not draws or len(draws) < 50:
        raise ValueError("Historial insuficiente para modelo LN.")

    # ---------
    # WINDOW DINÁMICO
    # ---------
    MAX_WINDOW = 200
    window = min(len(draws), MAX_WINDOW)
    data = draws[-window:]

    # ---------
    # CONFIG
    # ---------
    DECAY = 0.985          # peso exponencial
    MOMENTUM_WINDOW = 20   # últimos 20 sorteos
    OVERHEAT_THRESHOLD = 3 # repetido demasiadas veces reciente

    weighted_freq = defaultdict(float)
    short_freq = defaultdict(int)
    last_seen_index = {}

    # ---------
    # SCAN HISTORIAL
    # ---------
    for i, triple in enumerate(data):
        decay_weight = DECAY ** (window - i)

        for num in triple:
            weighted_freq[num] += decay_weight
            last_seen_index[num] = i

    # momentum corto
    for triple in data[-MOMENTUM_WINDOW:]:
        for num in triple:
            short_freq[num] += 1

    # ---------
    # SCORE FINAL
    # ---------
    scores = {}

    for num in weighted_freq.keys():

        wf = weighted_freq[num]
        momentum = short_freq[num]

        # gap
        gap = window - last_seen_index.get(num, window)
        gap_score = math.log1p(gap)

        # penalización si está muy caliente
        overheat_penalty = 0
        if momentum >= OVERHEAT_THRESHOLD:
            overheat_penalty = momentum * 0.8

        score = (
            0.35 * wf +
            0.25 * momentum +
            0.20 * gap_score -
            0.20 * overheat_penalty
        )

        scores[num] = score

    # ordenar
    ranked = sorted(scores.items(), key=lambda x: x[1], reverse=True)

    top12 = [x[0] for x in ranked[:12]]
    top3 = top12[:3]

    # métricas internas
    best_signal = ranked[0][1]
    best_a11 = sum(short_freq.get(n, 0) for n in top3)

    ok_alert = best_signal > 5  # threshold empírico

    # ---------
    # REGIME DETECTION
    # ---------
    avg_momentum = sum(short_freq.values()) / max(1, len(short_freq))

    if avg_momentum > 2:
        regime = "MOMENTUM"
    elif avg_momentum < 1:
        regime = "MEAN_REVERSION"
    else:
        regime = "MIXED"

    debug = {
        "window_used": window,
        "regime": regime,
        "unique_numbers": len(scores),
    }

    return ModelOutput(
        top3=top3,
        top12=top12,
        best_signal=best_signal,
        best_a11=best_a11,
        ok_alert=ok_alert,
        debug=debug
    )