"""Migra o histórico SQLite existente para PostgreSQL/Supabase.

Uso:
    set DATABASE_URL=postgresql://...
    python scripts/migrate_sqlite_to_supabase.py
"""
from __future__ import annotations

import argparse
import os
import sqlite3
import sys
from pathlib import Path
from typing import Any, Iterable

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from app_core.config import DEFAULT_DB_PATH, database_target  # noqa: E402
from app_core.database import connect, init_db, is_postgres_target  # noqa: E402

TABLES = ("runs", "apps", "logs", "api_tests")


def chunks(items: list[tuple[Any, ...]], size: int) -> Iterable[list[tuple[Any, ...]]]:
    for index in range(0, len(items), size):
        yield items[index:index + size]


def source_columns(con: sqlite3.Connection, table: str) -> list[str]:
    return [str(row["name"]) for row in con.execute(f"PRAGMA table_info({table})").fetchall()]


def target_columns(target: str, table: str) -> list[str]:
    with connect(target) as con:
        rows = con.execute(
            """
            SELECT column_name
            FROM information_schema.columns
            WHERE table_schema = current_schema() AND table_name = ?
            ORDER BY ordinal_position
            """,
            (table,),
        ).fetchall()
    return [str(row["column_name"]) for row in rows]


def migrate_table(source: sqlite3.Connection, target: str, table: str, batch_size: int) -> int:
    src_columns = source_columns(source, table)
    dst_columns = set(target_columns(target, table))
    columns = [column for column in src_columns if column in dst_columns]
    if not columns:
        return 0

    selected = ", ".join(columns)
    source_rows = source.execute(f"SELECT {selected} FROM {table} ORDER BY id").fetchall()
    values = [tuple(row[column] for column in columns) for row in source_rows]
    if not values:
        return 0

    placeholders = ", ".join("?" for _ in columns)
    update_columns = [column for column in columns if column != "id"]
    conflict = "DO NOTHING"
    if update_columns:
        assignments = ", ".join(f"{column} = EXCLUDED.{column}" for column in update_columns)
        conflict = f"DO UPDATE SET {assignments}"
    query = f"INSERT INTO {table} ({selected}) VALUES ({placeholders}) ON CONFLICT (id) {conflict}"

    copied = 0
    for batch in chunks(values, batch_size):
        with connect(target) as con:
            con.executemany(query, batch)
        copied += len(batch)
        print(f"  {table}: {copied}/{len(values)}")
    return copied


def reset_sequences(target: str) -> None:
    with connect(target) as con:
        for table in TABLES:
            con.execute(
                f"""
                SELECT setval(
                    pg_get_serial_sequence('{table}', 'id'),
                    COALESCE((SELECT MAX(id) FROM {table}), 1),
                    EXISTS(SELECT 1 FROM {table})
                )
                """
            )


def main() -> None:
    parser = argparse.ArgumentParser(description="Migra o SQLite local para o PostgreSQL/Supabase.")
    parser.add_argument("--source", default=str(DEFAULT_DB_PATH), help="Caminho do SQLite de origem.")
    parser.add_argument("--database-url", default="", help="URL PostgreSQL; por padrão usa DATABASE_URL/SUPABASE_DB_URL.")
    parser.add_argument("--batch-size", type=int, default=200)
    parser.add_argument("--merge", action="store_true", help="Mescla por ID quando o destino já contém dados.")
    args = parser.parse_args()

    source_path = Path(args.source).expanduser().resolve()
    target = args.database_url.strip() or database_target()
    if not source_path.exists():
        raise SystemExit(f"SQLite não encontrado: {source_path}")
    if not is_postgres_target(target):
        raise SystemExit("Defina DATABASE_URL/SUPABASE_DB_URL com a connection string PostgreSQL do Supabase.")

    init_db(target, force=True)
    with connect(target) as con:
        existing = sum(int(con.execute(f"SELECT COUNT(*) AS c FROM {table}").fetchone()["c"]) for table in TABLES)
    if existing and not args.merge:
        raise SystemExit(
            f"O destino já possui {existing} registros. Use --merge para atualizar/mesclar por ID."
        )

    source = sqlite3.connect(str(source_path))
    source.row_factory = sqlite3.Row
    try:
        source.execute("PRAGMA foreign_keys=ON")
        totals = {table: migrate_table(source, target, table, max(1, args.batch_size)) for table in TABLES}
    finally:
        source.close()
    reset_sequences(target)
    print("Migração concluída: " + ", ".join(f"{table}={count}" for table, count in totals.items()))


if __name__ == "__main__":
    main()
