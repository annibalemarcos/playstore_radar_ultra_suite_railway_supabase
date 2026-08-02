from __future__ import annotations

import hmac
import html
import json
import os
import re
import secrets
import threading
import time
from datetime import timedelta
from pathlib import Path
from typing import Any, Dict, List, Optional
from urllib.parse import urlsplit

import requests
from flask import Flask, flash, jsonify, redirect, render_template, request, send_file, session, url_for
from werkzeug.middleware.proxy_fix import ProxyFix

from app_core.categories import categorias_para_form
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
    load_saved_api_settings,
    mask_secret,
    save_api_settings,
    setting_source,
)
from app_core.database import (
    RUN_ACTIVE_STATUSES,
    database_backend,
    create_run,
    delete_run,
    get_app,
    get_run,
    get_stats,
    get_api_usage_stats,
    init_db,
    list_apps,
    list_logs,
    list_runs,
    now_iso,
    ping_database,
    latest_api_tests,
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


def _spawn_worker(run_id: int, cfg: RunConfig, api: Optional[ApiConfig] = None) -> None:
    api = api or ApiConfig()

    def worker() -> None:
        try:
            run_scraper(cfg, api=api, run_id=run_id)
        except Exception as exc:  # noqa: BLE001
            update_run(cfg.db_path, run_id, status="failed", finished_at=now_iso(), last_message=str(exc), errors_count=1)

    t = threading.Thread(target=worker, daemon=True)
    ACTIVE_THREADS[run_id] = t
    t.start()


def _create_and_start_run(cfg: RunConfig, parent_run_id: Optional[int] = None) -> int:
    cfg.db_path = db_path()
    cfg.output_dir = str(output_dir())
    api = ApiConfig()
    cfg.apply_level_defaults(api)
    run_id = create_run(cfg, status="queued", parent_run_id=parent_run_id)
    _spawn_worker(run_id, cfg, api)
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


def api_field_rows() -> List[Dict[str, Any]]:
    api = ApiConfig()
    rows: List[Dict[str, Any]] = []
    for field in API_FIELDS:
        attr = str(field["attr"])
        env_name = str(field["env"])
        value = getattr(api, attr, "") or ""
        source = setting_source(attr, env_name)
        rows.append(
            {
                **field,
                "value": value,
                "masked": mask_secret(value) if field.get("secret", True) else value,
                "source": source,
                "source_slug": "env" if source == ".env" else source,
                "is_env": source == ".env",
                "is_secret": field.get("secret", True),
            }
        )
    return rows


def api_cards() -> List[Dict[str, Any]]:
    api = ApiConfig()
    availability = api.available()
    usage = get_api_usage_stats(db_path())
    latest_tests = latest_api_tests(db_path())
    rows = api_field_rows()
    fields_by_provider: Dict[str, List[Dict[str, Any]]] = {}
    for row in rows:
        fields_by_provider.setdefault(str(row["provider"]), []).append(row)
    cards: List[Dict[str, Any]] = []
    for provider in PROVIDER_ORDER:
        fields = fields_by_provider.get(provider, [])
        sources = sorted({f["source"] for f in fields if f.get("value")})
        test = latest_tests.get(provider, {})
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
            }
        )
    return cards


def _status_message(response: requests.Response, max_len: int = 260) -> str:
    text = ""
    try:
        data = response.json()
        if isinstance(data, dict):
            for key in ("message", "error", "status", "name", "username"):
                if data.get(key):
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
        elif provider == "ScrapingAnt":
            if not api.scrapingant:
                raise ValueError("SCRAPINGANT_KEY vazio")
            response = session.get("https://api.scrapingant.com/v2/general", params={"x-api-key": api.scrapingant, "url": TEST_URL}, timeout=25)
        elif provider == "SerpAPI":
            if not api.serpapi:
                raise ValueError("SERPAPI_KEY vazio")
            response = session.get("https://serpapi.com/account", params={"api_key": api.serpapi}, timeout=20)
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
        message = _status_message(response) if response is not None else "sem resposta"
        ok = bool(response is not None and 200 <= response.status_code < 300)
        save_api_test_result(db_path(), provider, ok, status, message, latency_ms)
        return {"provider": provider, "ok": ok, "status": status, "message": message, "latency_ms": latency_ms}
    except Exception as exc:  # noqa: BLE001
        latency_ms = int((time.perf_counter() - start) * 1000)
        message = str(exc)[:500]
        save_api_test_result(db_path(), provider, False, "erro", message, latency_ms)
        return {"provider": provider, "ok": False, "status": "erro", "message": message, "latency_ms": latency_ms}


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
    active_runs = [r for r in runs if r.get("status") in RUN_ACTIVE_STATUSES]
    return render_template("index.html", api=api, stats=stats, runs=runs, active_runs=active_runs, apps=apps)


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
    run_id = _create_and_start_run(cfg)
    flash(f"Run #{run_id} iniciado. Agora é deixar o robozinho suar silício.", "success")
    return redirect(url_for("run_detail", run_id=run_id))


@app.route("/runs")
def runs_page():
    return render_template("runs.html", runs=list_runs(db_path(), 200))


@app.route("/run/<int:run_id>")
def run_detail(run_id: int):
    run = get_run(db_path(), run_id)
    if not run:
        flash("Run não encontrado.", "warning")
        return redirect(url_for("index"))
    logs = list_logs(db_path(), run_id, 200)
    apps = list_apps(db_path(), run_id=run_id, order="opportunity_score", limit=200)
    return render_template("run_detail.html", run=run, logs=logs, apps=apps)


@app.route("/run/<int:run_id>/pause", methods=["POST"])
def pause_run(run_id: int):
    run = get_run(db_path(), run_id)
    if not run:
        flash("Run não encontrado.", "warning")
        return redirect(url_for("runs_page"))
    if run.get("status") in {"running", "queued"}:
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
        request_run_status(db_path(), run_id, "running", "Retomando coleta.", "success")
        flash(f"Run #{run_id} retomada.", "success")
    else:
        flash("Essa busca não está pausada.", "info")
    return redirect(request.referrer or url_for("run_detail", run_id=run_id))


@app.route("/run/<int:run_id>/cancel", methods=["POST"])
def cancel_run(run_id: int):
    run = get_run(db_path(), run_id)
    if not run:
        flash("Run não encontrado.", "warning")
        return redirect(url_for("runs_page"))
    if _is_active(run):
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
    new_run_id = _create_and_start_run(cfg, parent_run_id=run_id)
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
    new_run_id = _create_and_start_run(cfg, parent_run_id=run_id)
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
    cards_by_group = {group: [c for c in cards if c.get("group") == group] for group in API_PROVIDER_GROUPS}
    fields_by_group = {group: [f for f in fields if f.get("group") == group] for group in API_PROVIDER_GROUPS}
    return render_template("settings.html", api=ApiConfig(), cards=cards, fields=fields, cards_by_group=cards_by_group, fields_by_group=fields_by_group, api_groups=API_PROVIDER_GROUPS)


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
