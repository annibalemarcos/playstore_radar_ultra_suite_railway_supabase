"""Camada de banco híbrida: SQLite local ou PostgreSQL/Supabase online."""
from __future__ import annotations

import os
import sqlite3
import threading
from contextlib import contextmanager
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, Iterable, Iterator, List, Optional

from .config import DEFAULT_DB_PATH, RunConfig
from .scoring import safe_json

try:  # Instalado no ambiente online; localmente só é necessário ao usar PostgreSQL.
    import psycopg
    from psycopg.rows import dict_row
except Exception:  # pragma: no cover - SQLite local continua funcionando sem psycopg.
    psycopg = None
    dict_row = None

APP_COLUMNS = [
    "run_id", "categoria", "categoria_codigo", "rank", "app_id", "title", "developer", "developer_email",
    "developer_website", "developer_address", "privacy_policy", "genre", "genre_id", "score", "ratings",
    "reviews", "installs", "min_installs", "real_installs", "free", "price", "currency", "contains_ads",
    "ad_supported", "offers_iap", "iap_price", "content_rating", "released", "updated", "version",
    "android_version", "summary", "description", "recent_changes", "icon", "header_image", "screenshots_json",
    "video", "url", "indie_score", "growth_score", "opportunity_score", "perfil_detectado", "is_giant",
    "estimated_mau", "revenue_monthly_usd_low", "revenue_monthly_usd_base", "revenue_monthly_usd_high",
    "profit_monthly_usd_base", "revenue_monthly_brl_base", "profit_monthly_brl_base", "financial_confidence",
    "financial_notes", "review_count_collected", "review_score_avg_recent", "review_positive_pct", "review_negative_pct",
    "review_keywords_json", "review_samples_json", "external_sources_used", "external_title", "external_description",
    "external_markdown_preview", "raw_json",
]

RUN_ACTIVE_STATUSES = {"queued", "running", "pause_requested", "paused", "cancel_requested", "delete_requested", "restart_requested"}
RUN_TERMINAL_STATUSES = {"finished", "finished_with_warnings", "failed", "cancelled", "deleted"}

_INIT_LOCK = threading.Lock()
_INITIALIZED_TARGETS: set[str] = set()


def now_iso() -> str:
    return datetime.now().strftime("%Y-%m-%d %H:%M:%S")


def resolve_db_target(db_path: str | Path | None = None) -> str:
    """Resolve o alvo sem quebrar o uso antigo baseado em caminho de arquivo."""
    value = str(db_path or "").strip()
    if value:
        return value
    return (
        os.getenv("DATABASE_URL", "").strip()
        or os.getenv("SUPABASE_DB_URL", "").strip()
        or str(DEFAULT_DB_PATH)
    )


def is_postgres_target(db_path: str | Path | None = None) -> bool:
    value = resolve_db_target(db_path).lower()
    return value.startswith("postgresql://") or value.startswith("postgres://")


def database_backend(db_path: str | Path | None = None) -> str:
    return "postgresql" if is_postgres_target(db_path) else "sqlite"


def _normalize_postgres_url(value: str) -> str:
    if value.startswith("postgres://"):
        return "postgresql://" + value[len("postgres://"):]
    return value


class DatabaseConnection:
    """Pequeno adaptador para manter as queries atuais compatíveis nos dois bancos."""

    def __init__(self, raw: Any, backend: str):
        self.raw = raw
        self.backend = backend

    def _query(self, query: str) -> str:
        # As queries do projeto usam placeholders DB-API do SQLite. Psycopg usa %s.
        return query.replace("?", "%s") if self.backend == "postgresql" else query

    def execute(self, query: str, params: Iterable[Any] | None = None):
        adapted = self._query(query)
        if params is None:
            return self.raw.execute(adapted)
        return self.raw.execute(adapted, tuple(params))

    def executemany(self, query: str, params_seq: Iterable[Iterable[Any]]):
        adapted = self._query(query)
        rows = [tuple(row) for row in params_seq]
        if self.backend == "postgresql":
            cursor = self.raw.cursor()
            cursor.executemany(adapted, rows)
            return cursor
        return self.raw.executemany(adapted, rows)

    def executescript(self, script: str) -> None:
        if self.backend == "sqlite":
            self.raw.executescript(script)
            return
        # O schema deste projeto não contém funções/procedures; divisão por ';' é segura aqui.
        for statement in (chunk.strip() for chunk in script.split(";")):
            if statement:
                self.raw.execute(statement)


