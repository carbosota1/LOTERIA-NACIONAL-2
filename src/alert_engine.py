# ============================================================
# FILE: src/alert_engine.py
# LN ALERT SYSTEM — Motor de aprendizaje dinámico
#
# En lugar de reglas fijas, calcula todo en tiempo real
# leyendo el alert_performance_log.csv acumulado.
# Mientras menos datos haya, más conservador es.
# Lo reciente pesa más (decay).
# ============================================================
from __future__ import annotations

import csv
import math
import os
from collections import Counter, defaultdict
from dataclasses import dataclass, field
from datetime import datetime
from typing import Dict, List, Optional, Tuple


# ── Constantes de comportamiento ─────────────────────────────
SIGNAL_BINS   = [0, 1.5, 1.7, 1.8, 1.9, 2.0, 2.1, 2.3, 2.5, 3.0, 99.0]
SIGNAL_LABELS = [
    "<1.5","1.5-1.7","1.7-1.8","1.8-1.9",
    "1.9-2.0","2.0-2.1","2.1-2.3","2.3-2.5","2.5-3.0",">3.0",
]

MIN_SAMPLES      = 5     # mínimo para confiar en la regla aprendida
DECAY            = 0.92  # peso de lo reciente (más bajo = más peso a lo nuevo)
DEFAULT_HIT_RATE = 0.25  # hit rate conservador cuando no hay suficiente data

# Umbrales de nivel basados en hit rate real
UMBRAL_FUEGO    = 0.50
UMBRAL_VERDE    = 0.35
UMBRAL_AMARILLO = 0.18

# ── Niveles ──────────────────────────────────────────────────
NIVEL_FUEGO    = "FUEGO"
NIVEL_VERDE    = "VERDE"
NIVEL_AMARILLO = "AMARILLO"
NIVEL_SKIP     = "SKIP"
NIVEL_APRENDIENDO = "APRENDIENDO"   # < MIN_SAMPLES

_EMOJI = {
    NIVEL_FUEGO:       "🔥",
    NIVEL_VERDE:       "✅",
    NIVEL_AMARILLO:    "⚠️",
    NIVEL_SKIP:        "⛔",
    NIVEL_APRENDIENDO: "📊",
}


# ── Resultado de la decisión ──────────────────────────────────
@dataclass
class AlertDecision:
    should_play: bool
    nivel: str
    hit12_pct: float          # % hit_top12 calculado dinámicamente
    hit3_pct: float           # % hit_top3 calculado dinámicamente
    n_samples: int            # cuántas muestras usó para calcular
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


# ── Cargador de performance log ───────────────────────────────
def _load_perf(perf_path: str) -> List[dict]:
    if not os.path.exists(perf_path):
        return []
    rows = []
    with open(perf_path, "r", encoding="utf-8") as f:
        for row in csv.DictReader(f):
            try:
                row["_signal"]   = float(row.get("best_signal", 0))
                row["_a11"]      = int(float(row.get("best_a11", -1)))
                row["_hit12"]    = int(row.get("hit_any_top12", 0))
                row["_hit3"]     = int(row.get("hit_any_top3", 0))
                row["_ts"]       = row.get("picked_from_ts_run", "")
                row["_turno"]    = "MID" if "|MID" in row.get("draw_id", "") else "NIGHT"
                row["_sig_bin"]  = _signal_bin(row["_signal"])
                row["_top12"]    = [x.strip() for x in row.get("top12", "").split(",") if x.strip()]
                row["_obs"]      = [
                    row.get("observed_n1", ""),
                    row.get("observed_n2", ""),
                    row.get("observed_n3", ""),
                ]
                # día de semana
                date_str = row.get("draw_id", "").split("|")[1] if "|" in row.get("draw_id", "") else ""
                row["_dow"] = datetime.strptime(date_str, "%Y-%m-%d").strftime("%A") if date_str else ""
                rows.append(row)
            except Exception:
                continue
    return rows


