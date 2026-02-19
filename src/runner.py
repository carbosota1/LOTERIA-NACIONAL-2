import argparse
from datetime import datetime, date as dt_date, timedelta
from zoneinfo import ZoneInfo

from config import Settings, TZ_RD, DRAW_GANAMAS, DRAW_NOCHE
from telegram_bot import get_telegram_creds, send_telegram_message
from store import append_csv, load_state, save_state, now_iso
from ln_history_xml import read_history_xml, write_history_xml, merge_rows, DrawRow
from model_ln import rank_numbers_from_draws
from performance import score_hits

# Tu scraper: pégalo en src/ln_scraper.py y se importa aquí
from ln_scraper import get_result  # tu función actual

PICKS_HEADER = [
    "ts_run","schedule_slot","target_draw_id","window_n",
    "top3","top12",
    "best_signal","best_a11","ok_alert","source_rows_hist_used",
    "same_day_mid_present","mid_today_nums",
    "model_version","debug_json"
]
DRAWS_HEADER = ["draw_id","fecha","label","n1","n2","n3","fetched_at","source"]
PERF_HEADER = [
    "draw_id","picked_from_ts_run",
    "top3","top12",
    "observed_n1","observed_n2","observed_n3",
    "hits_top3_count","hits_top12_count","hit_any_top3","hit_any_top12","hit_positions_top12",
    "best_signal","best_a11","ok_alert","source_rows_hist_used"
]

def draw_id(fecha: str, label: str) -> str:
    return f"LN|{fecha}|{label}"

def try_get_result(draw_title: str, fecha: str):
    try:
        return get_result(draw_title, fecha)
    except ValueError as e:
        msg = str(e).lower()
        if "aún no publicado" in msg or "resultado aún no publicado" in msg:
            return None
        # si no encontró el sorteo en la página también puede pasar en días raros
        if "no encontré el sorteo" in msg:
            return None
        raise

def sync_day(history_xml_path: str, fecha: str) -> list[DrawRow]:
    # trae resultados disponibles (MID/NIGHT) y devuelve filas nuevas
    new_rows = []
    mid = try_get_result(DRAW_GANAMAS, fecha)
    if mid:
        new_rows.append(DrawRow(fecha, DRAW_GANAMAS, mid[0], mid[1], mid[2]))

    night = try_get_result(DRAW_NOCHE, fecha)
    if night:
        new_rows.append(DrawRow(fecha, DRAW_NOCHE, night[0], night[1], night[2]))

    return new_rows

def pick_target_label(rows_today):
    # rows_today: dict label -> observed tuple
    if rows_today.get("MID") is None:
        return "MID"
    if rows_today.get("NIGHT") is None:
        return "NIGHT"
    return "DONE"

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--mode", choices=["picks","check","sync"], required=True)
    ap.add_argument("--slot", default="")
    ap.add_argument("--date", default="")  # opcional YYYY-MM-DD para backfills
    args = ap.parse_args()

    s = Settings()
    state_path = "data/state.json"

    today = datetime.now(TZ_RD).date()
    fecha = args.date.strip() or today.strftime("%Y-%m-%d")

    # 1) Siempre cargamos history
    existing = read_history_xml(s.history_xml_path)

    # 2) En picks/check/sync hacemos sync de HOY (y en sync también AYER por seguridad)
    new_rows = []
    new_rows += sync_day(s.history_xml_path, fecha)

    if args.mode == "sync":
        ayer = (datetime.strptime(fecha, "%Y-%m-%d").date() - timedelta(days=1)).strftime("%Y-%m-%d")
        new_rows += sync_day(s.history_xml_path, ayer)

    if new_rows:
        merged = merge_rows(existing, new_rows)
        # guardamos en XML normalizado (si quieres preservar tu formato exacto, lo ajusto)
        write_history_xml(s.history_xml_path, merged)
        existing = merged

    # Export mínimo a draws_log.csv (solo lo nuevo)
    for r in new_rows:
        label = "MID" if r.sorteo == DRAW_GANAMAS else "NIGHT"
        append_csv("data/draws_log.csv", {
            "draw_id": draw_id(r.fecha, label),
            "fecha": r.fecha,
            "label": label,
            "n1": r.primero,
            "n2": r.segundo,
            "n3": r.tercero,
            "fetched_at": now_iso(),
            "source": "loteriadominicana.com.do"
        }, DRAWS_HEADER)

    if args.mode == "sync":
        # cierre diario: además intenta calcular performance de todo lo que ya tenga resultado
        run_performance(existing)
        return

    if args.mode == "check":
        run_performance(existing)
        return

    if args.mode == "picks":
        run_picks(existing, args.slot, fecha)
        return

