from dataclasses import dataclass
from zoneinfo import ZoneInfo

TZ_RD = ZoneInfo("America/Santo_Domingo")

DRAW_GANAMAS = "Loteria Nacional- Gana Más"
DRAW_NOCHE   = "Loteria Nacional- Noche"

LABEL_MAP = {
    DRAW_GANAMAS: "MID",
    DRAW_NOCHE: "NIGHT",
}

@dataclass(frozen=True)
class Settings:
    history_xlsx_path: str = "data/la_nacional_history.xlsx"
    history_sheet_name: str = "history"
    window_n: int = 120

    telegram_bot_token_env: str = "TELEGRAM_BOT_TOKEN"
    telegram_chat_id_env: str = "TELEGRAM_CHAT_ID"