@contextmanager
def connect(db_path: str | Path | None = None) -> Iterator[DatabaseConnection]:
    target = resolve_db_target(db_path)
    if is_postgres_target(target):
        if psycopg is None:
            raise RuntimeError(
                "DATABASE_URL aponta para PostgreSQL, mas o driver psycopg não está instalado. "
                "Rode: pip install -r requirements.txt"
            )
        url = _normalize_postgres_url(target)
        kwargs: Dict[str, Any] = {"row_factory": dict_row, "connect_timeout": 20}
        sslmode = os.getenv("DB_SSLMODE", "").strip()
        if sslmode:
            kwargs["sslmode"] = sslmode
        elif "supabase.co" in url and "sslmode=" not in url.lower():
            kwargs["sslmode"] = "require"
        # Também funciona com o pooler transacional do Supabase, que não aceita prepared statements.
        raw = psycopg.connect(url, prepare_threshold=None, **kwargs)
        con = DatabaseConnection(raw, "postgresql")
        try:
            yield con
            raw.commit()
        except Exception:
            raw.rollback()
            raise
        finally:
            raw.close()
        return

    path = Path(target).expanduser()
    path.parent.mkdir(parents=True, exist_ok=True)
    raw = sqlite3.connect(str(path), timeout=30)
    raw.row_factory = sqlite3.Row
    con = DatabaseConnection(raw, "sqlite")
    try:
        raw.execute("PRAGMA journal_mode=WAL")
        raw.execute("PRAGMA foreign_keys=ON")
        yield con
        raw.commit()
    except Exception:
        raw.rollback()
        raise
    finally:
        raw.close()


def _column_exists(con: DatabaseConnection, table: str, column: str) -> bool:
    if con.backend == "postgresql":
        row = con.execute(
            """
            SELECT 1
            FROM information_schema.columns
            WHERE table_schema = current_schema() AND table_name = ? AND column_name = ?
            LIMIT 1
            """,
            (table, column),
        ).fetchone()
        return bool(row)
    rows = con.execute(f"PRAGMA table_info({table})").fetchall()
    return any(row["name"] == column for row in rows)


