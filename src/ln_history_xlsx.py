from dataclasses import dataclass
from typing import Dict, List, Tuple, Optional
from datetime import datetime, date as dt_date
import os

from openpyxl import load_workbook
from openpyxl.workbook import Workbook

@dataclass
class Row:
    fecha: str
    sorteo: str
    primero: str
    segundo: str
    tercero: str

COLS = ["fecha", "sorteo", "primero", "segundo", "tercero"]

def _z2(x) -> str:
    s = str(x).strip()
    if s == "":
        return ""
    digits = "".join(ch for ch in s if ch.isdigit())
    if digits == "":
        return ""
    return digits.zfill(2)

def _date_to_ymd(x) -> str:
    if isinstance(x, dt_date):
        return x.strftime("%Y-%m-%d")
    s = str(x).strip()
    # si viene tipo "2021-01-06 00:00:00"
    if " " in s:
        s = s.split(" ")[0].strip()
    # validar simple
    datetime.strptime(s, "%Y-%m-%d")
    return s

def _make_key(fecha: str, sorteo: str) -> Tuple[str, str]:
    return (fecha, sorteo.strip())

def read_history_xlsx(path: str, sheet_name: str) -> List[Row]:
    if not os.path.exists(path):
        raise FileNotFoundError(f"No existe el history XLSX: {path}")

    wb = load_workbook(path)
    if sheet_name not in wb.sheetnames:
        raise ValueError(f"No existe la hoja '{sheet_name}' en {path}. Hojas: {wb.sheetnames}")

    ws = wb[sheet_name]
    rows = list(ws.iter_rows(values_only=True))
    if not rows:
        return []

    header = [str(x).strip().lower() if x is not None else "" for x in rows[0]]
    idx = {name: header.index(name) for name in COLS if name in header}
    missing = [c for c in COLS if c not in idx]
    if missing:
        raise ValueError(f"Faltan columnas en XLSX: {missing}. Header detectado: {header}")

    out: List[Row] = []
    for r in rows[1:]:
        if r is None:
            continue
        fecha_raw = r[idx["fecha"]]
        sorteo_raw = r[idx["sorteo"]]
        if fecha_raw is None or sorteo_raw is None:
            continue
        fecha = _date_to_ymd(fecha_raw)
        sorteo = str(sorteo_raw).strip()
        primero = _z2(r[idx["primero"]])
        segundo = _z2(r[idx["segundo"]])
        tercero = _z2(r[idx["tercero"]])
        if not fecha or not sorteo:
            continue
        out.append(Row(fecha, sorteo, primero, segundo, tercero))

    # dedupe por (fecha,sorteo) conservando el último
    m: Dict[Tuple[str,str], Row] = {}
    for rr in out:
        m[_make_key(rr.fecha, rr.sorteo)] = rr
    return list(m.values())

def upsert_rows_xlsx(path: str, sheet_name: str, new_rows: List[Row]) -> int:
    """
    Inserta o actualiza filas por key=(fecha,sorteo).
    Retorna cuántas filas fueron insertadas/actualizadas.
    """
    if not new_rows:
        return 0

    wb = load_workbook(path)
    ws = wb[sheet_name]

    # map header
    rows = list(ws.iter_rows(values_only=False))
    if not rows:
        raise ValueError("La hoja está vacía, no hay header.")

    header = [str(c.value).strip().lower() if c.value is not None else "" for c in rows[0]]
    idx = {name: header.index(name) for name in COLS if name in header}
    missing = [c for c in COLS if c not in idx]
    if missing:
        raise ValueError(f"Faltan columnas en XLSX: {missing}. Header detectado: {header}")

    # index existing
    key_to_rownum: Dict[Tuple[str,str], int] = {}
    for i, r in enumerate(rows[1:], start=2):  # excel row numbers start at 1
        fecha_cell = r[idx["fecha"]].value
        sorteo_cell = r[idx["sorteo"]].value
        if fecha_cell is None or sorteo_cell is None:
            continue
        try:
            fecha = _date_to_ymd(fecha_cell)
        except Exception:
            continue
        sorteo = str(sorteo_cell).strip()
        key_to_rownum[_make_key(fecha, sorteo)] = i

    changed = 0
    for nr in new_rows:
        key = _make_key(nr.fecha, nr.sorteo)
        rownum = key_to_rownum.get(key)

        if rownum is None:
            # append
            rownum = ws.max_row + 1
            key_to_rownum[key] = rownum

        # write values (force as text strings)
        ws.cell(row=rownum, column=idx["fecha"] + 1, value=nr.fecha)
        ws.cell(row=rownum, column=idx["sorteo"] + 1, value=nr.sorteo)

        c1 = ws.cell(row=rownum, column=idx["primero"] + 1, value=_z2(nr.primero))
        c2 = ws.cell(row=rownum, column=idx["segundo"] + 1, value=_z2(nr.segundo))
        c3 = ws.cell(row=rownum, column=idx["tercero"] + 1, value=_z2(nr.tercero))

        # asegurar texto
        c1.number_format = "@"
        c2.number_format = "@"
        c3.number_format = "@"

        changed += 1

    wb.save(path)
    return changed
