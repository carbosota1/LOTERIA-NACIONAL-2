from typing import List, Dict, Tuple

def score_hits(top3: List[str], top12: List[str], observed: Tuple[str,str,str]) -> Dict:
    obs = list(observed)
    hits3 = [x for x in obs if x in top3]
    hits12 = [x for x in obs if x in top12]

    positions = []
    for x in hits12:
        positions.append(str(top12.index(x) + 1))

    return {
        "hits_top3_count": len(hits3),
        "hits_top12_count": len(hits12),
        "hit_any_top3": 1 if len(hits3) > 0 else 0,
        "hit_any_top12": 1 if len(hits12) > 0 else 0,
        "hit_positions_top12": ",".join(positions),
    }