# ── Motor dinámico ────────────────────────────────────────────
class DynamicAlertEngine:
    """
    Aprende de alert_performance_log.csv en cada ejecución.
    No tiene reglas fijas — todo se calcula desde los datos reales.
    """

    def __init__(self, perf_path: str):
        self._rows = _load_perf(perf_path)
        self._n_total = len(self._rows)

    # ── Peso decreciente (lo reciente pesa más) ───────────────
    def _weighted_rows(
        self,
        rows: List[dict],
        decay: float = DECAY,
    ) -> List[Tuple[dict, float]]:
        """Devuelve [(row, weight)] ordenado cronológicamente."""
        sorted_rows = sorted(rows, key=lambda r: r["_ts"])
        n = len(sorted_rows)
        return [
            (r, decay ** (n - 1 - i))
            for i, r in enumerate(sorted_rows)
        ]

    # ── Hit rate ponderado para una combinación ───────────────
    def _hit_rate(
        self,
        a11: int,
        turno: str,
        sig_bin: str,
        field: str = "_hit12",
    ) -> Tuple[float, int]:
        """
        Devuelve (hit_rate_ponderado, n_muestras) para la combo exacta.
        Si hay pocas muestras, amplía a nivel (a11, turno) para orientarse.
        """
        # Filtro exacto
        exact = [
            r for r in self._rows
            if r["_a11"] == a11
            and r["_turno"] == turno
            and r["_sig_bin"] == sig_bin
        ]

        if len(exact) >= MIN_SAMPLES:
            weighted = self._weighted_rows(exact)
            total_w  = sum(w for _, w in weighted)
            hit_w    = sum(w for r, w in weighted if r[field] == 1)
            return (hit_w / total_w if total_w > 0 else 0.0, len(exact))

        # Pocas muestras — ampliar a (a11, turno)
        broad = [
            r for r in self._rows
            if r["_a11"] == a11 and r["_turno"] == turno
        ]
        if len(broad) >= MIN_SAMPLES:
            weighted  = self._weighted_rows(broad)
            total_w   = sum(w for _, w in weighted)
            hit_w     = sum(w for r, w in weighted if r[field] == 1)
            broad_rate = hit_w / total_w if total_w > 0 else DEFAULT_HIT_RATE
            # Blend: 30% broad + muestra exacta si existe
            if exact:
                ex_rate = sum(r[field] for r in exact) / len(exact)
                blended = 0.7 * broad_rate + 0.3 * ex_rate
            else:
                blended = broad_rate
            return (blended, len(exact))   # n_samples = exact (honesto)

        # Sin datos — valor por defecto conservador
        return (DEFAULT_HIT_RATE, len(exact))

    # ── Mejores días aprendidos ───────────────────────────────
    def _best_days(self, a11: int, turno: str) -> List[str]:
        rows = [r for r in self._rows if r["_a11"] == a11 and r["_turno"] == turno]
        if len(rows) < 10:
            return []
        by_day: Dict[str, List[int]] = defaultdict(list)
        for r in rows:
            if r["_dow"]:
                by_day[r["_dow"]].append(r["_hit12"])
        good = []
        for day, hits in by_day.items():
            if len(hits) >= 2 and sum(hits) / len(hits) >= 0.40:
                good.append(day)
        return good

    # ── Posiciones prioritarias aprendidas ────────────────────
    def _priority_positions(self, a11: int, turno: str) -> List[int]:
        rows = [r for r in self._rows if r["_a11"] == a11 and r["_turno"] == turno]
        hits = [r for r in rows if r["_hit12"] == 1]
        if len(hits) < 3:
            return [12, 11, 10, 9, 8, 7]   # default

        pc = Counter()
        for r in hits:
            for obs in r["_obs"]:
                if obs in r["_top12"]:
                    pc[r["_top12"].index(obs) + 1] += 1

        return [p for p, _ in pc.most_common(6)] if pc else [12, 11, 10, 9, 8, 7]

    # ── Número observado dominante aprendido ──────────────────
    def _obs_dominant(self, a11: int, turno: str) -> str:
        rows = [r for r in self._rows if r["_a11"] == a11 and r["_turno"] == turno]
        hits = [r for r in rows if r["_hit12"] == 1]
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

        # 1) Modelo dice no alertar
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

        sig_bin = _signal_bin(best_signal)

        # 2) Hit rates dinámicos
        hr12, n12 = self._hit_rate(best_a11, turno, sig_bin, "_hit12")
        hr3,  n3  = self._hit_rate(best_a11, turno, sig_bin, "_hit3")

        nivel = _nivel_from_rate(hr12, n12)

        # 3) Día de semana
        good_day  = False
        day_name  = ""
        if fecha:
            try:
                day_name  = datetime.strptime(fecha, "%Y-%m-%d").strftime("%A")
                good_day  = day_name in self._best_days(best_a11, turno)
            except Exception:
                pass

        # 4) Posiciones y obs dominante aprendidos
        prio_pos   = self._priority_positions(best_a11, turno)
        obs_dom    = self._obs_dominant(best_a11, turno)
        nums_play  = [top12[p - 1] for p in prio_pos if 0 < p <= len(top12)]

        # 5) ¿Jugar top3?
        play_top3 = hr3 >= 0.20 and n12 >= MIN_SAMPLES

        # 6) Decisión
        if nivel == NIVEL_SKIP:
            should_play = False
        elif nivel == NIVEL_APRENDIENDO:
            should_play = good_day   # conservador mientras aprende
        elif nivel in (NIVEL_FUEGO, NIVEL_VERDE):
            should_play = True
        else:  # AMARILLO
            should_play = good_day or hr12 >= 0.30

        # 7) Razón legible
        data_note = (
            f"{int(hr12*100)}% hit real ({n12} muestras)"
            if n12 >= MIN_SAMPLES
            else f"Aprendiendo ({n12} muestras, mín {MIN_SAMPLES})"
        )
        day_tag = (
            f" | {day_name} ✅ día favorable"
            if good_day else (f" | {day_name}" if day_name else "")
        )
        reason = f"A11={best_a11} | {turno} | signal={best_signal:.4f} | bin={sig_bin} → {data_note}{day_tag}"

        return AlertDecision(
            should_play=should_play,
            nivel=nivel,
            hit12_pct=round(hr12 * 100, 1),
            hit3_pct=round(hr3 * 100, 1),
            n_samples=n12,
            play_top3=play_top3,
            priority_positions=prio_pos,
            numbers_to_play=nums_play,
            obs_dominant=obs_dom,
            good_day=good_day,
            day_name=day_name,
            reason=reason,
            signal_bin=sig_bin,
        )

    # ── Estadísticas para log ─────────────────────────────────
    def stats_summary(self) -> dict:
        return {
            "total_samples": self._n_total,
            "overall_hit12": (
                round(sum(r["_hit12"] for r in self._rows) / self._n_total * 100, 1)
                if self._n_total > 0 else 0
            ),
        }


