import argparse
import csv
import os
from datetime import datetime, timedelta
from typing import List, Tuple, Optional

from config import Settings, TZ_RD, DRAW_GANAMAS, DRAW_NOCHE, LABEL_MAP
from telegram_bot import get_telegram_creds, send_telegram_message
from store import append_csv, now_iso_utc
from ln_history_xlsx import (
    read_history_xlsx,
    upsert_rows_xlsx,
    sanitize_history_xlsx,
    latest_before,
    Row,
)
from model_ln import rank_numbers_from_draws
from performance import score_hits

from ln_scraper import get_result


PICKS_HEADER = [
    "ts_run", "schedule_slot", "target_draw_id", "window_n",
    "top3", "top12",
    "best_signal", "best_a11", "ok_alert", "source_rows_hist_used",
    "same_day_mid_present", "mid_today_nums",
    "debug_json", "model_version"
]
DRAWS_HEADER = ["draw_id", "fecha", "label", "n1", "n2", "n3", "fetched_at", "source"]
PERF_HEADER = [
    "draw_id", "picked_from_ts_run",
    "top3", "top12",
    "observed_n1", "observed_n2", "observed_n3",
    "hits_top3_count", "hits_top12_count", "hit_any_top3", "hit_any_top12", "hit_positions_top12",
    "best_signal", "best_a11", "ok_alert", "source_rows_hist_used"
]


def draw_id(fecha: str, label: str) -> str:
    return f"LN|{fecha}|{label}"


def safe_date_from_arg(date_str: str) -> str:
    date_str = (date_str or "").strip()
    if not date_str:
        return datetime.now(TZ_RD).date().strftime("%Y-%m-%d")
    datetime.strptime(date_str, "%Y-%m-%d")
    return date_str


def _today_ymd() -> str:
    return datetime.now(TZ_RD).date().strftime("%Y-%m-%d")


def try_get_result(draw_title: str, fecha: str) -> Optional[Tuple[str, str, str]]:
    try:
        return get_result(draw_title, fecha)
    except ValueError as e:
        msg = str(e).lower()
        if "aún no publicado" in msg or "resultado aún no publicado" in msg:
            return None
        if "no encontré el sorteo" in msg:
            return None
        raise


