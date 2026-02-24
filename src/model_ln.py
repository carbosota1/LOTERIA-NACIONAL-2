import pandas as pd
import numpy as np
from datetime import datetime


# ==========================================================
# UTILIDADES
# ==========================================================

def _normalize_numbers(df):
    for col in ["primero", "segundo", "tercero"]:
        df[col] = df[col].astype(str).str.zfill(2)
    return df


def _flatten_draws(df):
    return pd.concat([
        df["primero"],
        df["segundo"],
        df["tercero"]
    ]).reset_index(drop=True)


def _weighted_counts(series, alpha=0.97):
    """
    Peso exponencial: más reciente pesa más
    """
    weights = np.array([alpha ** i for i in range(len(series))])
    weights = weights[::-1]
    return series.groupby(series).apply(
        lambda x: weights[x.index].sum()
    )


def _decade(n):
    return int(n) // 10


# ==========================================================
# MODELO PRINCIPAL
# ==========================================================

def rank_numbers_from_draws(history_df, draw_type):
    """
    history_df: dataframe completo
    draw_type: "Gana Más" o "Noche"
    """

    if history_df is None or len(history_df) < 50:
        raise ValueError("History insuficiente.")

    df = history_df.copy()

    df = df[df["sorteo"].str.contains(draw_type, case=False, na=False)]

    if len(df) < 50:
        raise ValueError("No hay suficientes datos para ese sorteo.")

    df = _normalize_numbers(df)

    # ==========================================
    # WINDOW DINÁMICO
    # ==========================================
    WINDOW = 350
    df = df.tail(WINDOW)

    flat = _flatten_draws(df)

    if len(flat) < 50:
        raise ValueError("History muy corto tras filtrar.")

    # ==========================================
    # BASE SCORE (peso exponencial)
    # ==========================================
    weighted = _weighted_counts(flat)

    score = {}
    for n in [f"{i:02d}" for i in range(100)]:
        score[n] = weighted.get(n, 0.0)

    # ==========================================
    # ATRASO ESTRUCTURAL
    # ==========================================
    last_seen = {}
    reversed_flat = flat[::-1].reset_index(drop=True)

    for n in score.keys():
        try:
            idx = reversed_flat[reversed_flat == n].index[0]
            last_seen[n] = idx
        except:
            last_seen[n] = len(flat)

    atraso_prom = np.mean(list(last_seen.values()))

    for n in score:
        if last_seen[n] > atraso_prom:
            score[n] *= 1.15  # boost atraso

    # ==========================================
    # SOBRECALENTAMIENTO (penalización reciente)
    # ==========================================
    recent = flat.tail(12)
    recent_counts = recent.value_counts()

    for n, c in recent_counts.items():
        if c >= 2:
            score[n] *= 0.70  # penalización fuerte

    # ==========================================
    # BALANCE POR DECENAS
    # ==========================================
    decades = {}
    for n in score:
        d = _decade(n)
        decades.setdefault(d, 0)
        decades[d] += score[n]

    decade_avg = np.mean(list(decades.values()))

    for n in score:
        d = _decade(n)
        if decades[d] < decade_avg:
            score[n] *= 1.10  # boost decena fría

    # ==========================================
    # NORMALIZAR
    # ==========================================
    total = sum(score.values())
    if total == 0:
        raise ValueError("Score total 0.")

    for n in score:
        score[n] = score[n] / total

    ranked = sorted(score.items(), key=lambda x: x[1], reverse=True)

    top12 = [n for n, _ in ranked[:12]]
    top3 = top12[:3]

    best_signal = ranked[0][1]

    return {
        "top3": top3,
        "top12": top12,
        "best_signal": round(best_signal, 6),
        "rows_used": len(df)
    }