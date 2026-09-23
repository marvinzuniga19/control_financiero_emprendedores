from pathlib import Path
from tempfile import TemporaryDirectory
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from database import Database
from services import currency, parse_nonnegative_amount, parse_positive_amount, validate_iso_date


def run_tests():
    assert currency(1234.5) == "C$ 1,234.50"
    assert parse_positive_amount("C$ 1,250.75") == 1250.75
    assert parse_nonnegative_amount("0") == 0
    assert validate_iso_date("2026-09-23") == "2026-09-23"

    with TemporaryDirectory() as tmp:
        db = Database(Path(tmp) / "test.db")
        db.add_transaction({
            "date": "2026-01-10", "type": "Ingreso", "category": "Ventas",
            "description": "Venta", "payment_method": "Efectivo", "amount": 5000,
            "party": "Cliente", "notes": "",
        })
        db.add_transaction({
            "date": "2026-01-11", "type": "Gasto", "category": "Materiales",
            "description": "Compra", "payment_method": "Transferencia", "amount": 1200,
            "party": "Proveedor", "notes": "",
        })
        summary = db.summary(2026, 1)
        assert summary["income"] == 5000
        assert summary["expense"] == 1200
        assert summary["profit"] == 3800
        assert summary["count"] == 2
        monthly = db.monthly_summary(2026)
        assert monthly[0]["income"] == 5000
        assert monthly[0]["expense"] == 1200

    print("Todas las pruebas finalizaron correctamente.")


if __name__ == "__main__":
    run_tests()
