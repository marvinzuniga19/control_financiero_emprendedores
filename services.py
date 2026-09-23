from __future__ import annotations

import csv
from datetime import datetime
from pathlib import Path


MONTHS = {
    "Todo el año": None,
    "Enero": 1,
    "Febrero": 2,
    "Marzo": 3,
    "Abril": 4,
    "Mayo": 5,
    "Junio": 6,
    "Julio": 7,
    "Agosto": 8,
    "Septiembre": 9,
    "Octubre": 10,
    "Noviembre": 11,
    "Diciembre": 12,
}
MONTH_NAMES = list(MONTHS.keys())[1:]


def currency(value: float) -> str:
    return f"C$ {value:,.2f}"


def parse_positive_amount(value: str) -> float:
    normalized = value.strip().replace("C$", "").replace(",", "")
    amount = float(normalized)
    if amount <= 0:
        raise ValueError("El monto debe ser mayor que cero.")
    return round(amount, 2)


def parse_nonnegative_amount(value: str) -> float:
    normalized = value.strip().replace("C$", "").replace(",", "")
    amount = float(normalized)
    if amount < 0:
        raise ValueError("El monto no puede ser negativo.")
    return round(amount, 2)


def validate_iso_date(value: str) -> str:
    try:
        return datetime.strptime(value.strip(), "%Y-%m-%d").date().isoformat()
    except ValueError as exc:
        raise ValueError("La fecha debe tener el formato AAAA-MM-DD.") from exc


def export_transactions_csv(rows, path: str | Path) -> None:
    headers = ["ID", "Fecha", "Tipo", "Categoría", "Descripción", "Método", "Monto C$", "Cliente / Proveedor", "Notas"]
    with Path(path).open("w", newline="", encoding="utf-8-sig") as stream:
        writer = csv.writer(stream)
        writer.writerow(headers)
        for row in rows:
            writer.writerow([row["id"], row["date"], row["type"], row["category"], row["description"], row["payment_method"], row["amount"], row["party"], row["notes"]])