_SQLITE_SCHEMA = """
CREATE TABLE IF NOT EXISTS runs (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    created_at TEXT NOT NULL,
    started_at TEXT,
    finished_at TEXT,
    status TEXT NOT NULL DEFAULT 'queued',
    scope TEXT,
    level TEXT,
    profile TEXT,
    quantity INTEGER,
    max_categories INTEGER,
    apps_scanned INTEGER DEFAULT 0,
    apps_kept INTEGER DEFAULT 0,
    categories_done INTEGER DEFAULT 0,
    categories_total INTEGER DEFAULT 0,
    errors_count INTEGER DEFAULT 0,
    last_message TEXT,
    config_json TEXT,
    output_dir TEXT,
    html_path TEXT,
    json_path TEXT,
    csv_path TEXT
);
CREATE TABLE IF NOT EXISTS apps (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    run_id INTEGER NOT NULL,
    categoria TEXT, categoria_codigo TEXT, rank INTEGER, app_id TEXT, title TEXT, developer TEXT,
    developer_email TEXT, developer_website TEXT, developer_address TEXT, privacy_policy TEXT,
    genre TEXT, genre_id TEXT, score REAL, ratings INTEGER, reviews INTEGER, installs TEXT,
    min_installs INTEGER, real_installs INTEGER, free INTEGER, price TEXT, currency TEXT,
    contains_ads INTEGER, ad_supported INTEGER, offers_iap INTEGER, iap_price TEXT,
    content_rating TEXT, released TEXT, updated TEXT, version TEXT, android_version TEXT,
    summary TEXT, description TEXT, recent_changes TEXT, icon TEXT, header_image TEXT,
    screenshots_json TEXT, video TEXT, url TEXT, indie_score INTEGER, growth_score INTEGER,
    opportunity_score INTEGER, perfil_detectado TEXT, is_giant INTEGER, estimated_mau INTEGER,
    revenue_monthly_usd_low REAL, revenue_monthly_usd_base REAL, revenue_monthly_usd_high REAL,
    profit_monthly_usd_base REAL, revenue_monthly_brl_base REAL, profit_monthly_brl_base REAL,
    financial_confidence TEXT, financial_notes TEXT, review_count_collected INTEGER,
    review_score_avg_recent REAL, review_positive_pct REAL, review_negative_pct REAL,
    review_keywords_json TEXT, review_samples_json TEXT, external_sources_used TEXT,
    external_title TEXT, external_description TEXT, external_markdown_preview TEXT,
    raw_json TEXT, created_at TEXT NOT NULL,
    FOREIGN KEY(run_id) REFERENCES runs(id) ON DELETE CASCADE
);
CREATE TABLE IF NOT EXISTS logs (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    run_id INTEGER, level TEXT, message TEXT, created_at TEXT NOT NULL,
    FOREIGN KEY(run_id) REFERENCES runs(id) ON DELETE CASCADE
);
CREATE TABLE IF NOT EXISTS api_tests (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    provider TEXT NOT NULL, ok INTEGER NOT NULL DEFAULT 0, status TEXT,
    message TEXT, latency_ms INTEGER, created_at TEXT NOT NULL
);
"""

_POSTGRES_SCHEMA = (
    _SQLITE_SCHEMA.replace(
        "id INTEGER PRIMARY KEY AUTOINCREMENT", "id BIGSERIAL PRIMARY KEY"
    ).replace(
        "run_id INTEGER NOT NULL", "run_id BIGINT NOT NULL"
    ).replace(
        "run_id INTEGER, level TEXT", "run_id BIGINT, level TEXT"
    ).replace(
        "ratings INTEGER", "ratings BIGINT"
    ).replace(
        "reviews INTEGER", "reviews BIGINT"
    ).replace(
        "min_installs INTEGER", "min_installs BIGINT"
    ).replace(
        "real_installs INTEGER", "real_installs BIGINT"
    ).replace(
        "estimated_mau INTEGER", "estimated_mau BIGINT"
    ).replace(
        "review_count_collected INTEGER", "review_count_collected BIGINT"
    ).replace(
        " REAL", " DOUBLE PRECISION"
    )
)

_INDEX_SCHEMA = """
CREATE INDEX IF NOT EXISTS idx_apps_run ON apps(run_id);
CREATE INDEX IF NOT EXISTS idx_apps_app_id ON apps(app_id);
CREATE INDEX IF NOT EXISTS idx_apps_profile ON apps(perfil_detectado);
CREATE INDEX IF NOT EXISTS idx_apps_scores ON apps(indie_score, growth_score, opportunity_score);
CREATE INDEX IF NOT EXISTS idx_apps_created ON apps(created_at);
CREATE INDEX IF NOT EXISTS idx_logs_run ON logs(run_id);
CREATE INDEX IF NOT EXISTS idx_runs_status ON runs(status);
CREATE INDEX IF NOT EXISTS idx_runs_created ON runs(created_at);
CREATE INDEX IF NOT EXISTS idx_api_tests_provider ON api_tests(provider, created_at);
"""


def init_db(db_path: str | Path | None = None, force: bool = False) -> None:
    target = resolve_db_target(db_path)
    if not force and target in _INITIALIZED_TARGETS:
        return
    with _INIT_LOCK:
        if not force and target in _INITIALIZED_TARGETS:
            return
        with connect(target) as con:
            con.executescript(_POSTGRES_SCHEMA if con.backend == "postgresql" else _SQLITE_SCHEMA)
            con.executescript(_INDEX_SCHEMA)
            # Migração leve para bancos antigos: sem quebrar nada, só adiciona metadados úteis.
            extra_columns = {
                "control_note": "TEXT",
                "parent_run_id": "BIGINT" if con.backend == "postgresql" else "INTEGER",
                "updated_at": "TEXT",
            }
            for column, ddl_type in extra_columns.items():
                if not _column_exists(con, "runs", column):
                    con.execute(f"ALTER TABLE runs ADD COLUMN {column} {ddl_type}")
        _INITIALIZED_TARGETS.add(target)