# ── Formateador Telegram ──────────────────────────────────────
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

    # ── No jugar ─────────────────────────────────────────────
    if not decision.should_play:
        samples_note = (
            f"{int(decision.hit12_pct)}% hit real ({decision.n_samples} muestras)"
            if decision.n_samples >= MIN_SAMPLES
            else f"Aprendiendo ({decision.n_samples} muestras)"
        )
        return (
            f"{emoji} <b>[ALERT SYS] LN — {turno_label}</b>\n"
            f"📅 {fecha} | Nivel: <b>{decision.nivel}</b>\n\n"
            f"<b>NO JUGAR</b>\n"
            f"📉 {samples_note}\n\n"
            f"🔍 {decision.reason}\n\n"
            f"🧠 A11: {best_a11} | Signal: {best_signal:.4f} | bin: {decision.signal_bin} | rows: {rows_used}"
        )

    # ── Jugar ─────────────────────────────────────────────────
    pos_lines = []
    for pos in decision.priority_positions[:6]:
        idx = pos - 1
        if 0 <= idx < len(top12):
            pos_lines.append(f"   Pos {pos:02d} → <b>{top12[idx]}</b>")
    pos_block = "\n".join(pos_lines)

    top3_block = ""
    if decision.play_top3:
        top3_block = (
            f"\n🎯 <b>TOP3 también recomendado:</b> {', '.join(top3)}\n"
            f"   📈 {decision.hit3_pct}% hit_top3 real ({decision.n_samples} muestras)\n"
        )

    samples_note = (
        f"{decision.hit12_pct}% hit real ({decision.n_samples} muestras)"
        if decision.n_samples >= MIN_SAMPLES
        else f"Aprendiendo ({decision.n_samples} muestras, mín {MIN_SAMPLES})"
    )

    return (
        f"{emoji} <b>[ALERT SYS] LN — {turno_label}</b>\n"
        f"📅 {fecha} | Nivel: <b>{decision.nivel}</b>\n\n"
        f"▶️ <b>JUGAR — {samples_note}</b>\n\n"
        f"📌 <b>Números a jugar (posiciones prioritarias):</b>\n"
        f"{pos_block}\n"
        f"{top3_block}\n"
        f"📋 <b>Top12 completo:</b> {', '.join(top12)}\n\n"
        f"💡 <b>Espera el</b> <b>{decision.obs_dominant}</b> del resultado oficial\n\n"
        f"🔍 {decision.reason}\n\n"
        f"🧠 A11: {best_a11} | Signal: {best_signal:.4f} | bin: {decision.signal_bin} | rows: {rows_used}"
    )
