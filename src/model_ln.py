# ========================
# FILE: src/model_ln.py
# ========================

import math
from collections import Counter


class LNOutput:
    def __init__(self, top3, top12, best_signal, best_a11, ok_alert, debug):
        self.top3 = top3
        self.top12 = top12
        self.best_signal = best_signal
        self.best_a11 = best_a11
        self.ok_alert = ok_alert
        self.debug = debug


def rank_numbers_from_draws(draws, window_n=300):
    """
    draws = List[Tuple[n1, n2, n3]]
    EXACTAMENTE lo que tu runner envía.
    """

    if not draws or len(draws) < 50:
        raise ValueError("Historial insuficiente")

    recent = draws[-window_n:]

    freq = Counter()
    last_7 = recent[-7:]
    last_3 = recent[-3:]

    # Frecuencia base
    for n1, n2, n3 in recent:
        freq[n1] += 1
        freq[n2] += 1
        freq[n3] += 1

    scores = {}

    for num in freq:

        base = freq[num]

        # Momentum últimos 7 sorteos
        momentum = 0
        for n1, n2, n3 in last_7:
            if num in (n1, n2, n3):
                momentum += 1.5

        score = base + momentum

        # Penalización si salió en últimos 3
        for n1, n2, n3 in last_3:
            if num in (n1, n2, n3):
                score *= 0.85

        scores[num] = score

    ranked = sorted(scores.items(), key=lambda x: x[1], reverse=True)

    numbers = [x[0] for x in ranked]

    top12 = numbers[:12]
    top3 = numbers[:3]

    # Anti repetir exactamente el último sorteo
    last_draw = recent[-1]
    if set(top3) == set(last_draw) and len(numbers) > 3:
        top3 = numbers[:2] + [numbers[3]]

    best_signal = ranked[0][1]

    # A11 dinámico basado en dispersión
    avg_top10 = sum(x[1] for x in ranked[:10]) / 10
    variance = sum((x[1] - avg_top10) ** 2 for x in ranked[:10]) / 10
    best_a11 = int(10 + variance % 5)

    ok_alert = best_signal > avg_top10

    debug = {
        "unique_numbers": len(freq),
        "window_used": len(recent),
    }

    return LNOutput(
        top3=top3,
        top12=top12,
        best_signal=round(best_signal, 6),
        best_a11=best_a11,
        ok_alert=ok_alert,
        debug=debug,
    )