def ping_database(db_path: str | Path | None = None) -> bool:
    init_db(db_path)
    with connect(db_path) as con:
        row = con.execute("SELECT 1 AS ok").fetchone()
    return bool(row and row["ok"] == 1)

def create_run(cfg: RunConfig, status: str = "queued", parent_run_id: Optional[int] = None) -> int:
    init_db(cfg.db_path)
    params = (
        now_iso(), now_iso(), status, cfg.scope, cfg.level, cfg.profile, cfg.quantity, cfg.max_categories,
        cfg.to_json(), cfg.output_dir, "Na fila", parent_run_id,
    )
    query = """
        INSERT INTO runs(created_at, updated_at, status, scope, level, profile, quantity, max_categories, config_json, output_dir, last_message, parent_run_id)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
    """
    with connect(cfg.db_path) as con:
        if con.backend == "postgresql":
            row = con.execute(query + " RETURNING id", params).fetchone()
            return int(row["id"])
        cur = con.execute(query, params)
        return int(cur.lastrowid)


def update_run(db_path: str | Path, run_id: int, **kwargs: Any) -> None:
    if not kwargs:
        return
    allowed = {
        "started_at", "finished_at", "status", "apps_scanned", "apps_kept", "categories_done", "categories_total",
        "errors_count", "last_message", "html_path", "json_path", "csv_path", "output_dir", "control_note",
        "parent_run_id", "updated_at",
    }
    clean = {k: v for k, v in kwargs.items() if k in allowed}
    if not clean:
        return
    clean.setdefault("updated_at", now_iso())
    parts = ", ".join(f"{k} = ?" for k in clean)
    values = list(clean.values()) + [run_id]
    with connect(db_path) as con:
        con.execute(f"UPDATE runs SET {parts} WHERE id = ?", values)


def log(db_path: str | Path, run_id: int, message: str, level: str = "info") -> None:
    with connect(db_path) as con:
        exists = con.execute("SELECT 1 FROM runs WHERE id = ?", (run_id,)).fetchone()
        if not exists:
            return
        con.execute(
            "INSERT INTO logs(run_id, level, message, created_at) VALUES (?, ?, ?, ?)",
            (run_id, level, message, now_iso()),
        )
        con.execute("UPDATE runs SET last_message = ?, updated_at = ? WHERE id = ?", (message, now_iso(), run_id))


def request_run_status(db_path: str | Path, run_id: int, status: str, message: str, level: str = "warning") -> None:
    """Marca uma ação de controle para o worker obedecer no próximo ponto seguro."""
    update_run(db_path, run_id, status=status, control_note=message, last_message=message)
    log(db_path, run_id, message, level)


def delete_run(db_path: str | Path, run_id: int) -> None:
    init_db(db_path)
    with connect(db_path) as con:
        con.execute("DELETE FROM runs WHERE id = ?", (run_id,))


def as_int_bool(value: Any) -> Optional[int]:
    if value is None:
        return None
    if isinstance(value, bool):
        return 1 if value else 0
    return 1 if str(value).strip().lower() in {"1", "true", "sim", "yes", "s"} else 0