def run_picks(history_rows, slot: str, fecha: str):
    s = Settings()
    token, chat_id = get_telegram_creds(s.telegram_bot_token_env, s.telegram_chat_id_env)

    # detectar qué salió hoy
    mid_row = next((r for r in history_rows if r.fecha == fecha and r.sorteo == DRAW_GANAMAS), None)
    night_row = next((r for r in history_rows if r.fecha == fecha and r.sorteo == DRAW_NOCHE), None)

    rows_today = {
        "MID": (mid_row.primero, mid_row.segundo, mid_row.tercero) if mid_row else None,
        "NIGHT": (night_row.primero, night_row.segundo, night_row.tercero) if night_row else None,
    }

    target = pick_target_label(rows_today)
    if target == "DONE":
        send_telegram_message(f"✅ LN: Ya salieron MID y NIGHT hoy ({fecha}). NO_EVENT.", token, chat_id)
        return

    target_draw_id = f"LN|{fecha}|{target}"

    # armar lista cronológica de draws SOLO del sorteo target (MID o NIGHT) o ambos?
    # Para quiniela, lo más coherente es entrenar por label (MID con MID, NIGHT con NIGHT).
    target_sorteo = DRAW_GANAMAS if target == "MID" else DRAW_NOCHE
    draws = [(r.primero, r.segundo, r.tercero) for r in history_rows if r.sorteo == target_sorteo]
    if len(draws) < 50:
        send_telegram_message(f"⚠️ LN {target}: historial insuficiente ({len(draws)} filas).", token, chat_id)
        return

    out = rank_numbers_from_draws(draws, window_n=s.window_n)

    # Señales placeholders (si tú ya tienes fórmula best_signal/a11, aquí se conecta)
    best_signal = 0.0
    best_a11 = 0
    ok_alert = False
    source_rows = min(len(draws), s.window_n)

    same_day_mid_present = (rows_today["MID"] is not None)
    mid_today_nums = ",".join(rows_today["MID"]) if rows_today["MID"] else ""

    row = {
        "ts_run": now_iso(),
        "schedule_slot": slot,
        "target_draw_id": target_draw_id,
        "window_n": s.window_n,
        "top3": ",".join(out.top3),
        "top12": ",".join(out.top12),
        "best_signal": best_signal,
        "best_a11": best_a11,
        "ok_alert": int(ok_alert),
        "source_rows_hist_used": source_rows,
        "same_day_mid_present": int(same_day_mid_present),
        "mid_today_nums": mid_today_nums,
        "model_version": "LN-quiniela-v1",
        "debug_json": str(out.debug),
    }

    append_csv("data/picks_log.csv", row, PICKS_HEADER)

    # Mensaje Telegram
    title = "Gana Más" if target == "MID" else "Noche"
    msg = (
        f"🚨 <b>LN QUINIELA</b>\n"
        f"📅 {fecha} | 🎯 {title} | ⏰ Slot {slot}\n\n"
        f"✅ <b>Top3</b>: {', '.join(out.top3)}\n"
        f"📌 <b>Top12</b>: {', '.join(out.top12)}\n\n"
        f"🧩 same_day_mid_present: {same_day_mid_present}\n"
        f"📊 rows_used: {source_rows}\n"
    )
    send_telegram_message(msg, token, chat_id)

def run_performance(history_rows):
    # Busca resultados ya existentes y cruza contra picks_log
    # (Aquí dejamos listo el pipeline; si quieres, migramos a SQLite para joins más fáciles.)
    import csv, os

    picks_path = "data/picks_log.csv"
    perf_path = "data/performance_log.csv"

    if not os.path.exists(picks_path):
        return

    # Cargar picks
    with open(picks_path, "r", encoding="utf-8") as f:
        picks = list(csv.DictReader(f))

    # Indexar resultados por draw_id
    results = {}
    for r in history_rows:
        label = "MID" if r.sorteo == DRAW_GANAMAS else "NIGHT"
        did = draw_id(r.fecha, label)
        results[did] = (r.primero, r.segundo, r.tercero)

    # Dedupe: no repetir performance si ya existe
    existing_perf_keys = set()
    if os.path.exists(perf_path):
        with open(perf_path, "r", encoding="utf-8") as f:
            for row in csv.DictReader(f):
                existing_perf_keys.add((row["draw_id"], row["picked_from_ts_run"]))

    for p in picks:
        did = p["target_draw_id"]
        if did not in results:
            continue

        key = (did, p["ts_run"])
        if key in existing_perf_keys:
            continue

        observed = results[did]
        top3 = p["top3"].split(",") if p["top3"] else []
        top12 = p["top12"].split(",") if p["top12"] else []

        stats = score_hits(top3, top12, observed)

        row = {
            "draw_id": did,
            "picked_from_ts_run": p["ts_run"],
            "top3": p["top3"],
            "top12": p["top12"],
            "observed_n1": observed[0],
            "observed_n2": observed[1],
            "observed_n3": observed[2],
            **stats,
            "best_signal": p.get("best_signal",""),
            "best_a11": p.get("best_a11",""),
            "ok_alert": p.get("ok_alert",""),
            "source_rows_hist_used": p.get("source_rows_hist_used",""),
        }
        append_csv(perf_path, row, PERF_HEADER)

if __name__ == "__main__":
    main()
