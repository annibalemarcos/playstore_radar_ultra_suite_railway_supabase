from __future__ import annotations

import hmac
import hashlib
import html
import json
import os
import re
import secrets
import threading
import time
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any, Dict, List, Optional
from urllib.parse import urlsplit

import requests
from flask import Flask, flash, jsonify, redirect, render_template, request, send_file, session, url_for
from werkzeug.middleware.proxy_fix import ProxyFix

from app_core.categories import (
    CATEGORIAS_APPS,
    CATEGORIAS_JOGOS,
    SUBCATEGORIAS,
    categorias_para_form,
    selecionar_categorias,
)
from app_core.config import (
    API_FIELDS,
    API_PROVIDER_GROUPS,
    ApiConfig,
    database_target,
    output_target,
    LEVELS,
    PROFILES,
    SCOPES,
    RunConfig,
    SECRET_KEEP_SENTINEL,
    load_saved_api_settings,
    mask_secret,
    save_api_settings,
    setting_source,
)
from app_core.database import (
    RUN_ACTIVE_STATUSES,
    database_backend,
    claim_next_queued_run,
    create_run,
    delete_run,
    get_app,
    get_run,
    get_stats,
    get_api_usage_stats,
    get_category_insights,
    init_db,
    list_apps,
    list_logs,
    list_runs,
    now_iso,
    ping_database,
    queue_snapshot,
    latest_api_tests,
    requeue_interrupted_runs,
    request_run_status,
    run_progress,
    save_api_test_result,
    update_run,
)
from app_core.exports import export_all_formats, export_all_separate_zip, export_run_all
from app_core.runner import run_scraper

APP_ROOT = Path(__file__).resolve().parent
LOGIN_USERNAME = os.getenv("PLAYSTORE_RADAR_LOGIN_USER", "admin").strip() or "admin"
LOGIN_PASSWORD = os.getenv("PLAYSTORE_RADAR_LOGIN_PASSWORD", "000000") or "000000"
LOGIN_SESSION_HOURS = 12


def _load_session_secret() -> str:
    """Mantém os cookies de sessão assinados com uma chave local exclusiva."""
    configured = os.getenv("PLAYSTORE_RADAR_SECRET_KEY", "").strip()
    if configured:
        return configured

    secret_file = APP_ROOT / "data" / ".session_secret"
    try:
        if secret_file.exists():
            saved = secret_file.read_text(encoding="utf-8").strip()
            if len(saved) >= 32:
                return saved
        secret_file.parent.mkdir(parents=True, exist_ok=True)
        generated = secrets.token_hex(32)
        secret_file.write_text(generated, encoding="utf-8")
        return generated
    except OSError:
        # Último recurso: a sessão continua segura, mas expira ao reiniciar o processo.
        return secrets.token_hex(32)


app = Flask(__name__)
app.wsgi_app = ProxyFix(app.wsgi_app, x_for=1, x_proto=1, x_host=1, x_port=1)
app.config.update(
    SECRET_KEY=_load_session_secret(),
    PERMANENT_SESSION_LIFETIME=timedelta(hours=LOGIN_SESSION_HOURS),
    SESSION_COOKIE_HTTPONLY=True,
    SESSION_COOKIE_SAMESITE="Lax",
    SESSION_COOKIE_SECURE=bool(os.getenv("RAILWAY_ENVIRONMENT") or os.getenv("PLAYSTORE_RADAR_COOKIE_SECURE", "").lower() in {"1", "true", "yes", "on"}),
    PREFERRED_URL_SCHEME="https" if os.getenv("RAILWAY_ENVIRONMENT") else "http",
)

ACTIVE_THREADS: Dict[int, threading.Thread] = {}
QUEUE_LOCK = threading.Lock()
QUEUE_DISPATCHER: Optional[threading.Thread] = None
QUEUE_RECOVERED = False
QUEUE_WORKER_ID = f"web-{os.getpid()}"


def db_path() -> str:
    return database_target()


def output_dir() -> Path:
    return Path(output_target())


def _safe_next_url(value: str | None) -> str | None:
    if not value:
        return None
    parts = urlsplit(value)
    if parts.scheme or parts.netloc or not value.startswith("/") or value.startswith("//"):
        return None
    return value


def _is_authenticated() -> bool:
    return bool(session.get("authenticated") and session.get("username") == LOGIN_USERNAME)


@app.before_request
def before() -> Any:
    public_endpoints = {"login", "static", "health"}
    if request.endpoint == "health":
        return None

    init_db(db_path())
    if request.endpoint != "static":
        _ensure_queue_dispatcher()
    if request.endpoint in public_endpoints:
        return None
    if _is_authenticated():
        return None

    next_url = request.full_path if request.query_string else request.path
    return redirect(url_for("login", next=_safe_next_url(next_url)))


@app.after_request
def add_security_headers(response):
    response.headers.setdefault("X-Content-Type-Options", "nosniff")
    response.headers.setdefault("X-Frame-Options", "DENY")
    response.headers.setdefault("Referrer-Policy", "same-origin")
    if request.endpoint != "static":
        response.headers["Cache-Control"] = "no-store, max-age=0"
        response.headers["Pragma"] = "no-cache"
    return response


@app.context_processor
def inject_globals() -> Dict[str, Any]:
    return {
        "LEVELS": LEVELS,
        "PROFILES": PROFILES,
        "SCOPES": SCOPES,
        "RUN_ACTIVE_STATUSES": RUN_ACTIVE_STATUSES,
        "CATEGORY_GROUPS": categorias_para_form(),
    }


def _try_json(value: Any, fallback: Any = None) -> Any:
    if value is None:
        return fallback
    if isinstance(value, (dict, list)):
        return value
    if not isinstance(value, str):
        return fallback if fallback is not None else value
    text = value.strip()
    if not text:
        return fallback
    try:
        return json.loads(text)
    except Exception:
        return fallback if fallback is not None else value


def _pretty_json(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, indent=2, sort_keys=False)


def _clean_text(value: Any, limit: int | None = None) -> str:
    if value is None:
        return ""
    text = str(value)
    text = html.unescape(text)
    text = re.sub(r"<\s*br\s*/?>", "\n", text, flags=re.I)
    text = re.sub(r"</\s*(p|div|li|h\d)\s*>", "\n", text, flags=re.I)
    text = re.sub(r"<[^>]+>", "", text)
    text = text.replace("\r\n", "\n").replace("\r", "\n")
    text = re.sub(r"[ \t]+", " ", text)
    text = re.sub(r"\n{3,}", "\n\n", text)
    text = text.strip()
    if limit and len(text) > limit:
        return text[:limit].rstrip() + "…"
    return text


def _compact_number(value: Any) -> str:
    try:
        n = int(float(value or 0))
    except Exception:
        return "0"
    if n >= 1_000_000:
        return f"{n/1_000_000:.1f} mi".replace(".0", "")
    if n >= 1_000:
        return f"{n/1_000:.1f} mil".replace(".0", "")
    return str(n)


def _money(value: Any, prefix: str = "US$") -> str:
    try:
        n = float(value or 0)
    except Exception:
        n = 0.0
    if n >= 1_000_000:
        return f"{prefix} {n/1_000_000:.2f} mi"
    if n >= 1_000:
        return f"{prefix} {n:,.0f}".replace(",", ".")
    return f"{prefix} {n:.2f}"


def _split_sources(value: Any) -> List[str]:
    if isinstance(value, list):
        return [str(x) for x in value if x]
    if not value:
        return []
    return [x.strip() for x in str(value).split(",") if x.strip()]


def _cfg_from_run(run: Dict[str, Any]) -> RunConfig:
    raw_cfg = _try_json(run.get("config_json"), {}) or {}
    cfg = RunConfig.from_dict(raw_cfg)
    cfg.db_path = db_path()
    cfg.output_dir = str(output_dir())
    cfg.apply_level_defaults(ApiConfig())
    return cfg


def _csv_items(value: Any) -> List[str]:
    if isinstance(value, (list, tuple, set)):
        raw = ",".join(str(item) for item in value)
    else:
        raw = str(value or "")
    return [item.strip().upper() for item in raw.replace(";", ",").split(",") if item.strip()]


def _yes_no(value: Any) -> str:
    return "sim" if bool(value) else "não"


