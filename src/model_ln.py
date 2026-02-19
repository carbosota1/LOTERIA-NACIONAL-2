from collections import defaultdict, deque
from dataclasses import dataclass
from typing import List, Tuple, Dict
import math

@dataclass
class ModelOutput:
    top3: List[str]
    top12: List[str]
    debug: Dict

def _exp_weights(n: int, half_life: float = 30.0) -> List[float]:
    # pesos exponenciales: más reciente pesa más
    # w[t] para t=0..n-1 donde t=0 es el más antiguo; al final se normaliza
    lam = math.log(2) / half_life
    ws = [math.exp(lam * i) for i in range(n)]  # i crece hacia lo reciente
    s = sum(ws)
    return [w / s for w in ws]

def rank_numbers_from_draws(draws: List[Tuple[str,str,str]], window_n: int = 120) -> ModelOutput:
    """
    draws: lista de tuplas (n1,n2,n3) ordenadas cronológicamente (antiguo -> reciente).
    """
    if len(draws) < 30:
        raise ValueError("Historial insuficiente para rankear (mínimo recomendado 30).")

    last = draws[-window_n:] if len(draws) >= window_n else draws[:]
    n = len(last)

    weights = _exp_weights(n, half_life=30.0)

    # Frecuencia ponderada
    freq = defaultdict(float)
    # Atraso (distancia desde la última vez vista en ventana completa)
    last_seen = {f"{i:02d}": None for i in range(100)}

    for idx, (a,b,c) in enumerate(last):
        for x in (a,b,c):
            freq[x] += weights[idx]
        for x in (a,b,c):
            last_seen[x] = idx

    # tendencia corta (últimos 20)
    short = last[-20:] if n >= 20 else last
    short_count = defaultdict(int)
    for a,b,c in short:
        for x in (a,b,c):
            short_count[x] += 1

    def atraso_bonus(x: str) -> float:
        # bonus saturado 0..1
        if last_seen[x] is None:
            d = n
        else:
            d = (n - 1) - last_seen[x]
        lam = 0.12
        return 1.0 - math.exp(-lam * d)

    # score base
    scores = {}
    for i in range(100):
        x = f"{i:02d}"
        s = (
            0.60 * freq.get(x, 0.0) +
            0.25 * atraso_bonus(x) +
            0.15 * (short_count.get(x, 0) / max(1, len(short)*3))
        )
        scores[x] = s

    ranked = sorted(scores.keys(), key=lambda k: scores[k], reverse=True)
    top12 = ranked[:12]
    top3 = ranked[:3]

    debug = {
        "window_used": n,
        "top_score": scores[top12[0]],
        "bottom_top12_score": scores[top12[-1]],
    }
    return ModelOutput(top3=top3, top12=top12, debug=debug)