def app_to_db_row(run_id: int, app: Dict[str, Any]) -> Dict[str, Any]:
    data = {
        "run_id": run_id,
        "categoria": app.get("categoria"),
        "categoria_codigo": app.get("categoria_codigo") or app.get("category_code"),
        "rank": app.get("rank"),
        "app_id": app.get("appId") or app.get("app_id") or app.get("id"),
        "title": app.get("title"),
        "developer": app.get("developer"),
        "developer_email": app.get("developerEmail") or app.get("developer_email"),
        "developer_website": app.get("developerWebsite") or app.get("developer_website"),
        "developer_address": app.get("developerAddress") or app.get("developer_address"),
        "privacy_policy": app.get("privacyPolicy") or app.get("privacy_policy"),
        "genre": app.get("genre"),
        "genre_id": app.get("genreId") or app.get("genre_id"),
        "score": app.get("score"),
        "ratings": app.get("ratings"),
        "reviews": app.get("reviews"),
        "installs": app.get("installs"),
        "min_installs": app.get("minInstalls") or app.get("min_installs"),
        "real_installs": app.get("realInstalls") or app.get("real_installs"),
        "free": as_int_bool(app.get("free")),
        "price": app.get("price"),
        "currency": app.get("currency"),
        "contains_ads": as_int_bool(app.get("containsAds")),
        "ad_supported": as_int_bool(app.get("adSupported")),
        "offers_iap": as_int_bool(app.get("offersIAP")),
        "iap_price": app.get("inAppProductPrice") or app.get("iap_price"),
        "content_rating": app.get("contentRating") or app.get("content_rating"),
        "released": app.get("released"),
        "updated": app.get("updated"),
        "version": app.get("version"),
        "android_version": app.get("androidVersion") or app.get("android_version"),
        "summary": app.get("summary"),
        "description": app.get("description"),
        "recent_changes": app.get("recentChanges") or app.get("recent_changes"),
        "icon": app.get("icon"),
        "header_image": app.get("headerImage") or app.get("header_image"),
        "screenshots_json": safe_json(app.get("screenshots") or []),
        "video": app.get("video"),
        "url": app.get("url"),
        "indie_score": app.get("indie_score"),
        "growth_score": app.get("growth_score"),
        "opportunity_score": app.get("opportunity_score"),
        "perfil_detectado": app.get("perfil_detectado"),
        "is_giant": as_int_bool(app.get("is_giant")),
        "estimated_mau": app.get("estimated_mau"),
        "revenue_monthly_usd_low": app.get("revenue_monthly_usd_low"),
        "revenue_monthly_usd_base": app.get("revenue_monthly_usd_base"),
        "revenue_monthly_usd_high": app.get("revenue_monthly_usd_high"),
        "profit_monthly_usd_base": app.get("profit_monthly_usd_base"),
        "revenue_monthly_brl_base": app.get("revenue_monthly_brl_base"),
        "profit_monthly_brl_base": app.get("profit_monthly_brl_base"),
        "financial_confidence": app.get("financial_confidence"),
        "financial_notes": app.get("financial_notes"),
        "review_count_collected": app.get("review_count_collected"),
        "review_score_avg_recent": app.get("review_score_avg_recent"),
        "review_positive_pct": app.get("review_positive_pct"),
        "review_negative_pct": app.get("review_negative_pct"),
        "review_keywords_json": safe_json(app.get("review_keywords") or []),
        "review_samples_json": safe_json(app.get("review_samples") or []),
        "external_sources_used": ", ".join(app.get("external_sources_used") or []),
        "external_title": app.get("external_title"),
        "external_description": app.get("external_description"),
        "external_markdown_preview": app.get("external_markdown_preview"),
        "raw_json": safe_json(app),
    }
    return data


def insert_apps(db_path: str | Path, run_id: int, apps: Iterable[Dict[str, Any]]) -> int:
    rows = [app_to_db_row(run_id, app) for app in apps]
    if not rows:
        return 0
    placeholders = ", ".join("?" for _ in APP_COLUMNS)
    columns = ", ".join(APP_COLUMNS)
    values = [[row.get(c) for c in APP_COLUMNS] + [now_iso()] for row in rows]
    with connect(db_path) as con:
        exists = con.execute("SELECT 1 FROM runs WHERE id = ?", (run_id,)).fetchone()
        if not exists:
            return 0
        con.executemany(f"INSERT INTO apps({columns}, created_at) VALUES ({placeholders}, ?)", values)
    return len(rows)


