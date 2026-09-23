import sqlite3

import pytest

from database import Database, InUseError


@pytest.fixture
def db(tmp_path):
    return Database(tmp_path / "test.db")


def _transaction(**overrides):
    data = {
        "date": "2026-01-10", "type": "Ingreso", "category": "Ventas",
        "description": "Venta", "payment_method": "Efectivo", "amount": 5000,
        "party": "Cliente", "notes": "",
    }
    data.update(overrides)
    return data


def test_add_and_read_transaction(db):
    tid = db.add_transaction(_transaction())
    rows = db.transactions()
    assert len(rows) == 1
    assert rows[0]["id"] == tid
    assert rows[0]["amount"] == 5000


def test_stores_amount_in_cents(db):
    db.add_transaction(_transaction(amount=1250.75))
    with db.connect() as con:
        cents = con.execute("SELECT amount_cents FROM transactions").fetchone()[0]
        assert cents == 125075


def test_update_transaction_converts_cents(db):
    tid = db.add_transaction(_transaction(amount=100))
    db.update_transaction(tid, _transaction(amount=200.50))
    rows = db.transactions()
    assert rows[0]["amount"] == 200.5
    with db.connect() as con:
        assert con.execute("SELECT amount_cents FROM transactions").fetchone()[0] == 20050


def test_summary(db):
    db.add_transaction(_transaction())
    db.add_transaction(_transaction(date="2026-01-11", type="Gasto", category="Materiales", description="Compra", payment_method="Transferencia", amount=1200))
    summary = db.summary(2026, 1)
    assert summary["income"] == 5000
    assert summary["expense"] == 1200
    assert summary["profit"] == 3800
    assert summary["count"] == 2
    assert {c["category"] for c in summary["categories"]} == {"Ventas", "Materiales"}
    assert all(isinstance(c["total"], float) for c in summary["categories"])


def test_summary_filters_by_year_and_month(db):
    db.add_transaction(_transaction(date="2026-01-10"))
    db.add_transaction(_transaction(date="2025-12-10"))
    assert db.summary(2026)["count"] == 1
    assert db.summary(2025, 12)["count"] == 1


def test_monthly_summary(db):
    db.add_transaction(_transaction(date="2026-01-10"))
    db.add_transaction(_transaction(date="2026-01-11", type="Gasto", category="Materiales", description="Compra", amount=1200))
    monthly = db.monthly_summary(2026)
    assert monthly[0]["income"] == 5000
    assert monthly[0]["expense"] == 1200
    assert monthly[11]["income"] == 0.0


def test_transaction_filters(db):
    db.add_transaction(_transaction(date="2026-01-10"))
    db.add_transaction(_transaction(date="2026-02-10", type="Gasto", category="Materiales", description="Compra", amount=50))
    assert len(db.transactions(year=2026, month=1)) == 1
    assert len(db.transactions(start="2026-02-01", end="2026-02-28")) == 1
    assert len(db.transactions(transaction_type="Ingreso")) == 1
    assert len(db.transactions(search="Compra")) == 1
    assert len(db.transactions()) == 2


def test_delete_category_in_use_raises(db):
    db.add_transaction(_transaction())
    with pytest.raises(InUseError):
        db.delete_category("Ventas", "Ingreso")


def test_delete_payment_method_in_use_raises(db):
    db.add_transaction(_transaction())
    with pytest.raises(InUseError):
        db.delete_payment_method("Efectivo")


def test_delete_category_when_unused(db):
    db.delete_category("Ventas", "Ingreso")
    assert "Ventas" not in db.categories("Ingreso")


def test_delete_payment_method_when_unused(db):
    db.delete_payment_method("Efectivo")
    assert "Efectivo" not in db.payment_methods()


def test_add_category_validations(db):
    with pytest.raises(ValueError):
        db.add_category("   ", "Ingreso")
    db.add_category("Nueva Categoría", "Ingreso")
    with pytest.raises(ValueError):
        db.add_category("nueva   categoría", "Ingreso")


def test_add_payment_method_validations(db):
    with pytest.raises(ValueError):
        db.add_payment_method("   ")
    db.add_payment_method("Cheque")
    with pytest.raises(ValueError):
        db.add_payment_method("cheque")


def test_theme_setting_default_and_update(db):
    assert db.get_settings().get("theme") == "system"
    db.update_settings({"theme": "dark"})
    assert db.get_settings()["theme"] == "dark"


LEGACY_DDL = """
CREATE TABLE settings (
    key TEXT PRIMARY KEY,
    value TEXT NOT NULL
);
CREATE TABLE categories (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    name TEXT NOT NULL,
    type TEXT NOT NULL CHECK(type IN ('Ingreso', 'Gasto')),
    UNIQUE(name, type)
);
CREATE TABLE payment_methods (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    name TEXT NOT NULL UNIQUE
);
CREATE TABLE transactions (
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
CREATE INDEX idx_transactions_date ON transactions(date);
CREATE INDEX idx_transactions_type ON transactions(type);
CREATE INDEX idx_transactions_category ON transactions(category);
"""


def _insert_legacy(con, **overrides):
    data = {
        "date": "2026-01-10", "type": "Ingreso", "category": "Ventas",
        "description": "Venta", "payment_method": "Efectivo", "amount": 1250.75,
        "party": "", "notes": "",
    }
    data.update(overrides)
    con.execute(
        "INSERT INTO transactions(date, type, category, description, payment_method, amount, party, notes) "
        "VALUES (:date, :type, :category, :description, :payment_method, :amount, :party, :notes)",
        data,
    )


def test_fresh_database_is_schema_v2(db):
    with db.connect() as con:
        assert con.execute("PRAGMA user_version").fetchone()[0] == 2
        columns = {r["name"] for r in con.execute("PRAGMA table_info(transactions)")}
        assert "amount" not in columns
        assert "amount_cents" in columns


def test_migration_from_legacy_schema_to_cents(tmp_path):
    path = tmp_path / "legacy.db"
    con = sqlite3.connect(path)
    con.executescript(LEGACY_DDL)
    _insert_legacy(con, amount=1250.75)
    _insert_legacy(con, date="2026-01-11", type="Gasto", category="Materiales", description="Compra", payment_method="Transferencia", amount=49.99)
    con.commit()
    con.close()

    db = Database(path)

    assert path.with_name(f"{path.name}.bak").exists()
    rows = db.transactions()
    assert sorted(r["amount"] for r in rows) == [49.99, 1250.75]
    summary = db.summary(2026)
    assert summary["income"] == 1250.75
    assert summary["expense"] == 49.99
    with db.connect() as con:
        assert con.execute("PRAGMA user_version").fetchone()[0] == 2
        columns = {r["name"] for r in con.execute("PRAGMA table_info(transactions)")}
        assert "amount" not in columns
        assert "amount_cents" in columns
        assert con.execute("SELECT COUNT(*) FROM transactions WHERE amount_cents = 125075").fetchone()[0] == 1


def test_migration_does_not_duplicate_data(tmp_path):
    path = tmp_path / "legacy.db"
    con = sqlite3.connect(path)
    con.executescript(LEGACY_DDL)
    _insert_legacy(con, amount=10)
    con.commit()
    con.close()

    db = Database(path)
    db2 = Database(path)

    with db2.connect() as con:
        assert con.execute("PRAGMA user_version").fetchone()[0] == 2
        assert con.execute("SELECT COUNT(*) FROM transactions").fetchone()[0] == 1
    assert len(db2.transactions()) == 1