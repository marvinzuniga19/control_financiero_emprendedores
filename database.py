from __future__ import annotations

import shutil
import sqlite3
from contextlib import contextmanager
from pathlib import Path
from typing import Iterator

APP_DIR = Path(__file__).resolve().parent
DATA_DIR = APP_DIR / "data"
DB_PATH = DATA_DIR / "control_financiero.db"

SCHEMA_VERSION = 2

DEFAULT_INCOME_CATEGORIES = ["Ventas", "Servicios", "Pedidos personalizados", "Comisiones", "Otros ingresos"]
DEFAULT_EXPENSE_CATEGORIES = ["Materiales", "Publicidad", "Transporte", "Servicios básicos", "Alquiler", "Comisiones", "Impuestos", "Otros gastos"]
DEFAULT_PAYMENT_METHODS = ["Efectivo", "Transferencia", "Tarjeta", "Otro"]

TRANSACTIONS_DDL = """
CREATE TABLE IF NOT EXISTS transactions (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    date TEXT NOT NULL,
    type TEXT NOT NULL CHECK(type IN ('Ingreso', 'Gasto')),
    category TEXT NOT NULL,
    description TEXT NOT NULL,
    payment_method TEXT NOT NULL,
    amount_cents INTEGER NOT NULL CHECK(amount_cents > 0),
    party TEXT DEFAULT '',
    notes TEXT DEFAULT '',
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
);
"""


