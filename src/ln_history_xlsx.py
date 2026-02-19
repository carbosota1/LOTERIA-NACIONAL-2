import xml.etree.ElementTree as ET
from dataclasses import dataclass
from typing import List, Optional, Tuple, Dict
import os

@dataclass
class DrawRow:
    fecha: str      # YYYY-MM-DD
    sorteo: str
    primero: str    # "00"-"99"
    segundo: str
    tercero: str

KEY_FIELDS = ("fecha", "sorteo", "primero", "segundo", "tercero")

def _get_field_from_node(node: ET.Element, name: str) -> Optional[str]:
    # 1) attribute
    if name in node.attrib and node.attrib[name]:
        return node.attrib[name].strip()

    # 2) direct child tag
    child = node.find(name)
    if child is not None and (child.text or "").strip():
        return (child.text or "").strip()

    # 3) search any descendant tag with that name
    for sub in node.iter():
        if sub.tag.lower() == name and (sub.text or "").strip():
            return (sub.text or "").strip()

    return None

def _try_parse_row(node: ET.Element) -> Optional[DrawRow]:
    data: Dict[str, str] = {}
    for f in KEY_FIELDS:
        v = _get_field_from_node(node, f)
        if v:
            data[f] = v

    if not all(k in data for k in KEY_FIELDS):
        return None

    return DrawRow(
        fecha=data["fecha"],
        sorteo=data["sorteo"],
        primero=str(data["primero"]).zfill(2),
        segundo=str(data["segundo"]).zfill(2),
        tercero=str(data["tercero"]).zfill(2),
    )

def read_history_xml(path: str) -> List[DrawRow]:
    if not os.path.exists(path):
        return []
    tree = ET.parse(path)
    root = tree.getroot()

    rows: List[DrawRow] = []
    for node in root.iter():
        row = _try_parse_row(node)
        if row:
            rows.append(row)

    # dedupe by (fecha, sorteo)
    seen = set()
    out = []
    for r in rows:
        k = (r.fecha, r.sorteo)
        if k not in seen:
            seen.add(k)
            out.append(r)
    return out

def write_history_xml(path: str, rows: List[DrawRow]) -> None:
    # Guardamos en un XML simple y estable (sin depender del formato original).
    # Si tú NECESITAS mantener el formato original exacto, me dices y lo respetamos.
    root = ET.Element("history")
    for r in sorted(rows, key=lambda x: (x.fecha, x.sorteo)):
        ET.SubElement(
            root, "draw",
            {
                "fecha": r.fecha,
                "sorteo": r.sorteo,
                "primero": r.primero,
                "segundo": r.segundo,
                "tercero": r.tercero,
            }
        )
    tree = ET.ElementTree(root)
    os.makedirs(os.path.dirname(path), exist_ok=True)
    tree.write(path, encoding="utf-8", xml_declaration=True)

def merge_rows(existing: List[DrawRow], new_rows: List[DrawRow]) -> List[DrawRow]:
    m = {(r.fecha, r.sorteo): r for r in existing}
    for r in new_rows:
        m[(r.fecha, r.sorteo)] = r
    return list(m.values())
