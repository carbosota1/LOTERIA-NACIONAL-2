# ============================================================
# FILE: src/alert_config.py
# LN ALERT SYSTEM — Configuración central v3
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

@dataclass(frozen=True)
class AlertSettings:
    # History XLSX — mismo que el sistema principal (solo lectura)
    history_xlsx_path: str  = "data/la_nacional_history.xlsx"
    history_sheet_name: str = "history"
    window_n: int           = 120

    # Performance log del sistema PRINCIPAL (solo lectura)
    main_perf_log_path: str = "data/performance_log.csv"

    # Logs propios del alert system
    picks_log_path: str     = "data/alert_picks_log.csv"
    perf_log_path: str      = "data/alert_performance_log.csv"

    # Telegram
    telegram_bot_token_env: str = "TELEGRAM_BOT_TOKEN"
    telegram_chat_id_env: str   = "TELEGRAM_CHAT_ID"