def _run_search_summary(run: Dict[str, Any]) -> Dict[str, Any]:
    cfg = _cfg_from_run(run)
    category_name_by_code = {
        code.upper(): name
        for code, name, _term in [*CATEGORIAS_APPS.values(), *CATEGORIAS_JOGOS.values()]
    }
    subcategory_name_by_token = {
        f"{category_code.upper()}::{sub_code.upper()}": f"{category_name_by_code.get(category_code.upper(), category_code)} · {sub_name}"
        for category_code, subcats in SUBCATEGORIAS.items()
        for sub_code, sub_name, _term in subcats
    }

    category_codes = _csv_items(cfg.category_codes)
    subcategory_codes = _csv_items(cfg.subcategory_codes)
    category_names = [category_name_by_code.get(code, code) for code in category_codes]
    subcategory_names = [subcategory_name_by_token.get(code, code) for code in subcategory_codes]

    if cfg.search_query:
        search_mode = "Palavra-chave"
        main_context = f'Busca livre por "{cfg.search_query}"'
        filter_context = "Escopo e categorias foram ignorados porque a busca foi feita por termo."
        target_categories: List[Dict[str, str]] = []
        category_detail = "ignorado na busca por termo"
        subcategory_detail = "ignorado na busca por termo"
    else:
        search_mode = "Categorias"
        selected_targets = selecionar_categorias(cfg.scope, cfg.category_codes, cfg.subcategory_codes)
        if cfg.max_categories:
            selected_targets = selected_targets[: cfg.max_categories]
        target_categories = [
            {"code": code, "name": name, "term": term}
            for code, name, term in selected_targets
        ]
        if cfg.scope == "TODAS":
            main_context = "Todas as categorias de apps e jogos"
        elif subcategory_names:
            main_context = ", ".join(subcategory_names)
        elif category_names:
            main_context = ", ".join(category_names)
        else:
            main_context = f"Todas as categorias de {SCOPES.get(cfg.scope, cfg.scope).lower()}"
        filter_context = f"{len(target_categories)} alvo(s) efetivos na coleta."
        category_detail = ", ".join(category_names) if category_names else "todas do escopo"
        subcategory_detail = ", ".join(subcategory_names) if subcategory_names else "nenhuma"

    categories_total = int(run.get("categories_total") or len(target_categories) or (1 if cfg.search_query else 0))
    categories_done = int(run.get("categories_done") or 0)
    progress_pct = round((categories_done * 100 / categories_total), 1) if categories_total else 0
    if int(progress_pct) == progress_pct:
        progress_pct = int(progress_pct)

    detail_rows = [
        {"label": "Tipo de busca", "value": search_mode},
        {"label": "Palavra-chave", "value": cfg.search_query or "não usada"},
        {"label": "Escopo", "value": f"{cfg.scope} · {SCOPES.get(cfg.scope, cfg.scope)}"},
        {"label": "Categorias marcadas", "value": category_detail},
        {"label": "Subcategorias marcadas", "value": subcategory_detail},
        {"label": "Quantidade", "value": f"{cfg.quantity} apps/categoria"},
        {"label": "Máx. categorias", "value": str(cfg.max_categories) if cfg.max_categories else "todas"},
        {"label": "Detalhes por categoria", "value": str(cfg.detail_limit or cfg.quantity)},
        {"label": "Reviews por app", "value": str(cfg.reviews_per_app or 0)},
        {"label": "Apps pagos", "value": _yes_no(cfg.include_paid_apps)},
        {"label": "HTML exportável", "value": _yes_no(cfg.open_html)},
        {"label": "País / idioma", "value": f"{cfg.country.upper()} / {cfg.lang}"},
        {"label": "Câmbio", "value": f"US$ 1 = R$ {cfg.exchange_rate_brl:.2f}"},
    ]

    return {
        "cfg": cfg,
        "progress_pct": progress_pct,
        "search_mode": search_mode,
        "main_context": main_context,
        "filter_context": filter_context,
        "category_names": category_names,
        "subcategory_names": subcategory_names,
        "target_categories": target_categories,
        "target_preview": target_categories[:12],
        "target_more_count": max(0, len(target_categories) - 12),
        "detail_rows": detail_rows,
    }


def _queue_max_workers() -> int:
    try:
        return max(1, int(os.getenv("PLAYSTORE_RADAR_MAX_WORKERS", "1")))
    except ValueError:
        return 1


def _queue_info() -> Dict[str, Any]:
    info = queue_snapshot(db_path())
    info["max_workers"] = _queue_max_workers()
    return info


def _cleanup_active_threads() -> None:
    for run_id, thread in list(ACTIVE_THREADS.items()):
        if not thread.is_alive():
            ACTIVE_THREADS.pop(run_id, None)


def _run_worker_thread(run_id: int, cfg: RunConfig, api: Optional[ApiConfig] = None) -> None:
    api = api or ApiConfig()
    try:
        run_scraper(cfg, api=api, run_id=run_id)
    except Exception as exc:  # noqa: BLE001
        update_run(cfg.db_path, run_id, status="failed", finished_at=now_iso(), last_message=str(exc), errors_count=1)
    finally:
        ACTIVE_THREADS.pop(run_id, None)


def _spawn_worker(run_id: int, cfg: RunConfig, api: Optional[ApiConfig] = None) -> None:
    t = threading.Thread(target=_run_worker_thread, args=(run_id, cfg, api), name=f"run-worker-{run_id}", daemon=True)
    ACTIVE_THREADS[run_id] = t
    t.start()


def _dispatch_queue_once() -> None:
    with QUEUE_LOCK:
        _cleanup_active_threads()
        while len(ACTIVE_THREADS) < _queue_max_workers():
            run = claim_next_queued_run(db_path(), QUEUE_WORKER_ID)
            if not run:
                break
            cfg = _cfg_from_run(run)
            api = ApiConfig()
            cfg.apply_level_defaults(api)
            _spawn_worker(int(run["id"]), cfg, api)


def _queue_loop() -> None:
    while True:
        try:
            _dispatch_queue_once()
        except Exception:
            pass
        time.sleep(1.5)


def _ensure_queue_dispatcher() -> None:
    global QUEUE_DISPATCHER, QUEUE_RECOVERED
    if not QUEUE_RECOVERED:
        with QUEUE_LOCK:
            if not QUEUE_RECOVERED:
                requeue_interrupted_runs(db_path())
                QUEUE_RECOVERED = True
    if QUEUE_DISPATCHER and QUEUE_DISPATCHER.is_alive():
        return
    QUEUE_DISPATCHER = threading.Thread(target=_queue_loop, name="run-queue-dispatcher", daemon=True)
    QUEUE_DISPATCHER.start()


def _create_and_enqueue_run(cfg: RunConfig, parent_run_id: Optional[int] = None) -> int:
    cfg.db_path = db_path()
    cfg.output_dir = str(output_dir())
    api = ApiConfig()
    cfg.apply_level_defaults(api)
    run_id = create_run(cfg, status="queued", parent_run_id=parent_run_id)
    _ensure_queue_dispatcher()
    _dispatch_queue_once()
    return run_id


def _is_active(run: Dict[str, Any] | None) -> bool:
    return bool(run and run.get("status") in RUN_ACTIVE_STATUSES)


def build_app_view(app_row: Dict[str, Any], raw: Dict[str, Any]) -> Dict[str, Any]:
    """Cria uma visão humana da página de app. Nada de despejar JSON cru na cara do usuário."""
    reviews = _try_json(app_row.get("review_samples_json"), []) or raw.get("review_samples") or []
    keywords = _try_json(app_row.get("review_keywords_json"), []) or raw.get("review_keywords") or []
    screenshots = _try_json(app_row.get("screenshots_json"), []) or raw.get("screenshots") or []
    sources = _split_sources(app_row.get("external_sources_used") or raw.get("external_sources_used"))

    description = _clean_text(app_row.get("description") or raw.get("description"))
    external_preview = _clean_text(app_row.get("external_markdown_preview") or raw.get("external_markdown_preview"), 1800)

    monetization = []
    if app_row.get("contains_ads") or raw.get("containsAds"):
        monetization.append("tem anúncios")
    if app_row.get("offers_iap") or raw.get("offersIAP"):
        monetization.append("tem compras no app")
    if app_row.get("price") not in (None, "", 0, "0"):
        monetization.append(f"app pago/preço informado: {app_row.get('price')}")
    if not monetization:
        monetization.append("sem monetização clara nos dados coletados")

    score = app_row.get("score") or raw.get("score")
    installs = app_row.get("real_installs") or app_row.get("min_installs") or raw.get("realInstalls") or raw.get("minInstalls")
    ratings = app_row.get("ratings") or raw.get("ratings") or app_row.get("reviews") or raw.get("reviews")
    opportunity = app_row.get("opportunity_score") or 0
    indie = app_row.get("indie_score") or 0
    growth = app_row.get("growth_score") or 0

    human_lines = []
    human_lines.append(
        f"É um app de {app_row.get('categoria') or app_row.get('genre') or 'categoria não identificada'} feito por {app_row.get('developer') or 'desenvolvedor não informado'}."
    )
    human_lines.append(
        f"O radar marcou {opportunity}/100 em oportunidade, {indie}/100 em perfil indie e {growth}/100 em crescimento."
    )
    if installs:
        human_lines.append(f"Tração pública aproximada: {_compact_number(installs)} instalações/downloads detectados.")
    if score:
        human_lines.append(f"Nota média: {score}; avaliações/sinais públicos: {_compact_number(ratings)}.")
    human_lines.append("Monetização detectada: " + ", ".join(monetization) + ".")
    if keywords:
        human_lines.append("Palavras fortes em reviews: " + ", ".join([str(k) for k in keywords[:10]]) + ".")

    facts = [
        ("Categoria", app_row.get("categoria") or app_row.get("genre") or "N/A"),
        ("Perfil", app_row.get("perfil_detectado") or "N/A"),
        ("Instalações", app_row.get("installs") or _compact_number(installs)),
        ("Instalações reais", _compact_number(app_row.get("real_installs") or 0)),
        ("Avaliações", _compact_number(ratings or 0)),
        ("Última atualização", app_row.get("updated") or raw.get("lastUpdatedOn") or "N/A"),
        ("Coletado em", app_row.get("created_at") or "N/A"),
        ("Run", f"#{app_row.get('run_id')}" if app_row.get("run_id") else "N/A"),
    ]

    financial = [
        ("Receita base", _money(app_row.get("revenue_monthly_usd_base"))),
        ("Receita baixa", _money(app_row.get("revenue_monthly_usd_low"))),
        ("Receita alta", _money(app_row.get("revenue_monthly_usd_high"))),
        ("Lucro base", _money(app_row.get("profit_monthly_usd_base"))),
        ("Lucro base BRL", _money(app_row.get("profit_monthly_brl_base"), "R$")),
        ("Confiança", app_row.get("financial_confidence") or "N/A"),
    ]

    external_fetch_meta = _try_json(raw.get("external_fetch_meta"), None)
    serpapi_preview = _try_json(raw.get("serpapi_json_preview"), None)
    brave_preview = _try_json(raw.get("brave_search_json_preview"), None)

    raw_clean = dict(raw)
    for noisy_key in ["external_fetch_meta", "serpapi_json_preview", "brave_search_json_preview"]:
        if isinstance(raw_clean.get(noisy_key), str) and len(raw_clean[noisy_key]) > 4000:
            raw_clean[noisy_key] = raw_clean[noisy_key][:4000] + "… [cortado para visualização]"

    return {
        "human_summary": "\n".join(human_lines),
        "description": description,
        "external_preview": external_preview,
        "facts": facts,
        "financial": financial,
        "monetization": monetization,
        "keywords": keywords[:18],
        "reviews": reviews[:8] if isinstance(reviews, list) else [],
        "screenshots": screenshots[:12] if isinstance(screenshots, list) else [],
        "sources": sources,
        "ai_provider": raw.get("ai_provider_used"),
        "ai_brief": _clean_text(raw.get("ai_opportunity_brief")),
        "raw_pretty": _pretty_json(raw_clean),
        "external_fetch_pretty": _pretty_json(external_fetch_meta) if isinstance(external_fetch_meta, (dict, list)) else "",
        "serpapi_pretty": _pretty_json(serpapi_preview) if isinstance(serpapi_preview, (dict, list)) else "",
        "brave_pretty": _pretty_json(brave_preview) if isinstance(brave_preview, (dict, list)) else "",
    }


