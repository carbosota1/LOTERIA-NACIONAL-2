# ============================================================
# FILE: src/alert_engine.py
# LN ALERT SYSTEM — Motor de aprendizaje dinámico v3
#
# Lee AMBOS performance logs (principal + alert) para máxima data.
# Calcula todo en tiempo real con peso mayor a lo reciente.
# Manda resumen en el sync nocturno.
# ============================================================
from __future__ import annotations

import csv
import os
from collections import Counter, defaultdict
from dataclasses import dataclass
from datetime import datetime
from typing import Dict, List, Optional, Tuple


# ── Constantes ────────────────────────────────────────────────
SIGNAL_BINS   = [0, 1.5, 1.7, 1.8, 1.9, 2.0, 2.1, 2.3, 2.5, 3.0, 99.0]
SIGNAL_LABELS = [
    "<1.5","1.5-1.7","1.7-1.8","1.8-1.9",
    "1.9-2.0","2.0-2.1","2.1-2.3","2.3-2.5","2.5-3.0",">3.0",
]

MIN_SAMPLES      = 5      # mínimo para confiar en la regla
DECAY            = 0.92   # peso decreciente (más bajo = más peso a lo reciente)
DEFAULT_HIT_RATE = 0.25   # conservador cuando no hay data

# Umbrales de nivel
UMBRAL_FUEGO    = 0.50
UMBRAL_VERDE    = 0.35
UMBRAL_AMARILLO = 0.18

NIVEL_FUEGO       = "FUEGO"
NIVEL_VERDE       = "VERDE"
NIVEL_AMARILLO    = "AMARILLO"
NIVEL_SKIP        = "SKIP"
NIVEL_APRENDIENDO = "APRENDIENDO"

_EMOJI = {
    NIVEL_FUEGO:       "🔥",
    NIVEL_VERDE:       "✅",
    NIVEL_AMARILLO:    "⚠️",
    NIVEL_SKIP:        "⛔",
    NIVEL_APRENDIENDO: "📊",
}


# ── Resultado de decisión ─────────────────────────────────────
@dataclass
class AlertDecision:
    should_play: bool
    nivel: str
    hit12_pct: float
    hit3_pct: float
    n_samples: int
    play_top3: bool
    priority_positions: List[int]
    numbers_to_play: List[str]
    obs_dominant: str
    good_day: bool
    day_name: str
    reason: str
    signal_bin: str


# ── Helpers ───────────────────────────────────────────────────
def _signal_bin(signal: float) -> str:
    for i in range(len(SIGNAL_BINS) - 1):
        if SIGNAL_BINS[i] <= signal < SIGNAL_BINS[i + 1]:
            return SIGNAL_LABELS[i]
    return ">3.0"


def _nivel_from_rate(rate: float, n: int) -> str:
    if n < MIN_SAMPLES:
        return NIVEL_APRENDIENDO
    if rate >= UMBRAL_FUEGO:
        return NIVEL_FUEGO
    if rate >= UMBRAL_VERDE:
        return NIVEL_VERDE
    if rate >= UMBRAL_AMARILLO:
        return NIVEL_AMARILLO
    return NIVEL_SKIP


# ── Cargador de logs ──────────────────────────────────────────
def _load_log(path: str) -> List[dict]:
    """Carga un performance log (principal o alert) normalizando campos."""
    if not os.path.exists(path):
        return []
    rows = []
    with open(path, "r", encoding="utf-8") as f:
        for row in csv.DictReader(f):
            try:
                signal = float(row.get("best_signal", 0))
                a11    = int(float(row.get("best_a11", -1)))
                hit12  = int(row.get("hit_any_top12", 0))
                hit3   = int(row.get("hit_any_top3", 0))
                did    = row.get("draw_id", "")
                turno  = "MID" if "|MID" in did else "NIGHT"
                top12  = [x.strip() for x in row.get("top12", "").split(",") if x.strip()]
                obs    = [
                    row.get("observed_n1", ""),
                    row.get("observed_n2", ""),
                    row.get("observed_n3", ""),
                ]
                date_str = did.split("|")[1] if did.count("|") >= 2 else ""
                dow = datetime.strptime(date_str, "%Y-%m-%d").strftime("%A") if date_str else ""
                ts  = row.get("picked_from_ts_run", "")

                rows.append({
                    "_draw_id":  did,
                    "_signal":   signal,
                    "_a11":      a11,
                    "_hit12":    hit12,
                    "_hit3":     hit3,
                    "_turno":    turno,
                    "_sig_bin":  _signal_bin(signal),
                    "_top12":    top12,
                    "_obs":      obs,
                    "_dow":      dow,
                    "_ts":       ts,
                    "_ok_alert": int(row.get("ok_alert", 1)),
                })
            except Exception:
                continue
    return rows


