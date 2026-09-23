import pytest

from services import (
    build_alerts,
    currency,
    export_transactions_csv,
    is_dark_mode,
    parse_nonnegative_amount,
    parse_positive_amount,
    validate_iso_date,
)


def test_currency():
    assert currency(1234.5) == "C$ 1,234.50"


def test_parse_positive_amount():
    assert parse_positive_amount("C$ 1,250.75") == 1250.75


def test_parse_positive_amount_rejects_zero():
    with pytest.raises(ValueError):
        parse_positive_amount("0")


def test_parse_nonnegative_amount_accepts_zero():
    assert parse_nonnegative_amount("0") == 0


def test_parse_nonnegative_amount_rejects_negative():
    with pytest.raises(ValueError):
        parse_nonnegative_amount("-5")


def test_validate_iso_date():
    assert validate_iso_date("2026-09-23") == "2026-09-23"


def test_validate_iso_date_rejects_bad_format():
    with pytest.raises(ValueError):
        validate_iso_date("23/09/2026")


def test_is_dark_mode():
    assert is_dark_mode("Dark")
    assert not is_dark_mode(" Light ")
    assert not is_dark_mode("")


def test_build_alerts():
    settings = {"income_goal": "100", "expense_limit": "50"}
    summary = {"income": 120, "expense": 60, "profit": 60}
    alerts = build_alerts(settings, summary)
    assert alerts["compliance"] == 120.0
    assert alerts["used"] == 120.0
    assert "Meta de ingresos alcanzada." in alerts["messages"]
    assert "Gastos sobre el límite." in alerts["messages"]


def test_build_alerts_without_limits():
    settings = {"income_goal": "0", "expense_limit": "0"}
    summary = {"income": 10, "expense": 5, "profit": 5}
    alerts = build_alerts(settings, summary)
    assert alerts["compliance"] == 0.0
    assert alerts["used"] == 0.0


def test_export_transactions_csv(tmp_path):
    path = tmp_path / "out.csv"
    rows = [{
        "id": 1, "date": "2026-01-01", "type": "Ingreso", "category": "Ventas",
        "description": "Venta", "payment_method": "Efectivo", "amount": 1250.75,
        "party": "Cliente", "notes": "",
    }]
    export_transactions_csv(rows, path)
    content = path.read_text(encoding="utf-8-sig")
    assert "1250.75" in content
    assert "Ventas" in content
    assert content.splitlines()[0].startswith("ID")