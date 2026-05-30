# ============================================================
# FILE: src/alert_config.py
# LN ALERT SYSTEM — Configuración central
# ============================================================
from dataclasses import dataclass
from zoneinfo import ZoneInfo

TZ_RD = ZoneInfo("America/Santo_Domingo")

DRAW_GANAMAS = "Loteria Nacional- Gana Más"
DRAW_NOCHE   = "Loteria Nacional- Noche"

LABEL_MAP = {
    DRAW_GANAMAS: "MID",
    DRAW_NOCHE:   "NIGHT",
}

MID_PUBLISH_HOUR   = 14
MID_PUBLISH_MIN    = 40
NIGHT_PUBLISH_HOUR = 21
NIGHT_PUBLISH_MIN  = 15
PUBLISH_BUFFER_MIN = 8

NIVEL_FUEGO    = "FUEGO"
NIVEL_VERDE    = "VERDE"
NIVEL_AMARILLO = "AMARILLO"
NIVEL_SKIP     = "SKIP"

# ── Tabla de reglas de signal ────────────────────────────────
# Extraída del análisis de 219 sorteos (Feb–May 2026)
SIGNAL_RULES = [
    # ── A11 = 1 ─────────────────────────────────────────────
    (1, "MID",   1.50, 1.70,  100,  0, NIVEL_FUEGO),
    (1, "MID",   1.80, 1.90,    0,  0, NIVEL_SKIP),
    (1, "NIGHT", 1.90, 2.00,   50,  0, NIVEL_FUEGO),
    # ── A11 = 2 ─────────────────────────────────────────────
    (2, "MID",   1.70, 1.80,   80,  0, NIVEL_FUEGO),
    (2, "MID",   1.80, 1.90,   20, 20, NIVEL_AMARILLO),
    (2, "MID",   1.90, 2.00,    0,  0, NIVEL_SKIP),
    (2, "MID",   2.00, 2.10,   12,  0, NIVEL_SKIP),
    (2, "NIGHT", 1.50, 1.70,    0,  0, NIVEL_SKIP),
    (2, "NIGHT", 2.30, 2.50,   25,  0, NIVEL_AMARILLO),
    # ── A11 = 3 ─────────────────────────────────────────────
    (3, "MID",   1.80, 1.90,   71, 29, NIVEL_FUEGO),
    (3, "MID",   1.70, 1.80,   29,  0, NIVEL_AMARILLO),
    (3, "MID",   1.90, 2.00,   22,  0, NIVEL_AMARILLO),
    (3, "MID",   2.00, 2.10,    0,  0, NIVEL_SKIP),
    (3, "NIGHT", 2.30, 2.50,  100,  0, NIVEL_FUEGO),
    (3, "NIGHT", 1.50, 1.70,   43, 14, NIVEL_VERDE),
    (3, "NIGHT", 2.10, 2.30,   25, 25, NIVEL_AMARILLO),
    (3, "NIGHT", 1.80, 1.90,    0,  0, NIVEL_SKIP),
    (3, "NIGHT", 1.90, 2.00,    0,  0, NIVEL_SKIP),
    # ── A11 = 4 ─────────────────────────────────────────────
    (4, "MID",   1.50, 1.70,   67, 33, NIVEL_FUEGO),
    (4, "MID",   1.90, 2.00,   33,  0, NIVEL_VERDE),
    (4, "MID",   1.80, 1.90,   20,  0, NIVEL_AMARILLO),
    (4, "MID",   2.10, 2.30,   17, 17, NIVEL_AMARILLO),
    (4, "NIGHT", 2.30, 2.50,   80,  0, NIVEL_FUEGO),
    (4, "NIGHT", 1.80, 2.00,   50,  0, NIVEL_FUEGO),
    (4, "NIGHT", 2.10, 2.30,   33,  0, NIVEL_VERDE),
    (4, "NIGHT", 1.50, 1.80,    0,  0, NIVEL_SKIP),
    # ── A11 = 5 ─────────────────────────────────────────────
    (5, "MID",   1.50, 1.80,  100,  0, NIVEL_FUEGO),
    (5, "MID",   2.30, 2.50,   67,  0, NIVEL_FUEGO),
    (5, "MID",   2.50, 3.00,   40, 40, NIVEL_VERDE),
    (5, "MID",   2.10, 2.30,   30, 10, NIVEL_AMARILLO),
    (5, "MID",   1.80, 2.10,    0,  0, NIVEL_SKIP),
    (5, "NIGHT", 2.50, 3.00,   40, 40, NIVEL_VERDE),
    (5, "NIGHT", 1.70, 1.80,   33,  0, NIVEL_VERDE),
    (5, "NIGHT", 1.80, 2.50,    8,  0, NIVEL_SKIP),
    # ── A11 = 6 ─────────────────────────────────────────────
    (6, "MID",   1.70, 1.80,    0,  0, NIVEL_SKIP),
    (6, "NIGHT", 1.50, 3.00,   17,  0, NIVEL_AMARILLO),
    # ── A11 = 7 ─────────────────────────────────────────────
    (7, "NIGHT", 2.50, 3.00,   38,  0, NIVEL_VERDE),
    # ── A11 = 8 ─────────────────────────────────────────────
    (8, "NIGHT", 2.50, 3.00,   25,  0, NIVEL_AMARILLO),
]