# ── Motor dinámico ────────────────────────────────────────────
class DynamicAlertEngine:
    """
    Aprende de ambos performance logs en cada ejecución.
    performance_log.csv  → historial completo del sistema principal
    alert_performance_log.csv → historial del alert system
    Los duplicados (mismo draw_id) se deduplicан conservando uno.
    """

    def __init__(self, main_perf_path: str, alert_perf_path: str):
        main_rows  = _load_log(main_perf_path)
        alert_rows = _load_log(alert_perf_path)

        # Deduplicar por draw_id — preferir alert (tiene nivel_alerta)
        seen: Dict[str, dict] = {}
        for r in main_rows:
            seen[r["_draw_id"]] = r
        for r in alert_rows:
            seen[r["_draw_id"]] = r   # alert sobreescribe si existe

        self._rows   = list(seen.values())
        self._n_total = len(self._rows)

    # ── Peso decreciente ──────────────────────────────────────
    def _weighted(self, rows: List[dict]) -> List[Tuple[dict, float]]:
        sorted_rows = sorted(rows, key=lambda r: r["_ts"])
        n = len(sorted_rows)
        return [(r, DECAY ** (n - 1 - i)) for i, r in enumerate(sorted_rows)]

    # ── Hit rate ponderado ────────────────────────────────────
    def _hit_rate(
        self, a11: int, turno: str, sig_bin: str, field: str = "_hit12"
    ) -> Tuple[float, int]:

        # Filtro exacto (a11 + turno + bin)
        exact = [
            r for r in self._rows
            if r["_a11"] == a11 and r["_turno"] == turno
            and r["_sig_bin"] == sig_bin and r["_ok_alert"] == 1
        ]
        if len(exact) >= MIN_SAMPLES:
            wrows   = self._weighted(exact)
            total_w = sum(w for _, w in wrows)
            hit_w   = sum(w for r, w in wrows if r[field] == 1)
            return (hit_w / total_w if total_w > 0 else 0.0, len(exact))

        # Ampliar a (a11 + turno)
        broad = [
            r for r in self._rows
            if r["_a11"] == a11 and r["_turno"] == turno and r["_ok_alert"] == 1
        ]
        if len(broad) >= MIN_SAMPLES:
            wrows     = self._weighted(broad)
            total_w   = sum(w for _, w in wrows)
            hit_w     = sum(w for r, w in wrows if r[field] == 1)
            broad_rate = hit_w / total_w if total_w > 0 else DEFAULT_HIT_RATE
            if exact:
                ex_rate = sum(r[field] for r in exact) / len(exact)
                blended = 0.7 * broad_rate + 0.3 * ex_rate
            else:
                blended = broad_rate
            return (blended, len(exact))

        return (DEFAULT_HIT_RATE, len(exact))

    # ── Mejores días ──────────────────────────────────────────
    def _best_days(self, a11: int, turno: str) -> List[str]:
        rows = [r for r in self._rows if r["_a11"] == a11 and r["_turno"] == turno]
        if len(rows) < 10:
            return []
        by_day: Dict[str, List[int]] = defaultdict(list)
        for r in rows:
            if r["_dow"]:
                by_day[r["_dow"]].append(r["_hit12"])
        return [
            day for day, hits in by_day.items()
            if len(hits) >= 3 and sum(hits) / len(hits) >= 0.38
        ]

    # ── Posiciones prioritarias ───────────────────────────────
    def _priority_positions(self, a11: int, turno: str) -> List[int]:
        hits = [
            r for r in self._rows
            if r["_a11"] == a11 and r["_turno"] == turno and r["_hit12"] == 1
        ]
        if len(hits) < 3:
            return [12, 11, 10, 9, 8, 7]
        pc = Counter()
        for r in hits:
            for obs in r["_obs"]:
                if obs in r["_top12"]:
                    pc[r["_top12"].index(obs) + 1] += 1
        return [p for p, _ in pc.most_common(6)] if pc else [12, 11, 10, 9, 8, 7]

    # ── Número observado dominante ────────────────────────────
    def _obs_dominant(self, a11: int, turno: str) -> str:
        hits = [
            r for r in self._rows
            if r["_a11"] == a11 and r["_turno"] == turno and r["_hit12"] == 1
        ]
        if not hits:
            return "n1/n2/n3"
        n1 = sum(1 for r in hits if r["_obs"][0] in r["_top12"])
        n2 = sum(1 for r in hits if r["_obs"][1] in r["_top12"])
        n3 = sum(1 for r in hits if r["_obs"][2] in r["_top12"])
        mx = max(n1, n2, n3)
        if mx == 0:
            return "n1/n2/n3"
        dominant = []
        if n1 == mx: dominant.append("n1")
        if n2 == mx: dominant.append("n2")
        if n3 == mx: dominant.append("n3")
        return "/".join(dominant)

    # ── Evaluación principal ──────────────────────────────────
    def evaluate(
        self,
        best_a11: int,
        best_signal: float,
        ok_alert: bool,
        turno: str,
        top12: List[str],
        top3: List[str],
        fecha: Optional[str] = None,
    ) -> AlertDecision:

        if not ok_alert:
            return AlertDecision(
                should_play=False, nivel=NIVEL_SKIP,
                hit12_pct=0.0, hit3_pct=0.0, n_samples=0,
                play_top3=False, priority_positions=[],
                numbers_to_play=[], obs_dominant="",
                good_day=False, day_name="",
                reason="Modelo descartó esta jugada (ok_alert=False).",
                signal_bin="",
            )

        sig_bin       = _signal_bin(best_signal)
        hr12, n_exact = self._hit_rate(best_a11, turno, sig_bin, "_hit12")
        hr3,  _       = self._hit_rate(best_a11, turno, sig_bin, "_hit3")
        nivel         = _nivel_from_rate(hr12, n_exact)

        # Día de semana
        good_day = False
        day_name = ""
        if fecha:
            try:
                day_name = datetime.strptime(fecha, "%Y-%m-%d").strftime("%A")
                good_day = day_name in self._best_days(best_a11, turno)
            except Exception:
                pass

        prio_pos  = self._priority_positions(best_a11, turno)
        obs_dom   = self._obs_dominant(best_a11, turno)
        nums_play = [top12[p - 1] for p in prio_pos if 0 < p <= len(top12)]
        play_top3 = hr3 >= 0.20 and n_exact >= MIN_SAMPLES

        # Decisión
        if nivel == NIVEL_SKIP:
            should_play = False
        elif nivel == NIVEL_APRENDIENDO:
            should_play = good_day
        elif nivel in (NIVEL_FUEGO, NIVEL_VERDE):
            should_play = True
        else:  # AMARILLO
            should_play = good_day or hr12 >= 0.30

        data_note = (
            f"{int(hr12*100)}% hit real ({n_exact} muestras)"
            if n_exact >= MIN_SAMPLES
            else f"Aprendiendo ({n_exact} muestras, mín {MIN_SAMPLES})"
        )
        day_tag = (
            f" | {day_name} ✅ día favorable" if good_day
            else (f" | {day_name}" if day_name else "")
        )
        reason = (
            f"A11={best_a11} | {turno} | signal={best_signal:.4f} "
            f"| bin={sig_bin} → {data_note}{day_tag}"
        )

        return AlertDecision(
            should_play=should_play, nivel=nivel,
            hit12_pct=round(hr12 * 100, 1),
            hit3_pct=round(hr3 * 100, 1),
            n_samples=n_exact,
            play_top3=play_top3,
            priority_positions=prio_pos,
            numbers_to_play=nums_play,
            obs_dominant=obs_dom,
            good_day=good_day, day_name=day_name,
            reason=reason, signal_bin=sig_bin,
        )

    # ── Resumen para sync ─────────────────────────────────────
    def sync_summary(self, new_results: List[dict]) -> str:
        """
        Genera mensaje Telegram con resumen del sync nocturno.
        new_results: lista de dicts con keys:
          draw_id, nivel_alerta, should_play,
          hit_any_top12, hit_any_top3, hit_positions_top12,
          observed_n1, observed_n2, observed_n3
        """
        if not new_results:
            return ""

        total   = self._n_total
        global_hit = (
            round(sum(r["_hit12"] for r in self._rows) / total * 100, 1)
            if total > 0 else 0
        )

        lines = [
            f"📊 <b>[ALERT SYS] Sync — {datetime.utcnow().strftime('%Y-%m-%d')}</b>\n"
        ]

        for res in new_results:
            turno_label = "Gana Más" if "|MID" in res["draw_id"] else "Noche"
            hit12  = int(res.get("hit_any_top12", 0))
            hit3   = int(res.get("hit_any_top3", 0))
            nivel  = res.get("nivel_alerta", "?")
            play   = int(res.get("should_play", 0))
            pos    = res.get("hit_positions_top12", "")
            obs    = f"{res.get('observed_n1','?')}, {res.get('observed_n2','?')}, {res.get('observed_n3','?')}"

            jugado = "▶️ Jugado" if play else "⏸ No jugado"
            result_icon = "✅" if hit12 else "❌"
            hit_note = f"pos {pos}" if (hit12 and pos) else ("top3 ✅" if hit3 else "no acertó")

            lines.append(
                f"🎯 <b>{turno_label}</b> | {jugado} | Nivel: {nivel}\n"
                f"   Resultado: {obs}\n"
                f"   {result_icon} {hit_note}\n"
            )

        lines.append(f"\n📈 <b>Total data: {total} muestras | Hit global: {global_hit}%</b>")
        return "\n".join(lines)


