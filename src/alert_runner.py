# ============================================================
# FILE: src/alert_runner.py
# LN ALERT SYSTEM — Runner con motor dinámico
# ============================================================
import argparse
import csv
import os
from datetime import datetime, timedelta, time
from typing import List, Tuple, Optional

from alert_config import (
    AlertSettings, TZ_RD,
    DRAW_GANAMAS, DRAW_NOCHE, LABEL_MAP,
    MID_PUBLISH_HOUR, MID_PUBLISH_MIN,
    NIGHT_PUBLISH_HOUR, NIGHT_PUBLISH_MIN,
    PUBLISH_BUFFER_MIN,
)
from alert_engine import DynamicAlertEngine, build_message

from telegram_bot import get_telegram_creds, send_telegram_message
from store import append_csv, now_iso_utc
from ln_history_xlsx import read_history_xlsx, Row
from model_ln import rank_numbers_from_draws
from performance import score_hits
from ln_scraper import get_result


ALERT_PICKS_HEADER = [
    "ts_run", "schedule_slot", "target_draw_id",
    "top3", "top12",
    "best_signal", "best_a11", "ok_alert",
    "nivel_alerta", "should_play", "hit12_pct", "n_samples",
    "signal_bin", "priority_positions", "numbers_to_play",
    "obs_dominant", "good_day", "rows_used", "model_version",
]

ALERT_PERF_HEADER = [
    "draw_id", "picked_from_ts_run",
    "top3", "top12",
    "observed_n1", "observed_n2", "observed_n3",
    "hits_top3_count", "hits_top12_count",
    "hit_any_top3", "hit_any_top12", "hit_positions_top12",
    "best_signal", "best_a11", "ok_alert",
    "nivel_alerta", "should_play",
]


def _draw_id(fecha: str, label: str) -> str:
    return f"LN|{fecha}|{label}"

def _today_ymd() -> str:
    return datetime.now(TZ_RD).date().strftime("%Y-%m-%d")

def _safe_date(date_str: str) -> str:
    date_str = (date_str or "").strip()
    if not date_str:
        return _today_ymd()
    datetime.strptime(date_str, "%Y-%m-%d")
    return date_str

def _ready_by_time(draw_title: str, fecha: str) -> bool:
    today = datetime.now(TZ_RD).date()
    d = datetime.strptime(fecha, "%Y-%m-%d").date()
    if d != today:
        return True
    now = datetime.now(TZ_RD)
    buf = timedelta(minutes=PUBLISH_BUFFER_MIN)
    if draw_title == DRAW_GANAMAS:
        pub = datetime.combine(today, time(MID_PUBLISH_HOUR, MID_PUBLISH_MIN), tzinfo=TZ_RD) + buf
        return now >= pub
    if draw_title == DRAW_NOCHE:
        pub = datetime.combine(today, time(NIGHT_PUBLISH_HOUR, NIGHT_PUBLISH_MIN), tzinfo=TZ_RD) + buf
        return now >= pub
    return True

def _try_get_result(draw_title: str, fecha: str):
    if not _ready_by_time(draw_title, fecha):
        return None
    try:
        return get_result(draw_title, fecha)
    except ValueError as e:
        msg = str(e).lower()
        if "aún no publicado" in msg or "no encontré" in msg:
            return None
        raise

def _csv_has_row(path: str, match: dict) -> bool:
    if not os.path.exists(path):
        return False
    with open(path, "r", encoding="utf-8") as f:
        for row in csv.DictReader(f):
            if all(row.get(k, "") == str(v) for k, v in match.items()):
                return True
    return False

def _decide_target(fecha: str):
    mid = _try_get_result(DRAW_GANAMAS, fecha)
    if mid is None:
        return ("MID", DRAW_GANAMAS, None)
    night = _try_get_result(DRAW_NOCHE, fecha)
    if night is None:
        return ("NIGHT", DRAW_NOCHE, mid)
    return ("DONE", "", mid)