PROVIDER_ORDER = []
for _providers in API_PROVIDER_GROUPS.values():
    for _provider in _providers:
        if _provider not in PROVIDER_ORDER:
            PROVIDER_ORDER.append(_provider)


TEST_URL = "https://geo.brdtest.com/welcome.txt?product=unlocker&method=api"
_API_DASHBOARD_STATS_LOCK = threading.Lock()
_API_DASHBOARD_STATS_CACHE: Dict[str, Any] = {
    "loaded_at": 0.0,
    "refreshing": False,
    "usage": {},
    "tests": {},
}


def _refresh_api_dashboard_stats() -> None:
    usage: Dict[str, Dict[str, Any]] = {}
    tests: Dict[str, Dict[str, Any]] = {}
    try:
        usage = get_api_usage_stats(db_path())
        tests = latest_api_tests(db_path())
    except Exception:
        pass
    with _API_DASHBOARD_STATS_LOCK:
        _API_DASHBOARD_STATS_CACHE.update(
            {
                "loaded_at": time.time(),
                "refreshing": False,
                "usage": usage,
                "tests": tests,
            }
        )


def _api_dashboard_stats(max_age_seconds: int = 60) -> tuple[Dict[str, Dict[str, Any]], Dict[str, Dict[str, Any]]]:
    with _API_DASHBOARD_STATS_LOCK:
        loaded_at = float(_API_DASHBOARD_STATS_CACHE.get("loaded_at") or 0)
        is_fresh = bool(loaded_at and (time.time() - loaded_at) < max_age_seconds)
        usage = dict(_API_DASHBOARD_STATS_CACHE.get("usage") or {})
        tests = dict(_API_DASHBOARD_STATS_CACHE.get("tests") or {})
        if is_fresh:
            return usage, tests
        should_load_now = not loaded_at
        if not _API_DASHBOARD_STATS_CACHE.get("refreshing"):
            _API_DASHBOARD_STATS_CACHE["refreshing"] = True
            if not should_load_now:
                threading.Thread(target=_refresh_api_dashboard_stats, name="api-dashboard-stats", daemon=True).start()
    if should_load_now:
        _refresh_api_dashboard_stats()
        with _API_DASHBOARD_STATS_LOCK:
            usage = dict(_API_DASHBOARD_STATS_CACHE.get("usage") or {})
            tests = dict(_API_DASHBOARD_STATS_CACHE.get("tests") or {})
    return usage, tests


def _remember_api_test_result(result: Dict[str, Any]) -> None:
    provider = str(result.get("provider") or "")
    if not provider:
        return
    with _API_DASHBOARD_STATS_LOCK:
        tests = dict(_API_DASHBOARD_STATS_CACHE.get("tests") or {})
        tests[provider] = {
            "provider": provider,
            "ok": bool(result.get("ok")),
            "status": result.get("status") or "",
            "message": result.get("message") or "",
            "latency_ms": int(result.get("latency_ms") or 0),
            "diagnostics_json": json.dumps(result.get("diagnostics") or {}, ensure_ascii=False),
            "created_at": now_iso(),
        }
        _API_DASHBOARD_STATS_CACHE["tests"] = tests


def api_field_rows() -> List[Dict[str, Any]]:
    api = ApiConfig()
    rows: List[Dict[str, Any]] = []
    for field in API_FIELDS:
        attr = str(field["attr"])
        env_name = str(field["env"])
        value = getattr(api, attr, "") or ""
        source = setting_source(attr, env_name)
        is_secret = field.get("secret", True)
        has_value = bool(value)
        hide_value = bool(is_secret and has_value)
        rows.append(
            {
                **field,
                "value": value,
                "masked": mask_secret(value) if is_secret else value,
                "display_value": SECRET_KEEP_SENTINEL if hide_value else value,
                "display_placeholder": "Valor oculto por seguranca" if hide_value else field.get("placeholder", ""),
                "source": source,
                "source_slug": "env" if source == ".env" else source,
                "is_env": source == ".env",
                "is_secret": is_secret,
                "is_masked_secret": hide_value,
            }
        )
    return rows


def _short_diag_value(value: Any, max_len: int = 90) -> str:
    if isinstance(value, bool):
        return "sim" if value else "nao"
    if isinstance(value, (int, float)):
        return f"{value:g}" if isinstance(value, float) else str(value)
    text = re.sub(r"\s+", " ", str(value or "")).strip()
    if len(text) > max_len:
        return text[: max_len - 1].rstrip() + "..."
    return text


def _is_interesting_diagnostic_key(key: str) -> bool:
    normalized = re.sub(r"[^a-z0-9]+", "_", key.lower()).strip("_")
    blocked = ("token", "secret", "password", "passwd", "apikey", "api_key", "authorization", "credential", "email")
    if any(part in normalized for part in blocked):
        return False
    interesting = (
        "balance", "saldo", "credit", "credits", "quota", "limit", "remaining", "remain", "usage",
        "used", "available", "plan", "subscription", "requests", "request_count", "monthly", "reset",
        "rate", "status",
    )
    return any(part in normalized for part in interesting)


def _collect_response_diagnostics(data: Any, prefix: str = "", depth: int = 0) -> List[Dict[str, str]]:
    if depth > 3:
        return []
    items: List[Dict[str, str]] = []
    if isinstance(data, dict):
        for key, value in data.items():
            label = f"{prefix}.{key}" if prefix else str(key)
            if isinstance(value, (dict, list)):
                items.extend(_collect_response_diagnostics(value, label, depth + 1))
            elif _is_interesting_diagnostic_key(label):
                rendered = _short_diag_value(value)
                if rendered:
                    items.append({"label": label, "value": rendered})
    elif isinstance(data, list):
        for index, value in enumerate(data[:5]):
            items.extend(_collect_response_diagnostics(value, f"{prefix}[{index}]", depth + 1))
    return items


def _response_diagnostics(response: Optional[requests.Response]) -> Dict[str, Any]:
    if response is None:
        return {}
    items: List[Dict[str, str]] = []
    header_labels = {
        "x-ratelimit-limit": "rate_limit",
        "x-ratelimit-remaining": "rate_remaining",
        "x-ratelimit-reset": "rate_reset",
        "ratelimit-limit": "rate_limit",
        "ratelimit-remaining": "rate_remaining",
        "ratelimit-reset": "rate_reset",
        "retry-after": "retry_after",
        "x-scraperapi-remaining": "scraperapi_remaining",
        "spb-cost": "scrapingbee_cost",
        "spb-initial-status-code": "scrapingbee_initial_status",
    }
    for header, label in header_labels.items():
        value = response.headers.get(header)
        if value:
            items.append({"label": label, "value": _short_diag_value(value)})
    try:
        items.extend(_collect_response_diagnostics(response.json()))
    except Exception:
        pass
    deduped: List[Dict[str, str]] = []
    seen: set[tuple[str, str]] = set()
    for item in items:
        pair = (item.get("label", ""), item.get("value", ""))
        if pair in seen:
            continue
        seen.add(pair)
        deduped.append(item)
    return {"items": deduped[:10]} if deduped else {}


def _diagnostic_items(raw: Any) -> List[Dict[str, str]]:
    data = _try_json(raw, {}) or {}
    if not isinstance(data, dict):
        return []
    items = data.get("items") or []
    clean: List[Dict[str, str]] = []
    if isinstance(items, list):
        for item in items:
            if not isinstance(item, dict):
                continue
            label = _short_diag_value(item.get("label"), 44)
            value = _short_diag_value(item.get("value"), 90)
            if label and value:
                clean.append({"label": label, "value": value})
    return clean[:6]


def _balance_label(items: List[Dict[str, str]]) -> str:
    priority = ("balance", "saldo", "credit", "credits", "quota", "remaining", "remain", "available", "usage")
    for item in items:
        label = str(item.get("label") or "").lower()
        if any(word in label for word in priority):
            return f"{item.get('label')}: {item.get('value')}"
    return "nao informado"


def _redact_api_message(message: Any, api: ApiConfig) -> str:
    text = str(message or "")
    for field in API_FIELDS:
        if not field.get("secret", True):
            continue
        value = getattr(api, str(field.get("attr")), "") or ""
        if len(value) >= 6:
            text = text.replace(value, "[oculto]")
    text = re.sub(r"(?i)((?:api[_-]?key|apikey|token|access_token|secret|password)=)[^&\s]+", r"\1[oculto]", text)
    text = re.sub(r"(?i)(Authorization:\s*(?:Bearer|Token|Basic)\s+)[^\s,;]+", r"\1[oculto]", text)
    text = re.sub(r"(?i)((?:Bearer|Token|Basic)\s+)[A-Za-z0-9._:\-]{12,}", r"\1[oculto]", text)
    return text[:500]


