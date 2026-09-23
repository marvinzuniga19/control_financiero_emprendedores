from __future__ import annotations

import sqlite3
from contextlib import contextmanager
from pathlib import Path
from typing import Iterator


APP_DIR = Path(__file__).resolve().parent
DATA_DIR = APP_DIR / "data"
DB_PATH = DATA_DIR / "control_financiero.db"

DEFAULT_INCOME_CATEGORIES = ["Ventas", "Servicios", "Pedidos personalizados", "Comisiones", "Otros ingresos"]
DEFAULT_EXPENSE_CATEGORIES = ["Materiales", "Publicidad", "Transporte", "Servicios básicos", "Alquiler", "Comisiones", "Impuestos", "Otros gastos"]
DEFAULT_PAYMENT_METHODS = ["Efectivo", "Transferencia", "Tarjeta", "Otro"]


class Database:
    def __init__(self, path: Path | str = DB_PATH) -> None:
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.initialize()

    @contextmanager
    def connect(self) -> Iterator[sqlite3.Connection]:
        connection = sqlite3.connect(self.path)
        connection.row_factory = sqlite3.Row
        connection.execute("PRAGMA foreign_keys = ON")
        try:
            yield connection
            connection.commit()
        finally:
            connection.close()

    def initialize(self) -> None:
        with self.connect() as con:
            con.executescript(
                """
                CREATE TABLE IF NOT EXISTS settings (
                    key TEXT PRIMARY KEY,
                    value TEXT NOT NULL
                );

                CREATE TABLE IF NOT EXISTS categories (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    name TEXT NOT NULL,
                    type TEXT NOT NULL CHECK(type IN ('Ingreso', 'Gasto')),
                    UNIQUE(name, type)
                );

                CREATE TABLE IF NOT EXISTS payment_methods (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    name TEXT NOT NULL UNIQUE
                );

                CREATE TABLE IF NOT EXISTS transactions (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    date TEXT NOT NULL,
                    type TEXT NOT NULL CHECK(type IN ('Ingreso', 'Gasto')),
                    category TEXT NOT NULL,
                    description TEXT NOT NULL,
                    payment_method TEXT NOT NULL,
                    amount REAL NOT NULL CHECK(amount > 0),
                    party TEXT DEFAULT '',
                    notes TEXT DEFAULT '',
                    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
                );

                CREATE INDEX IF NOT EXISTS idx_transactions_date ON transactions(date);
                CREATE INDEX IF NOT EXISTS idx_transactions_type ON transactions(type);
                CREATE INDEX IF NOT EXISTS idx_transactions_category ON transactions(category);
                """
            )
            defaults = {
                "business_name": "Mi Negocio",
                "initial_balance": "18350.00",
                "income_goal": "36700.00",
                "expense_limit": "14680.00",
                "analysis_year": "2026",
            }
            con.executemany("INSERT OR IGNORE INTO settings(key, value) VALUES (?, ?)", defaults.items())
            con.executemany("INSERT OR IGNORE INTO categories(name, type) VALUES (?, 'Ingreso')", [(x,) for x in DEFAULT_INCOME_CATEGORIES])
            con.executemany("INSERT OR IGNORE INTO categories(name, type) VALUES (?, 'Gasto')", [(x,) for x in DEFAULT_EXPENSE_CATEGORIES])
            con.executemany("INSERT OR IGNORE INTO payment_methods(name) VALUES (?)", [(x,) for x in DEFAULT_PAYMENT_METHODS])

    def get_settings(self) -> dict[str, str]:
        with self.connect() as con:
            return {row["key"]: row["value"] for row in con.execute("SELECT key, value FROM settings")}

    def update_settings(self, values: dict[str, str]) -> None:
        with self.connect() as con:
            con.executemany(
                "INSERT INTO settings(key, value) VALUES (?, ?) ON CONFLICT(key) DO UPDATE SET value=excluded.value",
                values.items(),
            )

    def categories(self, transaction_type: str | None = None) -> list[str]:
        query = "SELECT name FROM categories"
        params: tuple[str, ...] = ()
        if transaction_type:
            query += " WHERE type = ?"
            params = (transaction_type,)
        query += " ORDER BY name"
        with self.connect() as con:
            return [row["name"] for row in con.execute(query, params)]

    def add_category(self, name: str, transaction_type: str) -> None:
        with self.connect() as con:
            con.execute("INSERT INTO categories(name, type) VALUES (?, ?)", (name.strip(), transaction_type))

    def delete_category(self, name: str, transaction_type: str) -> None:
        with self.connect() as con:
            con.execute("DELETE FROM categories WHERE name = ? AND type = ?", (name, transaction_type))

    def payment_methods(self) -> list[str]:
        with self.connect() as con:
            return [row["name"] for row in con.execute("SELECT name FROM payment_methods ORDER BY name")]

    def add_payment_method(self, name: str) -> None:
        with self.connect() as con:
            con.execute("INSERT INTO payment_methods(name) VALUES (?)", (name.strip(),))

    def delete_payment_method(self, name: str) -> None:
        with self.connect() as con:
            con.execute("DELETE FROM payment_methods WHERE name = ?", (name,))

    def add_transaction(self, data: dict) -> int:
        with self.connect() as con:
            cursor = con.execute(
                """INSERT INTO transactions(date, type, category, description, payment_method, amount, party, notes)
                   VALUES (:date, :type, :category, :description, :payment_method, :amount, :party, :notes)""",
                data,
            )
            return int(cursor.lastrowid)

    def update_transaction(self, transaction_id: int, data: dict) -> None:
        payload = dict(data)
        payload["id"] = transaction_id
        with self.connect() as con:
            con.execute(
                """UPDATE transactions SET date=:date, type=:type, category=:category,
                   description=:description, payment_method=:payment_method, amount=:amount,
                   party=:party, notes=:notes WHERE id=:id""",
                payload,
            )

    def delete_transaction(self, transaction_id: int) -> None:
        with self.connect() as con:
            con.execute("DELETE FROM transactions WHERE id = ?", (transaction_id,))

    def transactions(self, year: int | None = None, month: int | None = None, search: str = "") -> list[sqlite3.Row]:
        clauses, params = [], []
        if year:
            clauses.append("strftime('%Y', date) = ?")
            params.append(str(year))
        if month:
            clauses.append("strftime('%m', date) = ?")
            params.append(f"{month:02d}")
        if search.strip():
            clauses.append("(description LIKE ? OR category LIKE ? OR party LIKE ? OR notes LIKE ?)")
            term = f"%{search.strip()}%"
            params.extend([term, term, term, term])
        where = f" WHERE {' AND '.join(clauses)}" if clauses else ""
        with self.connect() as con:
            return list(con.execute(f"SELECT * FROM transactions{where} ORDER BY date DESC, id DESC", params))

    def summary(self, year: int, month: int | None = None) -> dict:
        date_filter = "strftime('%Y', date) = ?"
        params: list[str] = [str(year)]
        if month:
            date_filter += " AND strftime('%m', date) = ?"
            params.append(f"{month:02d}")
        with self.connect() as con:
            rows = con.execute(
                f"""SELECT type, COALESCE(SUM(amount), 0) total, COUNT(*) quantity
                    FROM transactions WHERE {date_filter} GROUP BY type""",
                params,
            ).fetchall()
            by_type = {row["type"]: (float(row["total"]), int(row["quantity"])) for row in rows}
            categories = con.execute(
                f"""SELECT category, type, COALESCE(SUM(amount), 0) total
                    FROM transactions WHERE {date_filter}
                    GROUP BY category, type ORDER BY total DESC""",
                params,
            ).fetchall()
        income, income_count = by_type.get("Ingreso", (0.0, 0))
        expense, expense_count = by_type.get("Gasto", (0.0, 0))
        return {
            "income": income,
            "expense": expense,
            "profit": income - expense,
            "count": income_count + expense_count,
            "categories": categories,
        }

    def monthly_summary(self, year: int) -> list[dict]:
        values = {month: {"month": month, "income": 0.0, "expense": 0.0} for month in range(1, 13)}
        with self.connect() as con:
            rows = con.execute(
                """SELECT CAST(strftime('%m', date) AS INTEGER) month, type, SUM(amount) total
                   FROM transactions WHERE strftime('%Y', date) = ? GROUP BY month, type""",
                (str(year),),
            ).fetchall()
        for row in rows:
            key = "income" if row["type"] == "Ingreso" else "expense"
            values[int(row["month"])][key] = float(row["total"])
        return list(values.values())