def row_to_dict(row: Any | None) -> Optional[Dict[str, Any]]:
    if row is None:
        return None
    if isinstance(row, dict):
        return dict(row)
    return {k: row[k] for k in row.keys()}


def get_run(db_path: str | Path, run_id: int) -> Optional[Dict[str, Any]]:
    init_db(db_path)
    with connect(db_path) as con:
        row = con.execute("SELECT * FROM runs WHERE id = ?", (run_id,)).fetchone()
    return row_to_dict(row)


def list_runs(db_path: str | Path, limit: int = 50) -> List[Dict[str, Any]]:
    init_db(db_path)
    with connect(db_path) as con:
        rows = con.execute("SELECT * FROM runs ORDER BY id DESC LIMIT ?", (limit,)).fetchall()
    return [row_to_dict(r) or {} for r in rows]


def list_logs(db_path: str | Path, run_id: int, limit: int = 200) -> List[Dict[str, Any]]:
    init_db(db_path)
    with connect(db_path) as con:
        rows = con.execute("SELECT * FROM logs WHERE run_id = ? ORDER BY id DESC LIMIT ?", (run_id, limit)).fetchall()
    return list(reversed([row_to_dict(r) or {} for r in rows]))


def list_apps(
    db_path: str | Path,
    run_id: Optional[int] = None,
    q: str = "",
    profile: str = "",
    min_score: Optional[float] = None,
    order: str = "opportunity_score",
    limit: int = 300,
    date_from: str = "",
    date_to: str = "",
) -> List[Dict[str, Any]]:
    init_db(db_path)
    order_map = {
        "created_at": ("apps.created_at", "DESC"),
        "created_at_asc": ("apps.created_at", "ASC"),
        "run_created_at": ("runs.created_at", "DESC"),
        "run_created_at_asc": ("runs.created_at", "ASC"),
        "opportunity_score": ("apps.opportunity_score", "DESC"),
        "opportunity_score_asc": ("apps.opportunity_score", "ASC"),
        "growth_score": ("apps.growth_score", "DESC"),
        "growth_score_asc": ("apps.growth_score", "ASC"),
        "indie_score": ("apps.indie_score", "DESC"),
        "indie_score_asc": ("apps.indie_score", "ASC"),
        "scores": ("(COALESCE(apps.opportunity_score,0)+COALESCE(apps.growth_score,0)+COALESCE(apps.indie_score,0))", "DESC"),
        "scores_asc": ("(COALESCE(apps.opportunity_score,0)+COALESCE(apps.growth_score,0)+COALESCE(apps.indie_score,0))", "ASC"),
        "score": ("apps.score", "DESC"),
        "score_asc": ("apps.score", "ASC"),
        "real_installs": ("apps.real_installs", "DESC"),
        "real_installs_asc": ("apps.real_installs", "ASC"),
        "revenue_monthly_usd_base": ("apps.revenue_monthly_usd_base", "DESC"),
        "revenue_monthly_usd_base_asc": ("apps.revenue_monthly_usd_base", "ASC"),
        "profit_monthly_usd_base": ("apps.profit_monthly_usd_base", "DESC"),
        "profit_monthly_usd_base_asc": ("apps.profit_monthly_usd_base", "ASC"),
        "ratings": ("apps.ratings", "DESC"),
        "updated": ("apps.updated", "DESC"),
        "id": ("apps.id", "DESC"),
    }
    order_expr, order_dir = order_map.get(order, order_map["opportunity_score"])
    where = []
    params: List[Any] = []
    if run_id:
        where.append("apps.run_id = ?")
        params.append(run_id)
    if q:
        where.append("(apps.title LIKE ? OR apps.developer LIKE ? OR apps.app_id LIKE ? OR apps.categoria LIKE ?)")
        like = f"%{q}%"
        params.extend([like, like, like, like])
    if profile:
        where.append("apps.perfil_detectado = ?")
        params.append(profile)
    if min_score is not None:
        where.append("apps.score >= ?")
        params.append(min_score)
    if date_from:
        where.append("date(apps.created_at) >= date(?)")
        params.append(date_from)
    if date_to:
        where.append("date(apps.created_at) <= date(?)")
        params.append(date_to)
    clause = "WHERE " + " AND ".join(where) if where else ""
    params.append(limit)
    order_clause = f"{order_expr} IS NULL ASC, {order_expr} {order_dir}, apps.id DESC"
    with connect(db_path) as con:
        rows = con.execute(
            f"""
            SELECT apps.*,
                   runs.created_at AS run_created_at,
                   runs.level AS run_level,
                   runs.profile AS run_profile,
                   runs.scope AS run_scope
            FROM apps
            LEFT JOIN runs ON runs.id = apps.run_id
            {clause}
            ORDER BY {order_clause}
            LIMIT ?
            """,
            params,
        ).fetchall()
    return [row_to_dict(r) or {} for r in rows]