def api_cards() -> List[Dict[str, Any]]:
    api = ApiConfig()
    availability = api.available()
    usage, latest_tests = _api_dashboard_stats()
    rows = api_field_rows()
    fields_by_provider: Dict[str, List[Dict[str, Any]]] = {}
    for row in rows:
        fields_by_provider.setdefault(str(row["provider"]), []).append(row)
    cards: List[Dict[str, Any]] = []
    for provider in PROVIDER_ORDER:
        fields = fields_by_provider.get(provider, [])
        sources = sorted({f["source"] for f in fields if f.get("value")})
        test = dict(latest_tests.get(provider, {}) or {})
        diagnostics = _diagnostic_items(test.get("diagnostics_json"))
        if test:
            test["diagnostics"] = diagnostics
            test["balance_label"] = _balance_label(diagnostics)
        use = usage.get(provider, {})
        cards.append(
            {
                "provider": provider,
                "group": next((g for g, names in API_PROVIDER_GROUPS.items() if provider in names), "Outros"),
                "configured": bool(availability.get(provider)),
                "sources": ", ".join(sources) if sources else "vazio",
                "fields": fields,
                "test": test,
                "usage": use,
                "last_used_at": use.get("last_used_at") or "",
            }
        )
    return cards


def quick_api_cards() -> List[Dict[str, Any]]:
    api = ApiConfig()
    availability = api.available()
    try:
        latest_tests = latest_api_tests(db_path())
    except Exception:
        latest_tests = {}
    cards: List[Dict[str, Any]] = []
    for provider in PROVIDER_ORDER:
        test = dict(latest_tests.get(provider, {}) or {})
        diagnostics = _diagnostic_items(test.get("diagnostics_json"))
        if test:
            test["diagnostics"] = diagnostics
            test["balance_label"] = _balance_label(diagnostics)
        cards.append(
            {
                "provider": provider,
                "group": next((g for g, names in API_PROVIDER_GROUPS.items() if provider in names), "Outros"),
                "configured": bool(availability.get(provider)),
                "sources": ".env/painel" if availability.get(provider) else "vazio",
                "test": test,
                "usage": {},
                "last_used_at": "",
            }
        )
    return cards


def api_diagnostic_summary(cards: List[Dict[str, Any]]) -> Dict[str, Any]:
    configured = [card for card in cards if card.get("configured")]
    tested = [card for card in configured if card.get("test")]
    working = [card for card in tested if card.get("test", {}).get("ok")]
    failed = [card for card in tested if not card.get("test", {}).get("ok")]
    latencies = [int(card.get("test", {}).get("latency_ms") or 0) for card in tested if int(card.get("test", {}).get("latency_ms") or 0) > 0]
    last_tests = [str(card.get("test", {}).get("created_at") or "") for card in tested if card.get("test", {}).get("created_at")]
    last_uses = [str(card.get("usage", {}).get("last_used_at") or "") for card in cards if card.get("usage", {}).get("last_used_at")]
    return {
        "total": len(cards),
        "configured": len(configured),
        "working": len(working),
        "failed": len(failed),
        "untested": max(0, len(configured) - len(tested)),
        "avg_latency_ms": round(sum(latencies) / len(latencies)) if latencies else 0,
        "last_test_at": max(last_tests) if last_tests else "",
        "last_used_at": max(last_uses) if last_uses else "",
    }


def _score_label(value: Any) -> str:
    try:
        return f"{int(round(float(value or 0)))}/100"
    except Exception:
        return "0/100"


def _dashboard_app(app_row: Dict[str, Any], metric_key: str, metric_label: str, money_metric: bool = False) -> Dict[str, Any]:
    metric_raw = app_row.get(metric_key)
    return {
        "id": app_row.get("id"),
        "title": app_row.get("title") or "Sem titulo",
        "developer": app_row.get("developer") or "",
        "category": app_row.get("categoria") or app_row.get("genre") or "Sem categoria",
        "icon": app_row.get("icon"),
        "metric_label": metric_label,
        "metric_value": _money(metric_raw) if money_metric else _score_label(metric_raw),
        "score_line": (
            f"opp {_score_label(app_row.get('opportunity_score'))} | "
            f"grow {_score_label(app_row.get('growth_score'))} | "
            f"indie {_score_label(app_row.get('indie_score'))}"
        ),
    }


def _category_insights() -> List[Dict[str, Any]]:
    return [
        {
            **item,
            "revenue": _money(item.get("revenue")),
            "top_app": item.get("top_app") or "Sem destaque",
        }
        for item in get_category_insights(db_path(), limit=6)
    ]


def dashboard_insights(runs: List[Dict[str, Any]], cards: List[Dict[str, Any]]) -> Dict[str, Any]:
    top_opportunities = [_dashboard_app(app, "opportunity_score", "oportunidade") for app in list_apps(db_path(), order="opportunity_score", limit=5)]
    top_growth = [_dashboard_app(app, "growth_score", "crescimento") for app in list_apps(db_path(), order="growth_score", limit=5)]
    revenue_apps = [
        app for app in list_apps(db_path(), order="revenue_monthly_usd_base", limit=25)
        if float(app.get("revenue_monthly_usd_base") or 0) > 0
    ][:5]
    top_revenue = [_dashboard_app(app, "revenue_monthly_usd_base", "receita/mes", True) for app in revenue_apps]
    run_alerts = [
        run for run in runs
        if run.get("status") in {"failed", "finished_with_warnings"} or int(run.get("errors_count") or 0) > 0
    ][:5]
    api_failures = [
        card for card in cards
        if card.get("configured") and card.get("test") and not card.get("test", {}).get("ok")
    ][:5]
    return {
        "top_opportunities": top_opportunities,
        "top_growth": top_growth,
        "top_revenue": top_revenue,
        "categories": _category_insights(),
        "run_alerts": run_alerts,
        "api_failures": api_failures,
        "api_summary": api_diagnostic_summary(cards),
    }


def _compare_app_key(app_row: Dict[str, Any]) -> str:
    app_id = str(app_row.get("app_id") or "").strip().lower()
    if app_id:
        return f"id:{app_id}"
    title = normalize_for_compare(app_row.get("title"))
    developer = normalize_for_compare(app_row.get("developer"))
    return f"text:{title}|{developer}"


def normalize_for_compare(value: Any) -> str:
    text = re.sub(r"\s+", " ", str(value or "").lower()).strip()
    return text


def _score_total(app_row: Dict[str, Any]) -> float:
    return (
        float(app_row.get("opportunity_score") or 0)
        + float(app_row.get("growth_score") or 0)
        + float(app_row.get("indie_score") or 0)
    )


