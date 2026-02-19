import csv
import os
from datetime import datetime
from typing import Dict, List

def ensure_csv(path: str, header: List[str]) -> None:
    os.makedirs(os.path.dirname(path), exist_ok=True)
    if not os.path.exists(path):
        with open(path, "w", newline="", encoding="utf-8") as f:
            csv.writer(f).writerow(header)

def append_csv(path: str, row: Dict, header: List[str]) -> None:
    ensure_csv(path, header)
    with open(path, "a", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=header)
        w.writerow({k: row.get(k, "") for k in header})

def now_iso_utc() -> str:
    return datetime.utcnow().replace(microsecond=0).isoformat() + "Z"
