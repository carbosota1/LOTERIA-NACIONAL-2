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


def _extract_row_fields(row):
    """
    Soporta:
    dict -> row["fecha"]
    tuple -> (fecha, sorteo, primero, segundo, tercero)
    """

    if isinstance(row, dict):
        return (
            row["fecha"],
            row["primero"],
            row["segundo"],
            row["tercero"],
        )

    # si es tuple/list
    return (
        row[0],  # fecha
        row[2],  # primero
        row[3],  # segundo
        row[4],  # tercero
    )


def _compute_scores(history, window_size):
    today = datetime.now().date()
    recent = history[-window_size:]

    freq = Counter()
    momentum = Counter()

    for row in recent:
        fecha, primero, segundo, tercero = _extract_row_fields(row)

        fecha_dt = datetime.strptime(str(fecha), "%Y-%m-%d").date()
        days_diff = (today - fecha_dt).days
        weight = _exp_decay_weight(days_diff)

        nums = [primero, segundo, tercero]

        for n in nums:
            freq[n] += weight
            if days_diff <= 7:
                momentum[n] += 1.5

    scores = {}

    for n in freq:
        base = freq[n]
        mom = momentum.get(n, 0)
        score = base + mom

        # penalización si salió en últimos 3 sorteos
        for row in history[-3:]:
            _, p1, p2, p3 = _extract_row_fields(row)
            if n in [p1, p2, p3]:
                score *= 0.85

        scores[n] = score

    return scores


def rank_numbers_from_draws(history, draw_type=None, slot=None, window_n=None):

    if not history or len(history) < 50:
        return None

    window = window_n if window_n else 300

    scores = _compute_scores(history, window)

    ranked = sorted(scores.items(), key=lambda x: x[1], reverse=True)

    numbers = [x[0] for x in ranked]

    top12 = numbers[:12]
    top3 = numbers[:3]

    # anti repetición exacta del sorteo anterior
    last_row = history[-1]
    _, p1, p2, p3 = _extract_row_fields(last_row)
    prev_nums = [p1, p2, p3]

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