# ── Formateador Telegram (picks) ──────────────────────────────
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
    emoji       = _EMOJI.get(decision.nivel, "❓")

    data_note = (
        f"{decision.hit12_pct}% hit real ({decision.n_samples} muestras)"
        if decision.n_samples >= MIN_SAMPLES
        else f"Aprendiendo ({decision.n_samples} muestras)"
    )

    if not decision.should_play:
        return (
            f"{emoji} <b>[ALERT SYS] LN — {turno_label}</b>\n"
            f"📅 {fecha} | Nivel: <b>{decision.nivel}</b>\n\n"
            f"<b>NO JUGAR</b>\n"
            f"📉 {data_note}\n\n"
            f"🔍 {decision.reason}\n\n"
            f"🧠 A11: {best_a11} | Signal: {best_signal:.4f} | bin: {decision.signal_bin} | rows: {rows_used}"
        )

    pos_lines = []
    for pos in decision.priority_positions[:6]:
        idx = pos - 1
        if 0 <= idx < len(top12):
            pos_lines.append(f"   Pos {pos:02d} → <b>{top12[idx]}</b>")

    top3_block = ""
    if decision.play_top3:
        top3_block = (
            f"\n🎯 <b>TOP3 también recomendado:</b> {', '.join(top3)}\n"
            f"   📈 {decision.hit3_pct}% hit_top3 real\n"
        )

    return (
        f"{emoji} <b>[ALERT SYS] LN — {turno_label}</b>\n"
        f"📅 {fecha} | Nivel: <b>{decision.nivel}</b>\n\n"
        f"▶️ <b>JUGAR — {data_note}</b>\n\n"
        f"📌 <b>Números a jugar (posiciones prioritarias):</b>\n"
        f"{chr(10).join(pos_lines)}\n"
        f"{top3_block}\n"
        f"📋 <b>Top12 completo:</b> {', '.join(top12)}\n\n"
        f"💡 <b>Espera el</b> <b>{decision.obs_dominant}</b> del resultado oficial\n\n"
        f"🔍 {decision.reason}\n\n"
        f"🧠 A11: {best_a11} | Signal: {best_signal:.4f} | bin: {decision.signal_bin} | rows: {rows_used}"
    )