def get_app(db_path: str | Path, app_pk: int) -> Optional[Dict[str, Any]]:
    init_db(db_path)
    with connect(db_path) as con:
        row = con.execute(
            """
            SELECT apps.*,
                   runs.created_at AS run_created_at,
                   runs.level AS run_level,
                   runs.profile AS run_profile,
                   runs.scope AS run_scope
            FROM apps
            LEFT JOIN runs ON runs.id = apps.run_id
            WHERE apps.id = ?
            """,
            (app_pk,),
        ).fetchone()
    return row_to_dict(row)


def get_stats(db_path: str | Path) -> Dict[str, Any]:
    init_db(db_path)
    with connect(db_path) as con:
        runs = con.execute("SELECT COUNT(*) c FROM runs").fetchone()["c"]
        apps = con.execute("SELECT COUNT(*) c FROM apps").fetchone()["c"]
        running = con.execute("SELECT COUNT(*) c FROM runs WHERE status IN ('queued','running','pause_requested','paused','cancel_requested','delete_requested','restart_requested')").fetchone()["c"]
        paused = con.execute("SELECT COUNT(*) c FROM runs WHERE status IN ('paused','pause_requested')").fetchone()["c"]
        avg_opp = con.execute("SELECT AVG(opportunity_score) c FROM apps").fetchone()["c"] or 0
        best = con.execute("SELECT title, opportunity_score FROM apps ORDER BY opportunity_score IS NULL ASC, opportunity_score DESC LIMIT 1").fetchone()
        total_rev = con.execute("SELECT SUM(revenue_monthly_usd_base) c FROM apps").fetchone()["c"] or 0
    return {
        "runs": runs,
        "apps": apps,
        "running": running,
        "paused": paused,
        "avg_opportunity": round(avg_opp, 1),
        "best_title": best["title"] if best else "—",
        "best_score": best["opportunity_score"] if best else 0,
        "total_revenue_usd_base": round(total_rev, 2),
    }


def run_progress(db_path: str | Path, run_id: int) -> Dict[str, Any]:
    run = get_run(db_path, run_id) or {}
    if not run:
        return {}
    total = run.get("categories_total") or 0
    done = run.get("categories_done") or 0
    pct = round(done * 100 / total, 1) if total else 0
    run["progress_pct"] = pct
    run["logs"] = list_logs(db_path, run_id, 220)
    run["is_active"] = run.get("status") in RUN_ACTIVE_STATUSES
    run["can_resume"] = run.get("status") in {"paused", "pause_requested"}
    return run


def save_api_test_result(db_path: str | Path, provider: str, ok: bool, status: str, message: str, latency_ms: int = 0) -> None:
    init_db(db_path)
    with connect(db_path) as con:
        con.execute(
            "INSERT INTO api_tests(provider, ok, status, message, latency_ms, created_at) VALUES (?, ?, ?, ?, ?, ?)",
            (provider, 1 if ok else 0, status, message[:1000], int(latency_ms or 0), now_iso()),
        )


def latest_api_tests(db_path: str | Path) -> Dict[str, Dict[str, Any]]:
    init_db(db_path)
    with connect(db_path) as con:
        rows = con.execute(
            """
            SELECT t.*
            FROM api_tests t
            JOIN (SELECT provider, MAX(id) AS max_id FROM api_tests GROUP BY provider) m
              ON m.provider = t.provider AND m.max_id = t.id
            ORDER BY t.provider
            """
        ).fetchall()
    return {str(r["provider"]): (row_to_dict(r) or {}) for r in rows}


