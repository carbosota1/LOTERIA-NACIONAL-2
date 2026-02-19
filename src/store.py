import csv, json, os
from datetime import datetime
from typing import Dict, List

def ensure_csv(path: str, header: List[str]) -> None:
    os.makedirs(os.path.dirname(path), exist_ok=True)
    if not os.path.exists(path):
        with open(path, "w", newline="", encoding="utf-8") as f:
            w = csv.writer(f)
            w.writerow(header)

def append_csv(path: str, row: Dict, header: List[str]) -> None:
    ensure_csv(path, header)
    with open(path, "a", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=header)
        w.writerow({k: row.get(k, "") for k in header})

def load_state(path: str) -> Dict:
    if not os.path.exists(path):
        return {}
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)

def save_state(path: str, state: Dict) -> None:
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        json.dump(state, f, ensure_ascii=False, indent=2)

def now_iso() -> str:
    return datetime.utcnow().replace(microsecond=0).isoformat() + "Z"