def csv_has_row(path: str, match: dict) -> bool:
    if not os.path.exists(path):
        return False
    with open(path, "r", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        for row in reader:
            ok = True
            for k, v in match.items():
                if row.get(k, "") != str(v):
                    ok = False
                    break
            if ok:
                return True
    return False


def pick_already_logged(target_draw_id: str, schedule_slot: str) -> bool:
    return csv_has_row("data/picks_log.csv", {
        "target_draw_id": target_draw_id,
        "schedule_slot": schedule_slot,
    })


def draw_already_logged(draw_id_value: str) -> bool:
    return csv_has_row("data/draws_log.csv", {"draw_id": draw_id_value})


def perf_already_logged(draw_id_value: str, picked_from_ts_run: str) -> bool:
    return csv_has_row("data/performance_log.csv", {
        "draw_id": draw_id_value,
        "picked_from_ts_run": picked_from_ts_run,
    })


def is_phantom_holiday_repeat(history: List[Row], sorteo: str, fecha: str, nums: Tuple[str, str, str]) -> bool:
    """
    Si el resultado de 'fecha' es EXACTAMENTE igual al último día anterior (normalmente ayer),
    lo tratamos como feriado/repetición fantasma y NO lo guardamos.
    """
    prev = latest_before(history, sorteo, fecha)
    if not prev:
        return False

    # si la fecha previa es justamente el día anterior, y el resultado es idéntico => feriado/repetición
    try:
        prev_d = datetime.strptime(prev.fecha, "%Y-%m-%d").date()
        cur_d = datetime.strptime(fecha, "%Y-%m-%d").date()
    except Exception:
        return False

    if (cur_d - prev_d).days == 1 and (prev.primero, prev.segundo, prev.tercero) == nums:
        return True

    return False


def sync_for_date(s: Settings, fecha: str, history_current: List[Row]) -> List[Row]:
    """
    Ejecuta scraper para MID/NIGHT en una fecha y upsert en XLSX master.
    BLOQUEA:
      - fechas futuras
      - resultados feriado/repetidos (fantasmas)
    """
    # bloquear fechas futuras
    today = datetime.now(TZ_RD).date()
    d = datetime.strptime(fecha, "%Y-%m-%d").date()
    if d > today:
        return []

    new_rows: List[Row] = []

    mid = try_get_result(DRAW_GANAMAS, fecha)
    if mid and not is_phantom_holiday_repeat(history_current, DRAW_GANAMAS, fecha, mid):
        new_rows.append(Row(fecha, DRAW_GANAMAS, mid[0], mid[1], mid[2]))

    night = try_get_result(DRAW_NOCHE, fecha)
    if night and not is_phantom_holiday_repeat(history_current, DRAW_NOCHE, fecha, night):
        new_rows.append(Row(fecha, DRAW_NOCHE, night[0], night[1], night[2]))

    if new_rows:
        upsert_rows_xlsx(s.history_xlsx_path, s.history_sheet_name, new_rows)

    return new_rows


def log_new_draws(new_rows: List[Row]) -> None:
    for r in new_rows:
        label = LABEL_MAP.get(r.sorteo, "")
        if not label:
            continue
        did = draw_id(r.fecha, label)
        if draw_already_logged(did):
            continue
        append_csv("data/draws_log.csv", {
            "draw_id": did,
            "fecha": r.fecha,
            "label": label,
            "n1": r.primero,
            "n2": r.segundo,
            "n3": r.tercero,
            "fetched_at": now_iso_utc(),
            "source": "loteriadominicana.com.do"
        }, DRAWS_HEADER)


def decide_target_live(fecha: str) -> Tuple[str, str, str, Optional[Tuple[str, str, str]]]:
    """
    Decide target basado en lo publicado EN VIVO (scraper), no en lo que diga el XLSX.
    - Si MID no está publicado: target MID
    - Si MID publicado y NIGHT no: target NIGHT + mid_today
    - Si ambos publicados: DONE
    """
    mid_live = try_get_result(DRAW_GANAMAS, fecha)
    if mid_live is None:
        return ("MID", DRAW_GANAMAS, "Gana Más", None)

    night_live = try_get_result(DRAW_NOCHE, fecha)
    if night_live is None:
        return ("NIGHT", DRAW_NOCHE, "Noche", mid_live)

    return ("DONE", "", "DONE", mid_live)


def run_picks(history: List[Row], fecha: str, slot: str):
    s = Settings()
    token, chat_id = get_telegram_creds(s.telegram_bot_token_env, s.telegram_chat_id_env)

    target_label, target_sorteo, title, mid_today = decide_target_live(fecha)

    if target_label == "DONE":
        send_telegram_message(f"✅ LN: Ya salieron Gana Más y Noche hoy ({fecha}). NO_EVENT.", token, chat_id)
        return

    target_id = draw_id(fecha, target_label)

    # ✅ no duplicar picks
    if pick_already_logged(target_id, slot):
        return

    draws: List[Tuple[str, str, str]] = [(r.primero, r.segundo, r.tercero) for r in history if r.sorteo == target_sorteo]
    if len(draws) < 50:
        send_telegram_message(f"⚠️ LN {title}: historial insuficiente ({len(draws)} filas).", token, chat_id)
        return

    try:
        out = rank_numbers_from_draws(draws, window_n=s.window_n)
    except Exception as e:
        send_telegram_message(f"⚠️ LN {title}: error modelo: {e}", token, chat_id)
        return

    same_day_mid_present = mid_today is not None
    mid_today_nums = ",".join(mid_today) if mid_today else ""

    row = {
        "ts_run": now_iso_utc(),
        "schedule_slot": slot,
        "target_draw_id": target_id,
        "window_n": s.window_n,
        "top3": ",".join(out.top3),
        "top12": ",".join(out.top12),
        "best_signal": out.best_signal,
        "best_a11": out.best_a11,
        "ok_alert": int(out.ok_alert),
        "source_rows_hist_used": min(len(draws), s.window_n),
        "same_day_mid_present": int(same_day_mid_present),
        "mid_today_nums": mid_today_nums,
        "debug_json": str(out.debug),
        "model_version": "LN-quiniela-v1",
    }

    append_csv("data/picks_log.csv", row, PICKS_HEADER)

    msg = (
        f"🚨 <b>LN QUINIELA</b>\n"
        f"📅 {fecha} | 🎯 {title} | ⏰ Slot {slot}\n\n"
        f"✅ <b>Top3</b>: {', '.join(out.top3)}\n"
        f"📌 <b>Top12</b>: {', '.join(out.top12)}\n\n"
        f"🧩 same_day_mid_present: {same_day_mid_present}\n"
        f"🧠 best_signal: {out.best_signal:.6f} | a11: {out.best_a11} | alert: {out.ok_alert}\n"
        f"📊 rows_used: {min(len(draws), s.window_n)}\n"
    )
    send_telegram_message(msg, token, chat_id)


def run_performance(history: List[Row]):
    picks_path = "data/picks_log.csv"
    if not os.path.exists(picks_path):
        return

    results = {}
    for r in history:
        label = LABEL_MAP.get(r.sorteo, "")
        if not label:
            continue
        results[draw_id(r.fecha, label)] = (r.primero, r.segundo, r.tercero)

    with open(picks_path, "r", encoding="utf-8") as f:
        picks = list(csv.DictReader(f))

    for p in picks:
        did = p.get("target_draw_id", "")
        ts_run = p.get("ts_run", "")
        if not did or not ts_run:
            continue
        if did not in results:
            continue

        if perf_already_logged(did, ts_run):
            continue

        observed = results[did]
        top3 = p["top3"].split(",") if p.get("top3") else []
        top12 = p["top12"].split(",") if p.get("top12") else []

        stats = score_hits(top3, top12, observed)

        row = {
            "draw_id": did,
            "picked_from_ts_run": ts_run,
            "top3": p.get("top3", ""),
            "top12": p.get("top12", ""),
            "observed_n1": observed[0],
            "observed_n2": observed[1],
            "observed_n3": observed[2],
            **stats,
            "best_signal": p.get("best_signal", ""),
            "best_a11": p.get("best_a11", ""),
            "ok_alert": p.get("ok_alert", ""),
            "source_rows_hist_used": p.get("source_rows_hist_used", ""),
        }
        append_csv("data/performance_log.csv", row, PERF_HEADER)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--mode", choices=["picks", "check", "sync"], required=True)
    ap.add_argument("--slot", default="")
    ap.add_argument("--date", default="")  # opcional YYYY-MM-DD
    args = ap.parse_args()

    s = Settings()

    # ✅ Determinar fecha objetivo
    fecha = safe_date_from_arg(args.date)

    # ✅ 1) SANITIZE primero (quita futuros + feriados repetidos)
    today_ymd = _today_ymd()
    sanitize_history_xlsx(s.history_xlsx_path, s.history_sheet_name, today_ymd)

    # cargar history limpio
    history = read_history_xlsx(s.history_xlsx_path, s.history_sheet_name)

    # ✅ 2) SYNC HOY (y en sync también AYER) pero bloqueando fantasmas/feriados
    new_today = sync_for_date(s, fecha, history)
    if new_today:
        # recargar history si hubo cambios
        history = read_history_xlsx(s.history_xlsx_path, s.history_sheet_name)
        log_new_draws(new_today)

    if args.mode == "sync":
        ayer = (datetime.strptime(fecha, "%Y-%m-%d").date() - timedelta(days=1)).strftime("%Y-%m-%d")
        new_y = sync_for_date(s, ayer, history)
        if new_y:
            history = read_history_xlsx(s.history_xlsx_path, s.history_sheet_name)
            log_new_draws(new_y)
        run_performance(history)
        return

    if args.mode == "check":
        run_performance(history)
        return

    if args.mode == "picks":
        run_picks(history, fecha, args.slot or "manual")
        return


if __name__ == "__main__":
    main()