def _compare_app_view(app_row: Dict[str, Any], other: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
    other = other or {}
    revenue = float(app_row.get("revenue_monthly_usd_base") or 0)
    other_revenue = float(other.get("revenue_monthly_usd_base") or 0)
    score_total = _score_total(app_row)
    other_score_total = _score_total(other)
    return {
        "id": app_row.get("id"),
        "title": app_row.get("title") or "Sem titulo",
        "developer": app_row.get("developer") or "",
        "category": app_row.get("categoria") or app_row.get("genre") or "Sem categoria",
        "icon": app_row.get("icon"),
        "score": app_row.get("score") or "N/A",
        "installs": _compact_number(app_row.get("real_installs") or app_row.get("min_installs") or 0),
        "opportunity": int(app_row.get("opportunity_score") or 0),
        "growth": int(app_row.get("growth_score") or 0),
        "indie": int(app_row.get("indie_score") or 0),
        "score_total": round(score_total, 1),
        "score_delta": round(score_total - other_score_total, 1),
        "revenue": _money(revenue),
        "revenue_raw": revenue,
        "revenue_delta": _money(revenue - other_revenue),
        "revenue_delta_raw": round(revenue - other_revenue, 2),
        "confidence": app_row.get("financial_confidence") or "",
    }


def _category_compare(base_apps: List[Dict[str, Any]], target_apps: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    def bucket(apps: List[Dict[str, Any]]) -> Dict[str, Dict[str, float]]:
        grouped: Dict[str, Dict[str, float]] = {}
        for app_row in apps:
            category = app_row.get("categoria") or app_row.get("genre") or "Sem categoria"
            item = grouped.setdefault(category, {"count": 0, "score": 0.0, "revenue": 0.0})
            item["count"] += 1
            item["score"] += _score_total(app_row)
            item["revenue"] += float(app_row.get("revenue_monthly_usd_base") or 0)
        return grouped

    base = bucket(base_apps)
    target = bucket(target_apps)
    rows: List[Dict[str, Any]] = []
    for category in sorted(set(base) | set(target)):
        b = base.get(category, {"count": 0, "score": 0.0, "revenue": 0.0})
        t = target.get(category, {"count": 0, "score": 0.0, "revenue": 0.0})
        b_avg = b["score"] / b["count"] if b["count"] else 0
        t_avg = t["score"] / t["count"] if t["count"] else 0
        rows.append(
            {
                "category": category,
                "base_count": int(b["count"]),
                "target_count": int(t["count"]),
                "count_delta": int(t["count"] - b["count"]),
                "base_avg": round(b_avg, 1),
                "target_avg": round(t_avg, 1),
                "score_delta": round(t_avg - b_avg, 1),
                "base_revenue": _money(b["revenue"]),
                "target_revenue": _money(t["revenue"]),
                "revenue_delta": _money(t["revenue"] - b["revenue"]),
                "revenue_delta_raw": round(t["revenue"] - b["revenue"], 2),
            }
        )
    return sorted(rows, key=lambda row: (abs(row["score_delta"]), abs(row["revenue_delta_raw"]), row["target_count"]), reverse=True)


def build_run_comparison(base_id: int, target_id: int) -> Dict[str, Any]:
    base_run = get_run(db_path(), base_id) or {}
    target_run = get_run(db_path(), target_id) or {}
    if not base_run or not target_run:
        return {}
    base_apps = list_apps(db_path(), run_id=base_id, order="scores", limit=50_000)
    target_apps = list_apps(db_path(), run_id=target_id, order="scores", limit=50_000)
    base_map = {_compare_app_key(app): app for app in base_apps}
    target_map = {_compare_app_key(app): app for app in target_apps}
    new_keys = sorted(set(target_map) - set(base_map), key=lambda key: _score_total(target_map[key]), reverse=True)
    removed_keys = sorted(set(base_map) - set(target_map), key=lambda key: _score_total(base_map[key]), reverse=True)
    common_keys = sorted(set(base_map) & set(target_map), key=lambda key: _score_total(target_map[key]) - _score_total(base_map[key]), reverse=True)
    base_revenue = sum(float(app.get("revenue_monthly_usd_base") or 0) for app in base_apps)
    target_revenue = sum(float(app.get("revenue_monthly_usd_base") or 0) for app in target_apps)
    base_score = sum(_score_total(app) for app in base_apps) / len(base_apps) if base_apps else 0
    target_score = sum(_score_total(app) for app in target_apps) / len(target_apps) if target_apps else 0
    common_views = [_compare_app_view(target_map[key], base_map[key]) for key in common_keys]
    improved = [app for app in common_views if app["score_delta"] > 0 or app["revenue_delta_raw"] > 0]
    declined = sorted(common_views, key=lambda app: (app["score_delta"], app["revenue_delta_raw"]))[:25]
    removed_apps = []
    for key in removed_keys[:50]:
        view = _compare_app_view(base_map[key])
        view["score_delta"] = -abs(view["score_total"])
        view["revenue_delta_raw"] = -abs(view["revenue_raw"])
        view["revenue_delta"] = _money(view["revenue_delta_raw"])
        removed_apps.append(view)
    return {
        "base_run": base_run,
        "target_run": target_run,
        "base_count": len(base_apps),
        "target_count": len(target_apps),
        "new_count": len(new_keys),
        "removed_count": len(removed_keys),
        "common_count": len(common_keys),
        "base_revenue": _money(base_revenue),
        "target_revenue": _money(target_revenue),
        "revenue_delta": _money(target_revenue - base_revenue),
        "revenue_delta_raw": round(target_revenue - base_revenue, 2),
        "base_score": round(base_score, 1),
        "target_score": round(target_score, 1),
        "score_delta": round(target_score - base_score, 1),
        "new_apps": [_compare_app_view(target_map[key]) for key in new_keys[:50]],
        "removed_apps": removed_apps,
        "improved_apps": improved[:50],
        "declined_apps": declined,
        "categories": _category_compare(base_apps, target_apps)[:50],
    }


def _status_message(response: requests.Response, max_len: int = 260) -> str:
    text = ""
    try:
        data = response.json()
        if isinstance(data, dict):
            errors = data.get("errors")
            if isinstance(errors, list) and errors:
                first_error = errors[0]
                if isinstance(first_error, dict):
                    text = str(first_error.get("message") or first_error.get("error") or "")
                else:
                    text = str(first_error)
            messages = data.get("messages")
            if not text and isinstance(messages, list) and messages:
                first_message = messages[0]
                if isinstance(first_message, dict):
                    text = str(first_message.get("message") or first_message.get("code") or "")
                else:
                    text = str(first_message)
            result = data.get("result")
            if not text and isinstance(result, dict) and result.get("status"):
                text = str(result.get("status"))
            for key in ("message", "error", "status", "name", "username"):
                if not text and data.get(key):
                    text = str(data.get(key))
                    break
            if not text:
                text = json.dumps(data, ensure_ascii=False)[:max_len]
        else:
            text = str(data)[:max_len]
    except Exception:
        text = (response.text or "")[:max_len]
    text = re.sub(r"\s+", " ", text).strip()
    return text or f"HTTP {response.status_code}"


def _aws_signing_key(secret: str, date_stamp: str, region: str = "auto", service: str = "s3") -> bytes:
    key_date = hmac.new(("AWS4" + secret).encode("utf-8"), date_stamp.encode("utf-8"), hashlib.sha256).digest()
    key_region = hmac.new(key_date, region.encode("utf-8"), hashlib.sha256).digest()
    key_service = hmac.new(key_region, service.encode("utf-8"), hashlib.sha256).digest()
    return hmac.new(key_service, b"aws4_request", hashlib.sha256).digest()


def _cloudflare_r2_test_response(api: ApiConfig, session: requests.Session) -> requests.Response:
    if not api.cloudflare_r2_access_key_id or not api.cloudflare_r2_secret_access_key or not api.cloudflare_r2_endpoint:
        raise ValueError("CLOUDFLARE_R2_ACCESS_KEY_ID, CLOUDFLARE_R2_SECRET_ACCESS_KEY ou CLOUDFLARE_R2_ENDPOINT vazio")

    endpoint = api.cloudflare_r2_endpoint.rstrip("/")
    parts = urlsplit(endpoint)
    if not parts.scheme or not parts.netloc:
        raise ValueError("CLOUDFLARE_R2_ENDPOINT inválido")

    amz_date = datetime.utcnow().strftime("%Y%m%dT%H%M%SZ")
    date_stamp = amz_date[:8]
    payload_hash = hashlib.sha256(b"").hexdigest()
    canonical_headers = (
        f"host:{parts.netloc}\n"
        f"x-amz-content-sha256:{payload_hash}\n"
        f"x-amz-date:{amz_date}\n"
    )
    signed_headers = "host;x-amz-content-sha256;x-amz-date"
    canonical_request = "\n".join(["GET", "/", "", canonical_headers, signed_headers, payload_hash])
    credential_scope = f"{date_stamp}/auto/s3/aws4_request"
    string_to_sign = "\n".join([
        "AWS4-HMAC-SHA256",
        amz_date,
        credential_scope,
        hashlib.sha256(canonical_request.encode("utf-8")).hexdigest(),
    ])
    signing_key = _aws_signing_key(api.cloudflare_r2_secret_access_key, date_stamp)
    signature = hmac.new(signing_key, string_to_sign.encode("utf-8"), hashlib.sha256).hexdigest()
    authorization = (
        "AWS4-HMAC-SHA256 "
        f"Credential={api.cloudflare_r2_access_key_id}/{credential_scope}, "
        f"SignedHeaders={signed_headers}, "
        f"Signature={signature}"
    )
    headers = {
        "Authorization": authorization,
        "x-amz-content-sha256": payload_hash,
        "x-amz-date": amz_date,
    }
    try:
        return session.get(endpoint + "/", headers=headers, timeout=25)
    except requests.exceptions.SSLError as exc:
        raise ValueError("Falha TLS/SSL no endpoint R2. Confira se CLOUDFLARE_R2_ENDPOINT usa o Account ID correto e se o endpoint S3 do R2 já está ativo.") from exc


def test_provider_connection(provider: str, api: Optional[ApiConfig] = None) -> Dict[str, Any]:
    """Teste leve de conexão/autorização. Alguns providers consomem 1 request de teste."""
    api = api or ApiConfig()
    session = requests.Session()
    session.headers.update({"User-Agent": "PlayStore Radar Ultra/1.0"})
    start = time.perf_counter()
    response: Optional[requests.Response] = None
    try:
        if provider == "ScraperAPI":
            if not api.scraperapi:
                raise ValueError("SCRAPERAPI_KEY vazio")
            response = session.get("https://api.scraperapi.com/", params={"api_key": api.scraperapi, "url": TEST_URL, "country_code": "br", "render": "false"}, timeout=25)
        elif provider == "ScrapingBee":
            if not api.scrapingbee:
                raise ValueError("SCRAPINGBEE_KEY vazio")
            response = session.get("https://app.scrapingbee.com/api/v1", params={"api_key": api.scrapingbee, "url": TEST_URL, "render_js": "false"}, timeout=25)
        elif provider == "Scrape.do":
            if not api.scrapedo:
                raise ValueError("SCRAPEDO_KEY vazio")
            response = session.get("https://api.scrape.do/", params={"token": api.scrapedo, "url": TEST_URL, "render": "false"}, timeout=25)
        elif provider == "Bright Data":
            if not api.brightdata or not api.brightdata_zone:
                raise ValueError("BRIGHTDATA_TOKEN ou BRIGHTDATA_WEB_UNLOCKER_ZONE vazio")
            response = session.post(
                "https://api.brightdata.com/request",
                headers={"Authorization": f"Bearer {api.brightdata}", "Content-Type": "application/json"},
                json={"zone": api.brightdata_zone, "url": TEST_URL, "format": "raw"},
                timeout=30,
            )
        elif provider == "Apify":
            if not api.apify:
                raise ValueError("APIFY_TOKEN vazio")
            response = session.get("https://api.apify.com/v2/users/me", params={"token": api.apify}, timeout=20)
        elif provider == "Firecrawl":
            if not api.firecrawl:
                raise ValueError("FIRECRAWL_KEY vazio")
            response = session.post(
                "https://api.firecrawl.dev/v1/scrape",
                headers={"Authorization": f"Bearer {api.firecrawl}", "Content-Type": "application/json"},
                json={"url": TEST_URL, "formats": ["markdown"]},
                timeout=30,
            )
        elif provider == "Hyperbrowser":
            if not api.hyperbrowser:
                raise ValueError("HYPERBROWSER_API_KEY vazio")
            response = session.get(
                "https://api.hyperbrowser.ai/api/sessions",
                params={"status": "active", "page": 1},
                headers={"x-api-key": api.hyperbrowser, "Accept": "application/json"},
                timeout=25,
            )
        elif provider == "Browserless":
            if not api.browserless or not api.browserless_endpoint:
                raise ValueError("BROWSERLESS_TOKEN ou BROWSERLESS_ENDPOINT vazio")
            endpoint = api.browserless_endpoint.rstrip("/")
            response = session.post(
                f"{endpoint}/smart-scrape",
                params={"token": api.browserless},
                headers={"Content-Type": "application/json", "Accept": "application/json"},
                json={"url": "https://example.com", "formats": ["markdown"]},
                timeout=35,
            )
        elif provider == "Browserbase":
            if not api.browserbase:
                raise ValueError("BROWSERBASE_API_KEY vazio")
            response = session.post(
                "https://api.browserbase.com/v1/fetch",
                headers={"X-BB-API-Key": api.browserbase, "Content-Type": "application/json", "Accept": "application/json"},
                json={"url": "https://example.com", "allowRedirects": True, "format": "raw"},
                timeout=35,
            )
        elif provider == "ScrapingAnt":
            if not api.scrapingant:
                raise ValueError("SCRAPINGANT_KEY vazio")
            response = session.get("https://api.scrapingant.com/v2/general", params={"x-api-key": api.scrapingant, "url": TEST_URL}, timeout=25)
        elif provider == "SerpAPI":
            if not api.serpapi:
                raise ValueError("SERPAPI_KEY vazio")
            response = session.get("https://serpapi.com/account", params={"api_key": api.serpapi}, timeout=20)
        elif provider == "SearchAPI":
            if not api.searchapi:
                raise ValueError("SEARCHAPI_KEY vazio")
            response = session.get(
                "https://www.searchapi.io/api/v1/me",
                params={"api_key": api.searchapi},
                headers={"Accept": "application/json"},
                timeout=20,
            )
        elif provider == "Crawlbase":
            if not api.crawlbase:
                raise ValueError("CRAWLBASE_KEY vazio")
            response = session.get("https://api.crawlbase.com/", params={"token": api.crawlbase, "url": TEST_URL}, timeout=25)
        elif provider == "Decodo":
            if not api.decodo:
                raise ValueError("DECODO_TOKEN vazio")
            response = session.post(
                "https://scraper-api.decodo.com/v2/scrape",
                headers={"Accept": "application/json", "Authorization": f"Basic {api.decodo}", "Content-Type": "application/json"},
                json={"url": "https://ip.decodo.com"},
                timeout=45,
            )
        elif provider == "Brave Search":
            if not api.brave_search:
                raise ValueError("BRAVE_SEARCH_KEY vazio")
            response = session.get(
                "https://api.search.brave.com/res/v1/web/search",
                params={"q": "google play notes app", "count": 3, "result_filter": "web", "safesearch": "moderate"},
                headers={"Accept": "application/json", "Accept-Encoding": "gzip", "X-Subscription-Token": api.brave_search},
                timeout=25,
            )
        elif provider == "OpenWebNinja":
            if not api.openwebninja or not api.openwebninja_endpoint:
                raise ValueError("OPENWEBNINJA_KEY ou OPENWEBNINJA_ENDPOINT vazio")
            headers = {"X-API-Key": api.openwebninja, "Accept": "application/json"}
            endpoint = api.openwebninja_endpoint.strip()
            if "/search" in endpoint.lower():
                response = session.get(endpoint, params={"q": "notes"}, headers=headers, timeout=25)
            else:
                response = session.post(endpoint, headers={**headers, "Content-Type": "application/json"}, json={"url": TEST_URL}, timeout=25)
        elif provider == "Scrapfly":
            if not api.scrapfly:
                raise ValueError("SCRAPFLY_KEY vazio")
            response = session.get("https://api.scrapfly.io/scrape", params={"key": api.scrapfly, "url": TEST_URL, "render_js": "false"}, timeout=30)
        elif provider == "WebScraping.AI":
            if not api.webscraping_ai:
                raise ValueError("WEBSCRAPING_AI_KEY vazio")
            response = session.get("https://api.webscraping.ai/html", params={"api_key": api.webscraping_ai, "url": TEST_URL, "js": "false"}, timeout=30)
        elif provider == "ZenRows":
            if not api.zenrows:
                raise ValueError("ZENROWS_KEY vazio")
            response = session.get("https://api.zenrows.com/v1/", params={"apikey": api.zenrows, "url": TEST_URL, "js_render": "false"}, timeout=30)
        elif provider == "AlterLab":
            if not api.alterlab:
                raise ValueError("ALTERLAB_KEY vazio")
            response = session.post("https://api.alterlab.io/api/v1/scrape", headers={"X-API-Key": api.alterlab, "Content-Type": "application/json"}, json={"url": TEST_URL, "mode": "auto"}, timeout=35)
        elif provider == "Scavio":
            if not api.scavio:
                raise ValueError("SCAVIO_KEY vazio")
            response = session.post("https://api.scavio.dev/api/v2/google", headers={"Authorization": f"Bearer {api.scavio}", "Content-Type": "application/json"}, json={"query": "site:play.google.com/store/apps/details notes app", "hl": "pt", "gl": "br"}, timeout=30)
        elif provider == "Exa":
            if not api.exa:
                raise ValueError("EXA_API_KEY vazio")
            response = session.post("https://api.exa.ai/search", headers={"x-api-key": api.exa, "Content-Type": "application/json"}, json={"query": "site:play.google.com/store/apps/details notes app", "numResults": 3}, timeout=30)
        elif provider == "Tavily":
            if not api.tavily:
                raise ValueError("TAVILY_API_KEY vazio")
            response = session.post("https://api.tavily.com/search", headers={"Authorization": f"Bearer {api.tavily}", "Content-Type": "application/json"}, json={"query": "site:play.google.com/store/apps/details notes app", "max_results": 3, "search_depth": "basic"}, timeout=30)
        elif provider == "You.com":
            if not api.youcom:
                raise ValueError("YOU_API_KEY vazio")
            response = session.get("https://api.ydc-index.io/search", headers={"X-API-Key": api.youcom, "Accept": "application/json"}, params={"query": "site:play.google.com/store/apps/details notes app", "count": 3}, timeout=30)
        elif provider == "Jina AI":
            if not api.jina:
                raise ValueError("JINA_API_KEY vazio")
            response = session.get("https://r.jina.ai/" + TEST_URL, headers={"Authorization": f"Bearer {api.jina}", "Accept": "text/plain"}, timeout=35)
        elif provider == "DeepSeek":
            if not api.deepseek:
                raise ValueError("DEEPSEEK_API_KEY vazio")
            response = session.post("https://api.deepseek.com/chat/completions", headers={"Authorization": f"Bearer {api.deepseek}", "Content-Type": "application/json"}, json={"model": "deepseek-chat", "messages": [{"role": "user", "content": "ping"}], "max_tokens": 5}, timeout=30)
        elif provider == "OpenRouter":
            if not api.openrouter:
                raise ValueError("OPENROUTER_API_KEY vazio")
            response = session.post("https://openrouter.ai/api/v1/chat/completions", headers={"Authorization": f"Bearer {api.openrouter}", "Content-Type": "application/json", "HTTP-Referer": "http://127.0.0.1:5892", "X-Title": "PlayStore Radar Ultra"}, json={"model": "openai/gpt-4.1-mini", "messages": [{"role": "user", "content": "ping"}], "max_tokens": 5}, timeout=30)
        elif provider == "Groq":
            if not api.groq:
                raise ValueError("GROQ_API_KEY vazio")
            response = session.get("https://api.groq.com/openai/v1/models", headers={"Authorization": f"Bearer {api.groq}"}, timeout=20)
        elif provider == "Mistral":
            if not api.mistral:
                raise ValueError("MISTRAL_API_KEY vazio")
            response = session.get("https://api.mistral.ai/v1/models", headers={"Authorization": f"Bearer {api.mistral}"}, timeout=20)
        elif provider == "Gemini":
            if not api.gemini:
                raise ValueError("GEMINI_API_KEY vazio")
            response = session.get(f"https://generativelanguage.googleapis.com/v1beta/models?key={api.gemini}", timeout=20)
        elif provider == "Fireworks":
            if not api.fireworks:
                raise ValueError("FIREWORKS_API_KEY vazio")
            response = session.get("https://api.fireworks.ai/inference/v1/models", headers={"Authorization": f"Bearer {api.fireworks}"}, timeout=20)
        elif provider == "Cohere":
            if not api.cohere:
                raise ValueError("COHERE_API_KEY vazio")
            response = session.get("https://api.cohere.com/v1/models", headers={"Authorization": f"Bearer {api.cohere}"}, timeout=20)
        elif provider == "NLPCloud":
            if not api.nlpcloud:
                raise ValueError("NLPCLOUD_TOKEN vazio")
            response = session.get("https://api.nlpcloud.io/v1/gpu/finetuned-gpt-neox-20b", headers={"Authorization": f"Token {api.nlpcloud}"}, timeout=20)
        elif provider == "Voyage AI":
            if not api.voyage:
                raise ValueError("VOYAGE_API_KEY vazio")
            response = session.post("https://api.voyageai.com/v1/embeddings", headers={"Authorization": f"Bearer {api.voyage}", "Content-Type": "application/json"}, json={"input": ["ping"], "model": "voyage-3-lite"}, timeout=30)
        elif provider == "Replicate":
            if not api.replicate:
                raise ValueError("REPLICATE_API_TOKEN vazio")
            response = session.get("https://api.replicate.com/v1/models", headers={"Authorization": f"Token {api.replicate}"}, timeout=20)
        elif provider == "Roboflow":
            if not api.roboflow:
                raise ValueError("ROBOFLOW_API_KEY vazio")
            response = session.get("https://api.roboflow.com/", params={"api_key": api.roboflow}, timeout=20)
        elif provider == "Cloudflare API Token":
            if not api.cloudflare_api_token:
                raise ValueError("CLOUDFLARE_API_TOKEN vazio")
            verify_url = "https://api.cloudflare.com/client/v4/user/tokens/verify"
            if api.cloudflare_account_id:
                verify_url = f"https://api.cloudflare.com/client/v4/accounts/{api.cloudflare_account_id}/tokens/verify"
            response = session.get(
                verify_url,
                headers={"Authorization": f"Bearer {api.cloudflare_api_token}", "Accept": "application/json"},
                timeout=20,
            )
        elif provider == "Cloudflare R2":
            response = _cloudflare_r2_test_response(api, session)
        elif provider == "Browse AI":
            if not api.browseai:
                raise ValueError("BROWSEAI_KEY vazio")
            token = api.browseai.split(":")[-1]
            response = session.get("https://api.browse.ai/v2/robots", headers={"Authorization": f"Bearer {token}"}, timeout=20)
        elif provider == "SimpleScraper":
            if not api.simplescraper:
                raise ValueError("SIMPLESCRAPER_KEY vazio")
            # SimpleScraper é orientado a recipes. Sem recipe_id, este teste só valida que há chave no painel.
            raise ValueError("SimpleScraper configurado, mas precisa de recipe/workflow para executar pelo app")
        elif provider == "AbstractAPI":
            if not api.abstractapi:
                raise ValueError("ABSTRACTAPI_KEY vazio")
            raise ValueError("AbstractAPI configurado, mas precisa escolher o produto AbstractAPI exato para testar")
        elif provider == "WolframAlpha":
            if not api.wolfram:
                raise ValueError("WOLFRAM_APP_ID vazio")
            response = session.get("https://api.wolframalpha.com/v1/result", params={"appid": api.wolfram, "i": "2+2"}, timeout=20)
        elif provider == "Ollama":
            response = session.get("http://127.0.0.1:11434/api/tags", timeout=5)
        else:
            raise ValueError(f"Provider desconhecido: {provider}")

        latency_ms = int((time.perf_counter() - start) * 1000)
        status = f"HTTP {response.status_code}" if response is not None else "sem resposta"
        message = _redact_api_message(_status_message(response) if response is not None else "sem resposta", api)
        ok = bool(response is not None and 200 <= response.status_code < 300)
        diagnostics = _response_diagnostics(response)
        result = {"provider": provider, "ok": ok, "status": status, "message": message, "latency_ms": latency_ms, "diagnostics": diagnostics}
        try:
            save_api_test_result(db_path(), provider, ok, status, message, latency_ms, diagnostics)
        except Exception:
            pass
        _remember_api_test_result(result)
        return result
    except Exception as exc:  # noqa: BLE001
        latency_ms = int((time.perf_counter() - start) * 1000)
        message = _redact_api_message(str(exc), api)
        result = {"provider": provider, "ok": False, "status": "erro", "message": message, "latency_ms": latency_ms, "diagnostics": {}}
        try:
            save_api_test_result(db_path(), provider, False, "erro", message, latency_ms, {})
        except Exception:
            pass
        _remember_api_test_result(result)
        return result


@app.route("/login", methods=["GET", "POST"])
def login():
    if _is_authenticated():
        return redirect(url_for("index"))

    next_url = _safe_next_url(request.values.get("next"))
    error = None

    if request.method == "POST":
        username = request.form.get("username", "").strip()
        password = request.form.get("password", "")
        username_ok = hmac.compare_digest(username, LOGIN_USERNAME)
        password_ok = hmac.compare_digest(password, LOGIN_PASSWORD)

        if username_ok and password_ok:
            session.clear()
            session.permanent = True
            session["authenticated"] = True
            session["username"] = LOGIN_USERNAME
            flash("Login realizado com sucesso.", "success")
            return redirect(next_url or url_for("index"))

        error = "Usuário ou senha incorretos."

    return render_template("login.html", error=error, next_url=next_url)


@app.route("/logout", methods=["POST"])
def logout():
    session.clear()
    flash("Sessão encerrada.", "info")
    return redirect(url_for("login"))


@app.route("/")
def index():
    api = ApiConfig()
    stats = get_stats(db_path())
    runs = list_runs(db_path(), 20)
    apps = list_apps(db_path(), limit=24)
    api_status_cards = quick_api_cards()
    executive = dashboard_insights(runs, api_status_cards)
    active_runs = [r for r in runs if r.get("status") in RUN_ACTIVE_STATUSES]
    queue = _queue_info()
    return render_template(
        "index.html",
        api=api,
        stats=stats,
        runs=runs,
        active_runs=active_runs,
        apps=apps,
        api_status_cards=api_status_cards,
        executive=executive,
        queue=queue,
    )


@app.route("/start", methods=["POST"])
def start_run():
    # Campos simples usam o último valor; categorias são multi-select com checkbox.
    data = {k: request.form.getlist(k)[-1] for k in request.form.keys()}
    scope = (data.get("scope") or "TODAS").upper()
    if scope == "APPS":
        selected = request.form.getlist("apps_category_codes")
        data["category_codes"] = ",".join(selected)
        data["subcategory_codes"] = ",".join(request.form.getlist("apps_subcategory_codes"))
    elif scope == "JOGOS":
        selected = request.form.getlist("games_category_codes")
        data["category_codes"] = ",".join(selected)
        data["subcategory_codes"] = ",".join(request.form.getlist("games_subcategory_codes"))
    else:
        # Escopo TODOS é literal: apps + jogos, sem filtro fino.
        data["category_codes"] = ""
        data["subcategory_codes"] = ""

    cfg = RunConfig.from_dict(data)
    run_id = _create_and_enqueue_run(cfg)
    flash(f"Run #{run_id} entrou na fila. O despachante inicia quando houver worker livre.", "success")
    return redirect(url_for("run_detail", run_id=run_id))


@app.route("/runs")
def runs_page():
    return render_template("runs.html", runs=list_runs(db_path(), 200), queue=_queue_info())


@app.route("/runs/compare")
def runs_compare_page():
    runs = list_runs(db_path(), 300)
    base_arg = request.args.get("base_id") or request.args.get("base")
    target_arg = request.args.get("target_id") or request.args.get("target")
    try:
        base_id = int(base_arg) if base_arg else 0
    except ValueError:
        base_id = 0
    try:
        target_id = int(target_arg) if target_arg else 0
    except ValueError:
        target_id = 0
    if (not base_id or not target_id) and len(runs) >= 2:
        target_id = target_id or int(runs[0]["id"])
        base_id = base_id or int(runs[1]["id"])
    comparison = build_run_comparison(base_id, target_id) if base_id and target_id and base_id != target_id else {}
    return render_template(
        "runs_compare.html",
        runs=runs,
        base_id=base_id,
        target_id=target_id,
        comparison=comparison,
    )


@app.route("/run/<int:run_id>")
def run_detail(run_id: int):
    run = get_run(db_path(), run_id)
    if not run:
        flash("Run não encontrado.", "warning")
        return redirect(url_for("index"))
    logs = list_logs(db_path(), run_id, 200)
    apps = list_apps(db_path(), run_id=run_id, order="opportunity_score", limit=200)
    return render_template("run_detail.html", run=run, run_summary=_run_search_summary(run), logs=logs, apps=apps, queue=_queue_info())


@app.route("/run/<int:run_id>/pause", methods=["POST"])
def pause_run(run_id: int):
    run = get_run(db_path(), run_id)
    if not run:
        flash("Run não encontrado.", "warning")
        return redirect(url_for("runs_page"))
    if run.get("status") == "queued":
        update_run(db_path(), run_id, status="paused", last_message="Run pausada antes de iniciar.")
        flash(f"Run #{run_id} pausada na fila.", "warning")
    elif run.get("status") == "running":
        request_run_status(db_path(), run_id, "pause_requested", "Pausa solicitada. O worker vai parar no próximo ponto seguro.")
        flash(f"Pausa solicitada para a Run #{run_id}.", "warning")
    else:
        flash("Essa busca não está rodando agora.", "info")
    return redirect(request.referrer or url_for("run_detail", run_id=run_id))


@app.route("/run/<int:run_id>/resume", methods=["POST"])
def resume_run(run_id: int):
    run = get_run(db_path(), run_id)
    if not run:
        flash("Run não encontrado.", "warning")
        return redirect(url_for("runs_page"))
    if run.get("status") in {"paused", "pause_requested"}:
        worker = ACTIVE_THREADS.get(run_id)
        if worker and worker.is_alive():
            update_run(db_path(), run_id, status="running", last_message="Retomando coleta.")
            flash(f"Run #{run_id} retomada.", "success")
        else:
            update_run(db_path(), run_id, status="queued", last_message="Run retomada e devolvida para a fila.")
            _ensure_queue_dispatcher()
            _dispatch_queue_once()
            flash(f"Run #{run_id} voltou para a fila.", "success")
    else:
        flash("Essa busca não está pausada.", "info")
    return redirect(request.referrer or url_for("run_detail", run_id=run_id))


@app.route("/run/<int:run_id>/cancel", methods=["POST"])
def cancel_run(run_id: int):
    run = get_run(db_path(), run_id)
    if not run:
        flash("Run não encontrado.", "warning")
        return redirect(url_for("runs_page"))
    worker = ACTIVE_THREADS.get(run_id)
    if run.get("status") == "queued" or (run.get("status") == "paused" and not (worker and worker.is_alive())):
        update_run(db_path(), run_id, status="cancelled", finished_at=now_iso(), last_message="Cancelada antes de iniciar.")
        flash(f"Run #{run_id} cancelada antes de iniciar.", "warning")
    elif _is_active(run):
        request_run_status(db_path(), run_id, "cancel_requested", "Cancelamento solicitado. Mantendo o histórico e os apps já salvos.")
        flash(f"Cancelamento solicitado para a Run #{run_id}.", "warning")
    else:
        update_run(db_path(), run_id, status="cancelled", finished_at=now_iso(), last_message="Marcada como cancelada manualmente.")
        flash(f"Run #{run_id} marcada como cancelada.", "warning")
    return redirect(request.referrer or url_for("run_detail", run_id=run_id))


@app.route("/run/<int:run_id>/delete", methods=["POST"])
def delete_run_route(run_id: int):
    run = get_run(db_path(), run_id)
    if not run:
        flash("Run já não existe.", "info")
        return redirect(url_for("runs_page"))
    worker = ACTIVE_THREADS.get(run_id)
    if run.get("status") == "queued":
        delete_run(db_path(), run_id)
        flash(f"Run #{run_id} removida da fila.", "success")
        return redirect(url_for("runs_page"))
    if _is_active(run) and worker and worker.is_alive():
        request_run_status(db_path(), run_id, "delete_requested", "Exclusão solicitada. A coleta será interrompida e removida.")
        flash(f"Exclusão solicitada para a Run #{run_id}. Ela some quando o worker chegar no próximo ponto seguro.", "warning")
        return redirect(url_for("runs_page"))
    delete_run(db_path(), run_id)
    flash(f"Run #{run_id} excluída com apps e logs.", "success")
    return redirect(url_for("runs_page"))


@app.route("/run/<int:run_id>/rerun", methods=["POST"])
def rerun_run(run_id: int):
    run = get_run(db_path(), run_id)
    if not run:
        flash("Run base não encontrada.", "warning")
        return redirect(url_for("runs_page"))
    cfg = _cfg_from_run(run)
    new_run_id = _create_and_enqueue_run(cfg, parent_run_id=run_id)
    flash(f"Busca refeita: Run #{new_run_id} criada a partir da Run #{run_id}.", "success")
    return redirect(url_for("run_detail", run_id=new_run_id))


@app.route("/run/<int:run_id>/restart", methods=["POST"])
def restart_run(run_id: int):
    run = get_run(db_path(), run_id)
    if not run:
        flash("Run base não encontrada.", "warning")
        return redirect(url_for("runs_page"))
    cfg = _cfg_from_run(run)
    if _is_active(run):
        request_run_status(db_path(), run_id, "restart_requested", "Reinício solicitado. Esta coleta será parada e uma nova será aberta.")
    else:
        update_run(db_path(), run_id, status="cancelled", finished_at=now_iso(), last_message="Reiniciada manualmente em outra run.")
    new_run_id = _create_and_enqueue_run(cfg, parent_run_id=run_id)
    flash(f"Run #{run_id} reiniciada como Run #{new_run_id}.", "success")
    return redirect(url_for("run_detail", run_id=new_run_id))


@app.route("/api/run/<int:run_id>/status")
def api_run_status(run_id: int):
    progress = run_progress(db_path(), run_id)
    return jsonify(progress)


@app.route("/settings")
def settings_page():
    cards = api_cards()
    fields = api_field_rows()
    card_lookup = {str(card.get("provider")): card for card in cards}
    cards_by_group = {group: [c for c in cards if c.get("group") == group] for group in API_PROVIDER_GROUPS}
    fields_by_group = {group: [f for f in fields if f.get("group") == group] for group in API_PROVIDER_GROUPS}
    diagnostic_summary = api_diagnostic_summary(cards)
    return render_template(
        "settings.html",
        api=ApiConfig(),
        cards=cards,
        fields=fields,
        card_lookup=card_lookup,
        cards_by_group=cards_by_group,
        fields_by_group=fields_by_group,
        api_groups=API_PROVIDER_GROUPS,
        diagnostic_summary=diagnostic_summary,
    )


@app.route("/settings/apis", methods=["POST"])
def save_api_settings_route():
    values = {field["attr"]: request.form.get(str(field["attr"]), "") for field in API_FIELDS}
    save_api_settings(values)
    flash("Configurações de API salvas. Campos do .env continuam tendo prioridade quando existirem.", "success")
    return redirect(url_for("settings_page"))


@app.route("/settings/api/<provider>/test", methods=["POST"])
def test_api_route(provider: str):
    provider = provider.replace("_", " ")
    result = test_provider_connection(provider)
    category = "success" if result.get("ok") else "warning"
    flash(f"{provider}: {result.get('status')} · {result.get('message')}", category)
    return redirect(url_for("settings_page"))


@app.route("/settings/api/test-all", methods=["POST"])
def test_all_apis_route():
    api = ApiConfig()
    availability = api.available()
    tested = 0
    ok_count = 0
    for provider in PROVIDER_ORDER:
        if not availability.get(provider):
            continue
        tested += 1
        result = test_provider_connection(provider, api)
        ok_count += 1 if result.get("ok") else 0
    if tested == 0:
        flash("Nenhuma API configurada para testar.", "warning")
    else:
        flash(f"Teste geral concluído: {ok_count}/{tested} APIs responderam bem.", "success" if ok_count == tested else "warning")
    return redirect(url_for("settings_page"))


@app.route("/api/settings/cards")
def api_settings_cards():
    return jsonify(api_cards())


@app.route("/apps")
def apps_page():
    q = request.args.get("q", "")
    profile = request.args.get("profile", "")
    run_id = request.args.get("run_id", type=int)
    min_score = request.args.get("min_score", type=float)
    order = request.args.get("order", "created_at")
    date_from = request.args.get("date_from", "")
    date_to = request.args.get("date_to", "")
    apps = list_apps(
        db_path(),
        run_id=run_id,
        q=q,
        profile=profile,
        min_score=min_score,
        order=order,
        date_from=date_from,
        date_to=date_to,
        limit=500,
    )
    runs = list_runs(db_path(), 150)
    selected_run = get_run(db_path(), run_id) if run_id else None
    return render_template(
        "apps.html",
        apps=apps,
        runs=runs,
        selected_run=selected_run,
        q=q,
        profile=profile,
        run_id=run_id,
        min_score=min_score,
        order=order,
        date_from=date_from,
        date_to=date_to,
    )


@app.route("/app/<int:app_pk>")
def app_detail(app_pk: int):
    app_row = get_app(db_path(), app_pk)
    if not app_row:
        flash("App não encontrado.", "warning")
        return redirect(url_for("apps_page"))
    raw = {}
    try:
        raw = json.loads(app_row.get("raw_json") or "{}")
    except Exception:
        raw = {}
    view = build_app_view(app_row, raw)
    return render_template("app_detail.html", app=app_row, raw=raw, view=view)


@app.route("/export/<int:run_id>/<fmt>")
def export_run(run_id: int, fmt: str):
    run = get_run(db_path(), run_id)
    if not run:
        flash("Run não encontrado.", "warning")
        return redirect(url_for("runs_page"))
    paths = export_run_all(db_path(), run_id, output_dir())
    path = paths.get(fmt)
    if not path:
        flash("Formato inválido.", "warning")
        return redirect(url_for("run_detail", run_id=run_id))
    return send_file(path, as_attachment=True)


@app.route("/export-all/<fmt>")
def export_all_route(fmt: str):
    if fmt not in {"html", "json", "csv"}:
        flash("Formato inválido.", "warning")
        return redirect(url_for("runs_page"))
    mode = request.args.get("mode", "combined")
    if mode == "separate":
        zip_path = export_all_separate_zip(db_path(), fmt, output_dir())
        if not zip_path:
            flash("Não há nenhuma busca para exportar ainda.", "info")
            return redirect(url_for("runs_page"))
        return send_file(zip_path, as_attachment=True)
    paths = export_all_formats(db_path(), output_dir())
    path = paths.get(fmt)
    if not path:
        flash("Não há nada para exportar ainda.", "info")
        return redirect(url_for("runs_page"))
    return send_file(path, as_attachment=True)


@app.route("/api/run/<int:run_id>/apps")
def api_run_apps(run_id: int):
    apps = list_apps(db_path(), run_id=run_id, order="opportunity_score", limit=60)
    compact = []
    for a in apps:
        compact.append({
            "id": a.get("id"),
            "title": a.get("title"),
            "developer": a.get("developer"),
            "icon": a.get("icon"),
            "categoria": a.get("categoria") or a.get("genre"),
            "genre": a.get("genre"),
            "score": a.get("score"),
            "installs": a.get("installs"),
            "min_installs": a.get("min_installs"),
            "real_installs": a.get("real_installs"),
            "opportunity_score": a.get("opportunity_score") or 0,
            "growth_score": a.get("growth_score") or 0,
            "indie_score": a.get("indie_score") or 0,
            "revenue_monthly_usd_base": a.get("revenue_monthly_usd_base") or 0,
            "profit_monthly_usd_base": a.get("profit_monthly_usd_base") or 0,
            "financial_confidence": a.get("financial_confidence"),
        })
    return jsonify({"apps": compact})


@app.route("/health")
def health():
    try:
        ok = ping_database(db_path())
        if ok:
            _ensure_queue_dispatcher()
        return jsonify({"status": "ok" if ok else "degraded", "database": database_backend(db_path())}), 200 if ok else 503
    except Exception as exc:  # noqa: BLE001
        return jsonify({
            "status": "error",
            "database": database_backend(db_path()),
            "message": "database unavailable",
            "error_type": type(exc).__name__,
        }), 503


if __name__ == "__main__":
    debug_enabled = os.getenv("PLAYSTORE_RADAR_DEBUG", "").strip().lower() in {"1", "true", "yes", "on"}
    port = int(os.getenv("PORT", "5892"))
    host = "0.0.0.0" if os.getenv("PORT") else "127.0.0.1"
    app.run(host=host, port=port, debug=debug_enabled)
