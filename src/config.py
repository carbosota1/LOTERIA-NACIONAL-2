# ========================
# FILE: src/config.py
# ========================
from dataclasses import dataclass
from zoneinfo import ZoneInfo

TZ_RD = ZoneInfo("America/Santo_Domingo")

DRAW_GANAMAS = "Loteria Nacional- Gana Más"
DRAW_NOCHE   = "Loteria Nacional- Noche"

LABEL_MAP = {
    DRAW_GANAMAS: "MID",
    DRAW_NOCHE: "NIGHT",
}

# ✅ Anti-fantasma por horario (RD)
# Ajusta estas horas si tu operación oficial es distinta.
MID_PUBLISH_HOUR = 14    # 2:40 PM RD
MID_PUBLISH_MIN  = 40

NIGHT_PUBLISH_HOUR = 21  # 9:15 PM RD
NIGHT_PUBLISH_MIN  = 15

PUBLISH_BUFFER_MIN = 8   # buffer de publicación del site (minutos)

@dataclass(frozen=True)
class Settings:
    history_xlsx_path: str = "data/la_nacional_history.xlsx"
    history_sheet_name: str = "history"
    window_n: int = 120

    telegram_bot_token_env: str = "TELEGRAM_BOT_TOKEN"
    telegram_chat_id_env: str = "TELEGRAM_CHAT_ID"
