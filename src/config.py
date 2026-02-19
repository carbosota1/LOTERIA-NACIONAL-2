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
    history_xml_path: str = "data/La_nacional_history.xml"
    window_n: int = 120

    # Telegram (se inyecta por env vars en GH Actions)
    telegram_bot_token_env: str = "TELEGRAM_BOT_TOKEN"
    telegram_chat_id_env: str = "TELEGRAM_CHAT_ID"
