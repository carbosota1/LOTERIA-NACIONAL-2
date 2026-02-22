import math
from collections import Counter
from datetime import datetime


class LNOutput:
    def __init__(self, top3, top12, best_signal, a11, rows_used, same_day_mid_present, alert):
        self.top3 = top3
        self.top12 = top12
        self.best_signal = best_signal
        self.a11 = a11
        self.rows_used = rows_used
        self.same_day_mid_present = same_day_mid_present
        self.alert = alert


def _exp_decay_weight(days_diff, decay_lambda=0.015):
    return math.exp(-decay_lambda * days_diff)


def _dynamic_window_size(history):
    # Si no tienes flag "hit" aún, simplemente usa 300
    return 300


def _compute_scores(history, window_size):
    today = datetime.now().date()
    recent = history[-window_size:]

    freq = Counter()
    momentum = Counter()

    for row in recent:
        fecha = datetime.strptime(row["fecha"], "%Y-%m-%d").date()
        days_diff = (today - fecha).days
        weight = _exp_decay_weight(days_diff)

        nums = [row["primero"], row["segundo"], row["tercero"]]

        for n in nums:
            freq[n] += weight
            if days_diff <= 7:
                momentum[n] += 1.5

    scores = {}

    for n in freq:
        base = freq[n]
        mom = momentum.get(n, 0)
        score = base + mom

        # Penalización si salió recientemente
        for row in history[-3:]:
            if n in [row["primero"], row["segundo"], row["tercero"]]:
                score *= 0.85

        scores[n] = score

    return scores


# 🔒 BLINDADA: todos los parámetros opcionales
def rank_numbers_from_draws(history, draw_type=None, slot=None, window_n=None):

    if not history or len(history) < 50:
        return None

    # Si runner manda window_n lo respetamos
    if window_n:
        window = window_n
    else:
        window = _dynamic_window_size(history)

    scores = _compute_scores(history, window)

    ranked = sorted(scores.items(), key=lambda x: x[1], reverse=True)

    numbers = [x[0] for x in ranked]

    top12 = numbers[:12]
    top3 = numbers[:3]

    # Anti repetición del día anterior
    yesterday = history[-1]
    prev_nums = [yesterday["primero"], yesterday["segundo"], yesterday["tercero"]]

    if set(top3) == set(prev_nums) and len(numbers) > 3:
        top3 = numbers[:2] + [numbers[3]]

    best_signal = ranked[0][1]
    a11 = 10 + int(best_signal % 5)
    alert = best_signal > (sum(x[1] for x in ranked[:10]) / 10)

    return LNOutput(
        top3=top3,
        top12=top12,
        best_signal=round(best_signal, 6),
        a11=a11,
        rows_used=window,
        same_day_mid_present=False,
        alert=alert,
    )
