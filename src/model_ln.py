# ========================
# FILE: src/model_ln.py
# ========================

from dataclasses import dataclass
from typing import List, Tuple, Dict
from collections import Counter


@dataclass
class ModelOutput:
    top3: List[str]
    top12: List[str]
    best_signal: float
    best_a11: int
    ok_alert: bool
    debug: Dict


def rank_numbers_from_draws(
    draws: List[Tuple[str, str, str]],
    window_n: int = 120
) -> ModelOutput:
    """
    draws: lista de tuplas (n1, n2, n3)
    window_n: cantidad máxima de sorteos a usar desde el final
    """

    if not draws:
        raise ValueError("Historial vacío")

    # Usar solo los últimos window_n sorteos
    draws_slice = draws[-window_n:] if len(draws) > window_n else draws

    counter = Counter()

    for n1, n2, n3 in draws_slice:
        counter[n1] += 1
        counter[n2] += 1
        counter[n3] += 1

    # Ordenar por frecuencia
    ranked = sorted(counter.items(), key=lambda x: x[1], reverse=True)

    top_numbers = [num for num, _ in ranked[:12]]

    # Asegurar siempre 12 números
    while len(top_numbers) < 12:
        top_numbers.append("00")

    top3 = top_numbers[:3]

    # Métricas simples
    best_signal = float(ranked[0][1]) if ranked else 0.0
    best_a11 = len([c for _, c in ranked[:11]])

    ok_alert = best_signal > 5  # puedes ajustar esto luego

    debug = {
        "total_draws_used": len(draws_slice),
        "unique_numbers": len(counter)
    }

    return ModelOutput(
        top3=top3,
        top12=top_numbers,
        best_signal=best_signal,
        best_a11=best_a11,
        ok_alert=ok_alert,
        debug=debug
    )