def run_picks(s: AlertSettings, fecha: str, slot: str) -> None:
    token, chat_id = get_telegram_creds(s.telegram_bot_token_env, s.telegram_chat_id_env)

    target_label, target_sorteo, mid_today = _decide_target(fecha)
    if target_label == "DONE":
        return

    target_id = _draw_id(fecha, target_label)
    if _csv_has_row(s.picks_log_path, {"target_draw_id": target_id}):
        return

    history = read_history_xlsx(s.history_xlsx_path, s.history_sheet_name)
    draws: List[Tuple[str, str, str]] = [
        (r.primero, r.segundo, r.tercero)
        for r in history if r.sorteo == target_sorteo
    ]

    if len(draws) < 50:
        send_telegram_message(
            f"⚠️ [ALERT SYS] Historial insuficiente ({len(draws)} filas).",
            token, chat_id,
        )
        return

    try:
        if target_label == "NIGHT" and mid_today:
            out = rank_numbers_from_draws(draws, window_n=s.window_n, mid_today=mid_today)
        else:
            out = rank_numbers_from_draws(draws, window_n=s.window_n)
    except Exception as e:
        send_telegram_message(f"⚠️ [ALERT SYS] Error modelo: {e}", token, chat_id)
        return

    rows_used = (
        out.debug.get("window_used", min(len(draws), s.window_n))
        if isinstance(out.debug, dict)
        else min(len(draws), s.window_n)
    )

    # ── Motor dinámico ────────────────────────────────────────
    engine   = DynamicAlertEngine(s.perf_log_path)
    decision = engine.evaluate(
        best_a11=out.best_a11,
        best_signal=out.best_signal,
        ok_alert=out.ok_alert,
        turno=target_label,
        top12=out.top12,
        top3=out.top3,
        fecha=fecha,
    )

    # ── Log CSV ───────────────────────────────────────────────
    append_csv(s.picks_log_path, {
        "ts_run":             now_iso_utc(),
        "schedule_slot":      slot,
        "target_draw_id":     target_id,
        "top3":               ",".join(out.top3),
        "top12":              ",".join(out.top12),
        "best_signal":        out.best_signal,
        "best_a11":           out.best_a11,
        "ok_alert":           int(out.ok_alert),
        "nivel_alerta":       decision.nivel,
        "should_play":        int(decision.should_play),
        "hit12_pct":          decision.hit12_pct,
        "n_samples":          decision.n_samples,
        "signal_bin":         decision.signal_bin,
        "priority_positions": ",".join(map(str, decision.priority_positions)),
        "numbers_to_play":    ",".join(decision.numbers_to_play),
        "obs_dominant":       decision.obs_dominant,
        "good_day":           int(decision.good_day),
        "rows_used":          rows_used,
        "model_version":      "LN-alert-v2-dynamic",
    }, ALERT_PICKS_HEADER)

    # ── Telegram ──────────────────────────────────────────────
    msg = build_message(
        decision=decision,
        fecha=fecha,
        turno=target_label,
        best_a11=out.best_a11,
        best_signal=out.best_signal,
        top12=out.top12,
        top3=out.top3,
        rows_used=rows_used,
    )
    send_telegram_message(msg, token, chat_id)


def run_performance(s: AlertSettings) -> None:
    if not os.path.exists(s.picks_log_path):
        return

    history = read_history_xlsx(s.history_xlsx_path, s.history_sheet_name)
    results = {}
    for r in history:
        label = LABEL_MAP.get(r.sorteo, "")
        if label:
            results[_draw_id(r.fecha, label)] = (r.primero, r.segundo, r.tercero)

    with open(s.picks_log_path, "r", encoding="utf-8") as f:
        picks = list(csv.DictReader(f))

    for p in picks:
        did    = p.get("target_draw_id", "")
        ts_run = p.get("ts_run", "")
        if not did or not ts_run or did not in results:
            continue
        if _csv_has_row(s.perf_log_path, {"draw_id": did, "picked_from_ts_run": ts_run}):
            continue

        observed = results[did]
        top3     = p["top3"].split(",")  if p.get("top3")  else []
        top12    = p["top12"].split(",") if p.get("top12") else []
        stats    = score_hits(top3, top12, observed)

        append_csv(s.perf_log_path, {
            "draw_id":            did,
            "picked_from_ts_run": ts_run,
            "top3":               p.get("top3", ""),
            "top12":              p.get("top12", ""),
            "observed_n1":        observed[0],
            "observed_n2":        observed[1],
            "observed_n3":        observed[2],
            **stats,
            "best_signal":        p.get("best_signal", ""),
            "best_a11":           p.get("best_a11", ""),
            "ok_alert":           p.get("ok_alert", ""),
            "nivel_alerta":       p.get("nivel_alerta", ""),
            "should_play":        p.get("should_play", ""),
        }, ALERT_PERF_HEADER)


def run_sync(s: AlertSettings, fecha: str) -> None:
    run_performance(s)


def main() -> None:
    ap = argparse.ArgumentParser(description="LN Alert System v2 Dynamic")
    ap.add_argument("--mode", choices=["picks", "check", "sync"], required=True)
    ap.add_argument("--slot", default="manual")
    ap.add_argument("--date", default="")
    args = ap.parse_args()

    s     = AlertSettings()
    fecha = _safe_date(args.date)

    if args.mode == "picks":
        run_picks(s, fecha, args.slot)
    elif args.mode == "check":
        run_performance(s)
    elif args.mode == "sync":
        run_sync(s, fecha)


if __name__ == "__main__":
    main()