def get_api_usage_stats(db_path: str | Path) -> Dict[str, Dict[str, Any]]:
    init_db(db_path)
    aliases = {
        "ScraperAPI": ["ScraperAPI", "Scraperapi"],
        "ScrapingBee": ["ScrapingBee"],
        "Scrape.do": ["Scrape.do", "Scrapedo"],
        "Bright Data": ["Bright Data", "BrightData"],
        "Apify": ["Apify"],
        "Firecrawl": ["Firecrawl"],
        "ScrapingAnt": ["ScrapingAnt"],
        "SerpAPI": ["SerpAPI", "serpapi_json_preview"],
        "Crawlbase": ["Crawlbase"],
        "Decodo": ["Decodo", "decodo"],
        "Brave Search": ["Brave Search", "brave_search", "brave_search_json_preview"],
        "OpenWebNinja": ["OpenWebNinja"],
        "Scrapfly": ["Scrapfly", "_scrapfly"],
        "WebScraping.AI": ["WebScraping.AI", "webscraping_ai"],
        "ZenRows": ["ZenRows", "zenrows"],
        "AlterLab": ["AlterLab", "alterlab"],
        "Scavio": ["Scavio", "_scavio_raw_preview"],
        "Exa": ["Exa", "_exa_raw_preview"],
        "Tavily": ["Tavily", "_tavily_raw_preview"],
        "You.com": ["You.com", "_you_raw_preview"],
        "Jina AI": ["Jina AI", "_jina", "jina_search"],
        "DeepSeek": ["DeepSeek", "ai_provider_used"],
        "OpenRouter": ["OpenRouter", "ai_provider_used"],
        "Groq": ["Groq", "ai_provider_used"],
        "Mistral": ["Mistral", "ai_provider_used"],
        "Gemini": ["Gemini", "ai_provider_used"],
        "Fireworks": ["Fireworks", "ai_provider_used"],
        "Cohere": ["Cohere"],
        "NLPCloud": ["NLPCloud"],
        "Voyage AI": ["Voyage AI"],
        "Replicate": ["Replicate"],
        "Roboflow": ["Roboflow"],
        "SimpleScraper": ["SimpleScraper"],
        "Browse AI": ["Browse AI"],
        "AbstractAPI": ["AbstractAPI"],
        "WolframAlpha": ["WolframAlpha"],
        "Ollama": ["Ollama"],
    }
    out: Dict[str, Dict[str, Any]] = {}
    with connect(db_path) as con:
        total_apps = con.execute("SELECT COUNT(*) c FROM apps").fetchone()["c"] or 0
        for provider, needles in aliases.items():
            where_parts = []
            params: List[Any] = []
            for needle in needles:
                where_parts.append("(external_sources_used LIKE ? OR raw_json LIKE ?)")
                params.extend([f"%{needle}%", f"%{needle}%"])
            source_row = con.execute(
                f"SELECT COUNT(*) c, MAX(created_at) last_at FROM apps WHERE {' OR '.join(where_parts)}",
                params,
            ).fetchone()
            log_where = " OR ".join("message LIKE ?" for _ in needles)
            log_params = [f"%{needle}%" for needle in needles]
            log_row = con.execute(
                f"SELECT COUNT(*) c, MAX(created_at) last_at FROM logs WHERE {log_where}",
                log_params,
            ).fetchone()
            app_count = int(source_row["c"] or 0)
            log_count = int(log_row["c"] or 0)
            last_candidates = [source_row["last_at"], log_row["last_at"]]
            last_at = max([x for x in last_candidates if x] or [None])
            out[provider] = {
                "apps_enriched": app_count,
                "log_mentions": log_count,
                "call_estimate": app_count + log_count,
                "last_used_at": last_at,
                "share_pct": round((app_count * 100 / total_apps), 1) if total_apps else 0,
            }
    return out
