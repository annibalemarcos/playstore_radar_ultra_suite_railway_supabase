"""Inicializa o schema no SQLite local ou no PostgreSQL configurado."""
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from app_core.config import database_target
from app_core.database import database_backend, init_db, ping_database


def main() -> None:
    target = database_target()
    init_db(target, force=True)
    if not ping_database(target):
        raise SystemExit("Banco inicializado, mas não respondeu ao teste.")
    print(f"Banco pronto: {database_backend(target)}")


if __name__ == "__main__":
    main()