class InUseError(Exception):
    """Se lanza al intentar eliminar una categoría o método de pago en uso."""


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

                """
                + TRANSACTIONS_DDL
                + """
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
                "theme": "system",
            }
            con.executemany("INSERT OR IGNORE INTO settings(key, value) VALUES (?, ?)", defaults.items())
            con.executemany("INSERT OR IGNORE INTO categories(name, type) VALUES (?, 'Ingreso')", [(x,) for x in DEFAULT_INCOME_CATEGORIES])
            con.executemany("INSERT OR IGNORE INTO categories(name, type) VALUES (?, 'Gasto')", [(x,) for x in DEFAULT_EXPENSE_CATEGORIES])
            con.executemany("INSERT OR IGNORE INTO payment_methods(name) VALUES (?)", [(x,) for x in DEFAULT_PAYMENT_METHODS])

            version = con.execute("PRAGMA user_version").fetchone()[0]
            if version < SCHEMA_VERSION:
                if self._needs_amount_migration(con):
                    self._backup_database()
                    self._migrate_amount_to_cents(con)
                con.execute(f"PRAGMA user_version = {SCHEMA_VERSION}")

    @staticmethod
    def _needs_amount_migration(con: sqlite3.Connection) -> bool:
        columns = {row["name"] for row in con.execute("PRAGMA table_info(transactions)")}
        return "amount" in columns and "amount_cents" not in columns

    def _backup_database(self) -> None:
        if self.path.exists():
            shutil.copy2(self.path, f"{self.path}.bak")

    @staticmethod
    def _migrate_amount_to_cents(con: sqlite3.Connection) -> None:
        con.execute("ALTER TABLE transactions ADD COLUMN amount_cents INTEGER")
        con.execute("UPDATE transactions SET amount_cents = CAST(ROUND(amount * 100) AS INTEGER)")
        con.execute(
            "CREATE TABLE transactions_v2 ("
            "id INTEGER PRIMARY KEY AUTOINCREMENT,"
            "date TEXT NOT NULL,"
            "type TEXT NOT NULL CHECK(type IN ('Ingreso', 'Gasto')),"
            "category TEXT NOT NULL,"
            "description TEXT NOT NULL,"
            "payment_method TEXT NOT NULL,"
            "amount_cents INTEGER NOT NULL CHECK(amount_cents > 0),"
            "party TEXT DEFAULT '',"
            "notes TEXT DEFAULT '',"
            "created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP"
            ")"
        )
        con.execute(
            """INSERT INTO transactions_v2 (id, date, type, category, description, payment_method, amount_cents, party, notes, created_at)
               SELECT id, date, type, category, description, payment_method, amount_cents, party, notes, created_at
               FROM transactions"""
        )
        con.execute("DROP TABLE transactions")
        con.execute("ALTER TABLE transactions_v2 RENAME TO transactions")
        con.execute("CREATE INDEX IF NOT EXISTS idx_transactions_date ON transactions(date)")
        con.execute("CREATE INDEX IF NOT EXISTS idx_transactions_type ON transactions(type)")
        con.execute("CREATE INDEX IF NOT EXISTS idx_transactions_category ON transactions(category)")

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
        name = " ".join(name.strip().split())
        if not name:
            raise ValueError("El nombre no puede estar vacío.")
        with self.connect() as con:
            existing = con.execute(
                "SELECT 1 FROM categories WHERE lower(name) = lower(?) AND type = ?",
                (name, transaction_type),
            ).fetchone()
            if existing:
                raise ValueError(f"La categoría \"{name}\" ya existe.")
            con.execute("INSERT INTO categories(name, type) VALUES (?, ?)", (name, transaction_type))

    def delete_category(self, name: str, transaction_type: str) -> None:
        with self.connect() as con:
            used = con.execute(
                "SELECT COUNT(*) FROM transactions WHERE category = ? AND type = ?",
                (name, transaction_type),
            ).fetchone()[0]
            if used:
                raise InUseError(f"La categoría \"{name}\" se usa en {used} movimiento(s); no se puede eliminar.")
            con.execute("DELETE FROM categories WHERE name = ? AND type = ?", (name, transaction_type))

    def payment_methods(self) -> list[str]:
        with self.connect() as con:
            return [row["name"] for row in con.execute("SELECT name FROM payment_methods ORDER BY name")]

    def add_payment_method(self, name: str) -> None:
        name = " ".join(name.strip().split())
        if not name:
            raise ValueError("El nombre no puede estar vacío.")
        with self.connect() as con:
            existing = con.execute(
                "SELECT 1 FROM payment_methods WHERE lower(name) = lower(?)",
                (name,),
            ).fetchone()
            if existing:
                raise ValueError(f"El método de pago \"{name}\" ya existe.")
            con.execute("INSERT INTO payment_methods(name) VALUES (?)", (name,))

    def delete_payment_method(self, name: str) -> None:
        with self.connect() as con:
            used = con.execute(
                "SELECT COUNT(*) FROM transactions WHERE payment_method = ?",
                (name,),
            ).fetchone()[0]
            if used:
                raise InUseError(f"El método de pago \"{name}\" se usa en {used} movimiento(s); no se puede eliminar.")
            con.execute("DELETE FROM payment_methods WHERE name = ?", (name,))

    @staticmethod
    def _to_cents(amount: float) -> int:
        return int(round(float(amount) * 100))

    def add_transaction(self, data: dict) -> int:
        payload = dict(data)
        payload["amount_cents"] = self._to_cents(payload.pop("amount"))
        with self.connect() as con:
            cursor = con.execute(
                """INSERT INTO transactions(date, type, category, description, payment_method, amount_cents, party, notes)
                   VALUES (:date, :type, :category, :description, :payment_method, :amount_cents, :party, :notes)""",
                payload,
            )
            return int(cursor.lastrowid)

    def update_transaction(self, transaction_id: int, data: dict) -> None:
        payload = dict(data)
        payload["id"] = transaction_id
        payload["amount_cents"] = self._to_cents(payload.pop("amount"))
        with self.connect() as con:
            con.execute(
                """UPDATE transactions SET date=:date, type=:type, category=:category,
                   description=:description, payment_method=:payment_method, amount_cents=:amount_cents,
                   party=:party, notes=:notes WHERE id=:id""",
                payload,
            )

    def delete_transaction(self, transaction_id: int) -> None:
        with self.connect() as con:
            con.execute("DELETE FROM transactions WHERE id = ?", (transaction_id,))

    def transactions(
        self,
        year: int | None = None,
        month: int | None = None,
        search: str = "",
        start: str | None = None,
        end: str | None = None,
        transaction_type: str | None = None,
    ) -> list[sqlite3.Row]:
        clauses, params = [], []
        if year:
            clauses.append("strftime('%Y', date) = ?")
            params.append(str(year))
        if month:
            clauses.append("strftime('%m', date) = ?")
            params.append(f"{month:02d}")
        if transaction_type:
            clauses.append("type = ?")
            params.append(transaction_type)
        if start:
            clauses.append("date >= ?")
            params.append(start)
        if end:
            clauses.append("date <= ?")
            params.append(end)
        if search.strip():
            clauses.append("(description LIKE ? OR category LIKE ? OR party LIKE ? OR notes LIKE ?)")
            term = f"%{search.strip()}%"
            params.extend([term, term, term, term])
        where = f" WHERE {' AND '.join(clauses)}" if clauses else ""
        select = (
            "SELECT id, date, type, category, description, payment_method,"
            " CAST(amount_cents AS REAL) / 100.0 AS amount, party, notes, created_at"
            " FROM transactions"
        )
        with self.connect() as con:
            return list(con.execute(f"{select}{where} ORDER BY date DESC, id DESC", params))

    def summary(self, year: int, month: int | None = None) -> dict:
        date_filter = "strftime('%Y', date) = ?"
        params: list[str] = [str(year)]
        if month:
            date_filter += " AND strftime('%m', date) = ?"
            params.append(f"{month:02d}")
        with self.connect() as con:
            rows = con.execute(
                f"""SELECT type, COALESCE(SUM(amount_cents), 0) total_cents, COUNT(*) quantity
                    FROM transactions WHERE {date_filter} GROUP BY type""",
                params,
            ).fetchall()
            by_type = {row["type"]: (float(row["total_cents"]) / 100.0, int(row["quantity"])) for row in rows}
            categories = [
                {"category": row["category"], "type": row["type"], "total": float(row["total_cents"]) / 100.0}
                for row in con.execute(
                    f"""SELECT category, type, COALESCE(SUM(amount_cents), 0) total_cents
                        FROM transactions WHERE {date_filter}
                        GROUP BY category, type ORDER BY total_cents DESC""",
                    params,
                ).fetchall()
            ]
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
                """SELECT CAST(strftime('%m', date) AS INTEGER) month, type, SUM(amount_cents) total_cents
                   FROM transactions WHERE strftime('%Y', date) = ? GROUP BY month, type""",
                (str(year),),
            ).fetchall()
        for row in rows:
            key = "income" if row["type"] == "Ingreso" else "expense"
            values[int(row["month"])][key] = float(row["total_cents"]) / 100.0
        return list(values.values())