# ── Posiciones prioritarias dentro del top12 ─────────────────
PRIORITY_POSITIONS = {
    (2, "MID"):   [10, 4, 9,  6,  3],
    (2, "NIGHT"): [6,  9, 11, 12, 8],
    (3, "MID"):   [12, 2, 7,  9,  11, 3],
    (3, "NIGHT"): [10, 4, 11, 1,  12, 9],
    (4, "MID"):   [2,  9, 11, 8,  12],
    (4, "NIGHT"): [12, 6, 9,  5,  10],
    (5, "MID"):   [10, 4, 11, 8,  3],
    (5, "NIGHT"): [1,  3, 8,  11, 10],
    (7, "NIGHT"): [11, 10, 8, 9,  12],
}

# ── Número observado dominante ───────────────────────────────
OBS_DOMINANT = {
    (2, "MID"):   "n2/n3",
    (2, "NIGHT"): "n3",
    (3, "MID"):   "n1/n3",
    (3, "NIGHT"): "n1/n3",
    (4, "MID"):   "n2",
    (4, "NIGHT"): "n1",
    (5, "MID"):   "n2",
    (5, "NIGHT"): "n2",
    (7, "NIGHT"): "n2",
}

# ── Mejores días por A11 + turno ─────────────────────────────
BEST_DAYS = {
    (2, "MID"):   ["Friday", "Thursday"],
    (2, "NIGHT"): ["Sunday"],
    (3, "MID"):   ["Thursday", "Saturday", "Friday"],
    (3, "NIGHT"): ["Thursday", "Saturday", "Monday"],
    (4, "MID"):   ["Wednesday", "Sunday", "Thursday"],
    (4, "NIGHT"): ["Wednesday", "Sunday", "Monday", "Friday"],
    (5, "MID"):   ["Wednesday", "Tuesday", "Saturday", "Monday", "Friday"],
    (5, "NIGHT"): ["Wednesday", "Tuesday", "Saturday"],
    (7, "NIGHT"): ["Monday", "Saturday", "Sunday"],
}

# ── Settings ─────────────────────────────────────────────────
# Apunta al mismo data/ del sistema principal
@dataclass(frozen=True)
class AlertSettings:
    history_xlsx_path: str  = "data/la_nacional_history.xlsx"
    history_sheet_name: str = "history"
    window_n: int           = 120
    picks_log_path: str     = "data/alert_picks_log.csv"
    perf_log_path: str      = "data/alert_performance_log.csv"
    telegram_bot_token_env: str = "TELEGRAM_BOT_TOKEN"
    telegram_chat_id_env: str   = "TELEGRAM_CHAT_ID"
