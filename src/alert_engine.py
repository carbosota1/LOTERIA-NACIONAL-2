# ============================================================
# FILE: src/alert_engine.py
# LN ALERT SYSTEM — Motor de decisión
# Lee outputs del modelo y decide SI jugar, QUÉ posiciones
# y construye el mensaje Telegram.
# NO toca la lógica del modelo original.
# ============================================================
from __future__ import annotations
from dataclasses import dataclass, field
from datetime import datetime
from typing import List, Optional, Tuple

from alert_config import (
    SIGNAL_RULES, PRIORITY_POSITIONS, OBS_DOMINANT,
    BEST_DAYS, NIVEL_FUEGO, NIVEL_VERDE, NIVEL_AMARILLO, NIVEL_SKIP,
)


# ── Resultado de evaluación ──────────────────────────────────
@dataclass
class AlertDecision:
    should_play: bool
    nivel: str
    hit_top12_pct: int
    hit_top3_pct: int
    play_top3: bool
    priority_positions: List[int]
    numbers_to_play: List[str]        # números del top12 en posiciones prio
    obs_dominant: str
    good_day: bool
    day_name: str
    reason: str


# ── Motor principal ──────────────────────────────────────────
def evaluate(
    best_a11: int,
    best_signal: float,
    ok_alert: bool,
    turno: str,
    top12: List[str],
    top3: List[str],
    fecha: Optional[str] = None,
) -> AlertDecision:
    """
    Evalúa si se debe jugar basándose en la data histórica.
    No modifica ni reordena top3/top12.
    """

    # 1) Filtro base: modelo dice no alertar
    if not ok_alert:
        return AlertDecision(
            should_play=False, nivel=NIVEL_SKIP,
            hit_top12_pct=0, hit_top3_pct=0,
            play_top3=False, priority_positions=[],
            numbers_to_play=[], obs_dominant="",
            good_day=False, day_name="",
            reason="Modelo descartó esta jugada (ok_alert=False).",
        )

    # 2) Buscar regla de signal
    nivel = NIVEL_AMARILLO
    hr12, hr3 = 20, 0
    rule_found = False

    for rule in SIGNAL_RULES:
        ra11, rturno, smin, smax, rhr12, rhr3, rnivel = rule
        if ra11 == best_a11 and rturno == turno and smin <= best_signal < smax:
            nivel, hr12, hr3 = rnivel, rhr12, rhr3
            rule_found = True
            break

    # Sin regla específica → conservador
    if not rule_found:
        nivel = NIVEL_AMARILLO
        hr12, hr3 = 20, 0

    # 3) Zona muerta → salir
    if nivel == NIVEL_SKIP:
        return AlertDecision(
            should_play=False, nivel=NIVEL_SKIP,
            hit_top12_pct=hr12, hit_top3_pct=hr3,
            play_top3=False, priority_positions=[],
            numbers_to_play=[], obs_dominant="",
            good_day=False, day_name="",
            reason=f"Zona de baja performance (A11={best_a11}/{turno}/signal={best_signal:.3f}). No jugar.",
        )

    # 4) Día de semana
    good_day = False
    day_name = ""
    if fecha:
        try:
            dt = datetime.strptime(fecha, "%Y-%m-%d")
            day_name = dt.strftime("%A")
            good_day = day_name in BEST_DAYS.get((best_a11, turno), [])
        except Exception:
            pass

    # 5) Posiciones prioritarias
    prio_pos = PRIORITY_POSITIONS.get((best_a11, turno), [12, 11, 10, 9, 8, 7])
    numbers_to_play = [top12[p - 1] for p in prio_pos if 0 < p <= len(top12)]

    # 6) Qué número observado esperar
    obs_dom = OBS_DOMINANT.get((best_a11, turno), "n1/n2/n3")

    # 7) ¿Jugar top3 también?
    play_top3 = hr3 >= 20

    # 8) Decisión final
    if nivel in (NIVEL_FUEGO, NIVEL_VERDE):
        should_play = True
    elif nivel == NIVEL_AMARILLO:
        should_play = good_day  # solo si el día acompaña
    else:
        should_play = False

    # 9) Razón
    day_tag = f" | {day_name} {'✅ día favorable' if good_day else '(día neutro)'}" if day_name else ""
    reason = (
        f"A11={best_a11} | {turno} | signal={best_signal:.4f} "
        f"→ {hr12}% hit_top12 histórico{day_tag}"
    )

    return AlertDecision(
        should_play=should_play,
        nivel=nivel,
        hit_top12_pct=hr12,
        hit_top3_pct=hr3,
        play_top3=play_top3,
        priority_positions=prio_pos,
        numbers_to_play=numbers_to_play,
        obs_dominant=obs_dom,
        good_day=good_day,
        day_name=day_name,
        reason=reason,
    )


# ── Formateador Telegram ─────────────────────────────────────
_EMOJI = {
    NIVEL_FUEGO:    "🔥",
    NIVEL_VERDE:    "✅",
    NIVEL_AMARILLO: "⚠️",
    NIVEL_SKIP:     "⛔",
}

def build_message(
    decision: AlertDecision,
    fecha: str,
    turno: str,
    best_a11: int,
    best_signal: float,
    top12: List[str],
    top3: List[str],
    rows_used: int,
) -> str:
    turno_label = "Gana Más" if turno == "MID" else "Noche"
    emoji = _EMOJI.get(decision.nivel, "❓")

    # ── Mensaje de NO jugar ──────────────────────────────────
    if not decision.should_play:
        return (
            f"{emoji} <b>[ALERT SYS] LN — {turno_label}</b>\n"
            f"📅 {fecha}\n\n"
            f"<b>NO JUGAR</b>\n\n"
            f"🔍 {decision.reason}\n\n"
            f"🧠 A11: {best_a11} | Signal: {best_signal:.4f} | rows: {rows_used}"
        )

    # ── Bloque de números por posición ──────────────────────
    pos_lines = []
    for pos in decision.priority_positions[:6]:
        idx = pos - 1
        if 0 <= idx < len(top12):
            pos_lines.append(f"   Pos {pos:02d} → <b>{top12[idx]}</b>")
    pos_block = "\n".join(pos_lines)

    # ── Bloque top3 opcional ─────────────────────────────────
    top3_block = ""
    if decision.play_top3:
        top3_block = (
            f"\n🎯 <b>TOP3 también recomendado:</b> {', '.join(top3)}\n"
            f"   📈 {decision.hit_top3_pct}% hit_top3 histórico\n"
        )

    return (
        f"{emoji} <b>[ALERT SYS] LN — {turno_label}</b>\n"
        f"📅 {fecha} | Nivel: <b>{decision.nivel}</b>\n\n"
        f"▶️ <b>JUGAR — {decision.hit_top12_pct}% hit histórico</b>\n\n"
        f"📌 <b>Números a jugar (posiciones prioritarias):</b>\n"
        f"{pos_block}\n"
        f"{top3_block}\n"
        f"📋 <b>Top12 completo:</b> {', '.join(top12)}\n\n"
        f"💡 <b>Espera el</b> <b>{decision.obs_dominant}</b> del resultado oficial\n\n"
        f"🔍 {decision.reason}\n\n"
        f"🧠 A11: {best_a11} | Signal: {best_signal:.4f} | rows: {rows_used}"
    )
