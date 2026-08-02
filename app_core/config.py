"""Configurações compartilhadas entre CLI e dashboard web."""
from __future__ import annotations

import json
import os
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any, Dict, Optional

try:
    from dotenv import load_dotenv
except Exception:  # pragma: no cover
    def load_dotenv(*_: Any, **__: Any) -> bool:
        return False

ROOT_DIR = Path(__file__).resolve().parents[1]
DATA_DIR = ROOT_DIR / "data"
DEFAULT_DB_PATH = DATA_DIR / "playstore_radar.db"
DEFAULT_OUTPUT_DIR = ROOT_DIR / "playstore_radar_outputs"

load_dotenv(ROOT_DIR / ".env")
load_dotenv()

LEVELS: Dict[str, str] = {
    "SIMPLES": "⚡ Simples — rápido, parecido com o atual",
    "PROFUNDO": "🧬 Profundo — detalhes completos + reviews recentes",
    "FINANCEIRO": "💰 Financeiro — estimativa de receita/lucro",
    "FULL": "🛰️ Full — financeiro + APIs externas disponíveis",
    "ULTRA_FULL": "🧨 Ultra Full — tudo ligado, mais reviews e fontes",
}

PROFILES: Dict[str, str] = {
    "TODOS": "🌍 Todos — sem filtro",
    "PEQUENOS_INDIE": "🌱 Pequenos/indie — evita gigantes e caça apps menores",
    "CRESCENDO": "📈 Crescendo — sinais de tração recente",
    "OPORTUNIDADE": "💎 Oportunidade — pequeno/médio + monetização + boa nota",
    "SEM_GIGANTES": "🚫 Sem gigantes — corta WhatsApp/Facebook/Google etc.",
}

SCOPES: Dict[str, str] = {
    "TODAS": "Apps + Jogos",
    "APPS": "Somente Aplicativos",
    "JOGOS": "Somente Jogos",
}


def env(name: str, default: str = "") -> str:
    return os.getenv(name, default).strip()


def database_target() -> str:
    """PostgreSQL/Supabase quando configurado; SQLite local por padrão."""
    return env("DATABASE_URL") or env("SUPABASE_DB_URL") or str(DEFAULT_DB_PATH)


def output_target() -> str:
    return env("PLAYSTORE_RADAR_OUTPUT_DIR") or str(DEFAULT_OUTPUT_DIR)


API_SETTINGS_PATH = DATA_DIR / "api_settings.json"

API_PROVIDER_GROUPS: Dict[str, list[str]] = {
    "Scraping / Render": [
        "ScraperAPI", "ScrapingBee", "Scrape.do", "Bright Data", "Apify", "Firecrawl", "Hyperbrowser",
        "Browserless", "Browserbase", "ScrapingAnt", "Crawlbase", "Decodo", "Scrapfly",
        "WebScraping.AI", "ZenRows", "AlterLab", "Jina AI",
    ],
    "Search / Discovery": ["SerpAPI", "SearchAPI", "Brave Search", "OpenWebNinja", "Scavio", "Exa", "Tavily", "You.com", "Jina AI", "WolframAlpha"],
    "LLM / Insights": ["DeepSeek", "OpenRouter", "Groq", "Mistral", "Gemini", "Fireworks", "Cohere", "NLPCloud"],
    "Embeddings / Vision": ["Jina AI", "Voyage AI", "Replicate", "Roboflow"],
    "Automation / Recipes": ["SimpleScraper", "Browse AI", "AbstractAPI", "Ollama"],
    "Storage / Infra": ["Cloudflare API Token", "Cloudflare R2"],
}

API_FIELDS = [
    # Scraping / renderização
    {"group": "Scraping / Render", "provider": "ScraperAPI", "attr": "scraperapi", "env": "SCRAPERAPI_KEY", "label": "ScraperAPI", "placeholder": "api_key"},
    {"group": "Scraping / Render", "provider": "ScrapingBee", "attr": "scrapingbee", "env": "SCRAPINGBEE_KEY", "label": "ScrapingBee", "placeholder": "api_key"},
    {"group": "Scraping / Render", "provider": "Scrape.do", "attr": "scrapedo", "env": "SCRAPEDO_KEY", "label": "Scrape.do", "placeholder": "token"},
    {"group": "Scraping / Render", "provider": "Bright Data", "attr": "brightdata", "env": "BRIGHTDATA_TOKEN", "label": "Bright Data Token", "placeholder": "Bearer token"},
    {"group": "Scraping / Render", "provider": "Bright Data", "attr": "brightdata_zone", "env": "BRIGHTDATA_WEB_UNLOCKER_ZONE", "label": "Bright Data Zone", "placeholder": "playstore_unlocker", "secret": False},
    {"group": "Scraping / Render", "provider": "Apify", "attr": "apify", "env": "APIFY_TOKEN", "label": "Apify Token", "placeholder": "apify_api_..."},
    {"group": "Scraping / Render", "provider": "Apify", "attr": "apify_actor_id", "env": "APIFY_ACTOR_ID", "label": "Apify Actor ID", "placeholder": "oneary/google-play-store-scraper", "secret": False},
    {"group": "Scraping / Render", "provider": "Firecrawl", "attr": "firecrawl", "env": "FIRECRAWL_KEY", "label": "Firecrawl", "placeholder": "fc-..."},
    {"group": "Scraping / Render", "provider": "Hyperbrowser", "attr": "hyperbrowser", "env": "HYPERBROWSER_API_KEY", "label": "Hyperbrowser API Key", "placeholder": "hb_..."},
    {"group": "Scraping / Render", "provider": "Browserless", "attr": "browserless", "env": "BROWSERLESS_TOKEN", "label": "Browserless Token", "placeholder": "token"},
    {"group": "Scraping / Render", "provider": "Browserless", "attr": "browserless_endpoint", "env": "BROWSERLESS_ENDPOINT", "label": "Browserless Endpoint", "placeholder": "https://production-sfo.browserless.io", "secret": False},
    {"group": "Scraping / Render", "provider": "Browserbase", "attr": "browserbase", "env": "BROWSERBASE_API_KEY", "label": "Browserbase API Key", "placeholder": "bb_live_..."},
    {"group": "Scraping / Render", "provider": "Browserbase", "attr": "browserbase_project_id", "env": "BROWSERBASE_PROJECT_ID", "label": "Browserbase Project ID", "placeholder": "opcional", "secret": False},
    {"group": "Scraping / Render", "provider": "ScrapingAnt", "attr": "scrapingant", "env": "SCRAPINGANT_KEY", "label": "ScrapingAnt", "placeholder": "api_key"},
    {"group": "Scraping / Render", "provider": "Crawlbase", "attr": "crawlbase", "env": "CRAWLBASE_KEY", "label": "Crawlbase", "placeholder": "token"},
    {"group": "Scraping / Render", "provider": "Decodo", "attr": "decodo", "env": "DECODO_TOKEN", "label": "Decodo Web Scraping API", "placeholder": "Basic token/base64"},
    {"group": "Scraping / Render", "provider": "Scrapfly", "attr": "scrapfly", "env": "SCRAPFLY_KEY", "label": "Scrapfly", "placeholder": "scp-live-..."},
    {"group": "Scraping / Render", "provider": "WebScraping.AI", "attr": "webscraping_ai", "env": "WEBSCRAPING_AI_KEY", "label": "WebScraping.AI", "placeholder": "uuid/api_key"},
    {"group": "Scraping / Render", "provider": "ZenRows", "attr": "zenrows", "env": "ZENROWS_KEY", "label": "ZenRows", "placeholder": "api_key"},
    {"group": "Scraping / Render", "provider": "AlterLab", "attr": "alterlab", "env": "ALTERLAB_KEY", "label": "AlterLab API Key", "placeholder": "sk_live_..."},
    {"group": "Scraping / Render", "provider": "AlterLab", "attr": "alterlab_playground", "env": "ALTERLAB_PLAYGROUND_KEY", "label": "AlterLab Playground Key", "placeholder": "sk_live_...", "secret": True},

    # Search / discovery
    {"group": "Search / Discovery", "provider": "SerpAPI", "attr": "serpapi", "env": "SERPAPI_KEY", "label": "SerpAPI", "placeholder": "api_key"},
    {"group": "Search / Discovery", "provider": "SearchAPI", "attr": "searchapi", "env": "SEARCHAPI_KEY", "label": "SearchAPI.io", "placeholder": "api_key"},
    {"group": "Search / Discovery", "provider": "Brave Search", "attr": "brave_search", "env": "BRAVE_SEARCH_KEY", "label": "Brave Search API", "placeholder": "BSAP..."},
    {"group": "Search / Discovery", "provider": "OpenWebNinja", "attr": "openwebninja", "env": "OPENWEBNINJA_KEY", "label": "OpenWebNinja Key", "placeholder": "ak_..."},
    {"group": "Search / Discovery", "provider": "OpenWebNinja", "attr": "openwebninja_endpoint", "env": "OPENWEBNINJA_ENDPOINT", "label": "OpenWebNinja Endpoint", "placeholder": "https://api.openwebninja.com/play-store-apps/search", "secret": False},
    {"group": "Search / Discovery", "provider": "Scavio", "attr": "scavio", "env": "SCAVIO_KEY", "label": "Scavio Search API", "placeholder": "sk_..."},
    {"group": "Search / Discovery", "provider": "Exa", "attr": "exa", "env": "EXA_API_KEY", "label": "Exa Search", "placeholder": "api_key"},
    {"group": "Search / Discovery", "provider": "Tavily", "attr": "tavily", "env": "TAVILY_API_KEY", "label": "Tavily Search", "placeholder": "tvly-..."},
    {"group": "Search / Discovery", "provider": "You.com", "attr": "youcom", "env": "YOU_API_KEY", "label": "You.com Search", "placeholder": "ydc-sk-..."},
    {"group": "Search / Discovery", "provider": "WolframAlpha", "attr": "wolfram", "env": "WOLFRAM_APP_ID", "label": "WolframAlpha App ID", "placeholder": "APP_ID"},

    # LLMs / insights
    {"group": "LLM / Insights", "provider": "DeepSeek", "attr": "deepseek", "env": "DEEPSEEK_API_KEY", "label": "DeepSeek", "placeholder": "sk-..."},
    {"group": "LLM / Insights", "provider": "OpenRouter", "attr": "openrouter", "env": "OPENROUTER_API_KEY", "label": "OpenRouter", "placeholder": "sk-or-..."},
    {"group": "LLM / Insights", "provider": "Groq", "attr": "groq", "env": "GROQ_API_KEY", "label": "Groq", "placeholder": "gsk_..."},
    {"group": "LLM / Insights", "provider": "Mistral", "attr": "mistral", "env": "MISTRAL_API_KEY", "label": "Mistral", "placeholder": "api_key"},
    {"group": "LLM / Insights", "provider": "Gemini", "attr": "gemini", "env": "GEMINI_API_KEY", "label": "Gemini / Google AI", "placeholder": "AIza..."},
    {"group": "LLM / Insights", "provider": "Fireworks", "attr": "fireworks", "env": "FIREWORKS_API_KEY", "label": "Fireworks AI", "placeholder": "fw_..."},
    {"group": "LLM / Insights", "provider": "Cohere", "attr": "cohere", "env": "COHERE_API_KEY", "label": "Cohere", "placeholder": "api_key"},
    {"group": "LLM / Insights", "provider": "NLPCloud", "attr": "nlpcloud", "env": "NLPCLOUD_TOKEN", "label": "NLPCloud", "placeholder": "token"},

    # Embeddings / visão / automações
    {"group": "Embeddings / Vision", "provider": "Jina AI", "attr": "jina", "env": "JINA_API_KEY", "label": "Jina AI", "placeholder": "jina_..."},
    {"group": "Embeddings / Vision", "provider": "Voyage AI", "attr": "voyage", "env": "VOYAGE_API_KEY", "label": "Voyage AI", "placeholder": "pa-..."},
    {"group": "Embeddings / Vision", "provider": "Replicate", "attr": "replicate", "env": "REPLICATE_API_TOKEN", "label": "Replicate", "placeholder": "r8_..."},
    {"group": "Embeddings / Vision", "provider": "Roboflow", "attr": "roboflow", "env": "ROBOFLOW_API_KEY", "label": "Roboflow", "placeholder": "api_key"},
    {"group": "Automation / Recipes", "provider": "SimpleScraper", "attr": "simplescraper", "env": "SIMPLESCRAPER_KEY", "label": "SimpleScraper", "placeholder": "api_key"},
    {"group": "Automation / Recipes", "provider": "Browse AI", "attr": "browseai", "env": "BROWSEAI_KEY", "label": "Browse AI", "placeholder": "token ou workspace:token"},
    {"group": "Automation / Recipes", "provider": "AbstractAPI", "attr": "abstractapi", "env": "ABSTRACTAPI_KEY", "label": "AbstractAPI", "placeholder": "api_key"},
    {"group": "Automation / Recipes", "provider": "Ollama", "attr": "ollama", "env": "OLLAMA_API_KEY", "label": "Ollama API Key", "placeholder": "opcional/local/remoto"},

    # Storage / infra
    {"group": "Storage / Infra", "provider": "Cloudflare API Token", "attr": "cloudflare_token_name", "env": "CLOUDFLARE_TOKEN_NAME", "label": "Cloudflare Token Name", "placeholder": "fancy-tooth-7e81", "secret": False},
    {"group": "Storage / Infra", "provider": "Cloudflare API Token", "attr": "cloudflare_account_id", "env": "CLOUDFLARE_ACCOUNT_ID", "label": "Cloudflare Account ID", "placeholder": "account_id", "secret": False},
    {"group": "Storage / Infra", "provider": "Cloudflare API Token", "attr": "cloudflare_api_token", "env": "CLOUDFLARE_API_TOKEN", "label": "Cloudflare API Token", "placeholder": "cfat_..."},
    {"group": "Storage / Infra", "provider": "Cloudflare R2", "attr": "cloudflare_r2_access_key_id", "env": "CLOUDFLARE_R2_ACCESS_KEY_ID", "label": "R2 Access Key ID", "placeholder": "access_key_id"},
    {"group": "Storage / Infra", "provider": "Cloudflare R2", "attr": "cloudflare_r2_secret_access_key", "env": "CLOUDFLARE_R2_SECRET_ACCESS_KEY", "label": "R2 Secret Access Key", "placeholder": "secret_access_key"},
    {"group": "Storage / Infra", "provider": "Cloudflare R2", "attr": "cloudflare_r2_endpoint", "env": "CLOUDFLARE_R2_ENDPOINT", "label": "R2 S3 Endpoint", "placeholder": "https://<account>.r2.cloudflarestorage.com", "secret": False},
]


def load_saved_api_settings() -> Dict[str, str]:
    try:
        data = json.loads(API_SETTINGS_PATH.read_text(encoding="utf-8"))
    except Exception:
        return {}
    if not isinstance(data, dict):
        return {}
    return {str(k): str(v).strip() for k, v in data.items() if str(v).strip()}


def save_api_settings(values: Dict[str, Any]) -> None:
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    current = load_saved_api_settings()
    valid_attrs = {f["attr"] for f in API_FIELDS}
    for key, value in values.items():
        if key not in valid_attrs:
            continue
        text_value = str(value or "").strip()
        if text_value:
            current[key] = text_value
        else:
            current.pop(key, None)
    API_SETTINGS_PATH.write_text(json.dumps(current, ensure_ascii=False, indent=2), encoding="utf-8")


def setting(attr: str, env_name: str, default: str = "") -> str:
    # Regra do painel: se .env estiver preenchido, ele ganha. Configuração salva no menu entra como fallback.
    value = env(env_name)
    if value:
        return value
    return load_saved_api_settings().get(attr, default).strip()


def setting_source(attr: str, env_name: str) -> str:
    if env(env_name):
        return ".env"
    if load_saved_api_settings().get(attr):
        return "painel"
    return "vazio"


def mask_secret(value: str) -> str:
    value = str(value or "")
    if not value:
        return ""
    if len(value) <= 10:
        return "•" * len(value)
    return value[:5] + "…" + value[-4:]


@dataclass
class ApiConfig:
    scraperapi: str = field(default_factory=lambda: setting("scraperapi", "SCRAPERAPI_KEY"))
    scrapingbee: str = field(default_factory=lambda: setting("scrapingbee", "SCRAPINGBEE_KEY"))
    scrapedo: str = field(default_factory=lambda: setting("scrapedo", "SCRAPEDO_KEY"))
    brightdata: str = field(default_factory=lambda: setting("brightdata", "BRIGHTDATA_TOKEN"))
    brightdata_zone: str = field(default_factory=lambda: setting("brightdata_zone", "BRIGHTDATA_WEB_UNLOCKER_ZONE"))
    apify: str = field(default_factory=lambda: setting("apify", "APIFY_TOKEN"))
    apify_actor_id: str = field(default_factory=lambda: setting("apify_actor_id", "APIFY_ACTOR_ID", "oneary/google-play-store-scraper"))
    firecrawl: str = field(default_factory=lambda: setting("firecrawl", "FIRECRAWL_KEY"))
    hyperbrowser: str = field(default_factory=lambda: setting("hyperbrowser", "HYPERBROWSER_API_KEY"))
    browserless: str = field(default_factory=lambda: setting("browserless", "BROWSERLESS_TOKEN"))
    browserless_endpoint: str = field(default_factory=lambda: setting("browserless_endpoint", "BROWSERLESS_ENDPOINT", "https://production-sfo.browserless.io"))
    browserbase: str = field(default_factory=lambda: setting("browserbase", "BROWSERBASE_API_KEY"))
    browserbase_project_id: str = field(default_factory=lambda: setting("browserbase_project_id", "BROWSERBASE_PROJECT_ID"))
    scrapingant: str = field(default_factory=lambda: setting("scrapingant", "SCRAPINGANT_KEY"))
    serpapi: str = field(default_factory=lambda: setting("serpapi", "SERPAPI_KEY"))
    searchapi: str = field(default_factory=lambda: setting("searchapi", "SEARCHAPI_KEY"))
    crawlbase: str = field(default_factory=lambda: setting("crawlbase", "CRAWLBASE_KEY"))
    decodo: str = field(default_factory=lambda: setting("decodo", "DECODO_TOKEN"))
    brave_search: str = field(default_factory=lambda: setting("brave_search", "BRAVE_SEARCH_KEY"))
    openwebninja: str = field(default_factory=lambda: setting("openwebninja", "OPENWEBNINJA_KEY"))
    openwebninja_endpoint: str = field(default_factory=lambda: setting("openwebninja_endpoint", "OPENWEBNINJA_ENDPOINT"))

    # Novos providers
    scrapfly: str = field(default_factory=lambda: setting("scrapfly", "SCRAPFLY_KEY"))
    webscraping_ai: str = field(default_factory=lambda: setting("webscraping_ai", "WEBSCRAPING_AI_KEY"))
    zenrows: str = field(default_factory=lambda: setting("zenrows", "ZENROWS_KEY"))
    alterlab: str = field(default_factory=lambda: setting("alterlab", "ALTERLAB_KEY"))
    alterlab_playground: str = field(default_factory=lambda: setting("alterlab_playground", "ALTERLAB_PLAYGROUND_KEY"))
    scavio: str = field(default_factory=lambda: setting("scavio", "SCAVIO_KEY"))
    exa: str = field(default_factory=lambda: setting("exa", "EXA_API_KEY"))
    tavily: str = field(default_factory=lambda: setting("tavily", "TAVILY_API_KEY"))
    youcom: str = field(default_factory=lambda: setting("youcom", "YOU_API_KEY"))
    wolfram: str = field(default_factory=lambda: setting("wolfram", "WOLFRAM_APP_ID"))
    deepseek: str = field(default_factory=lambda: setting("deepseek", "DEEPSEEK_API_KEY"))
    openrouter: str = field(default_factory=lambda: setting("openrouter", "OPENROUTER_API_KEY"))
    groq: str = field(default_factory=lambda: setting("groq", "GROQ_API_KEY"))
    mistral: str = field(default_factory=lambda: setting("mistral", "MISTRAL_API_KEY"))
    gemini: str = field(default_factory=lambda: setting("gemini", "GEMINI_API_KEY"))
    fireworks: str = field(default_factory=lambda: setting("fireworks", "FIREWORKS_API_KEY"))
    cohere: str = field(default_factory=lambda: setting("cohere", "COHERE_API_KEY"))
    nlpcloud: str = field(default_factory=lambda: setting("nlpcloud", "NLPCLOUD_TOKEN"))
    jina: str = field(default_factory=lambda: setting("jina", "JINA_API_KEY"))
    voyage: str = field(default_factory=lambda: setting("voyage", "VOYAGE_API_KEY"))
    replicate: str = field(default_factory=lambda: setting("replicate", "REPLICATE_API_TOKEN"))
    roboflow: str = field(default_factory=lambda: setting("roboflow", "ROBOFLOW_API_KEY"))
    simplescraper: str = field(default_factory=lambda: setting("simplescraper", "SIMPLESCRAPER_KEY"))
    browseai: str = field(default_factory=lambda: setting("browseai", "BROWSEAI_KEY"))
    abstractapi: str = field(default_factory=lambda: setting("abstractapi", "ABSTRACTAPI_KEY"))
    ollama: str = field(default_factory=lambda: setting("ollama", "OLLAMA_API_KEY"))
    cloudflare_token_name: str = field(default_factory=lambda: setting("cloudflare_token_name", "CLOUDFLARE_TOKEN_NAME"))
    cloudflare_account_id: str = field(default_factory=lambda: setting("cloudflare_account_id", "CLOUDFLARE_ACCOUNT_ID"))
    cloudflare_api_token: str = field(default_factory=lambda: setting("cloudflare_api_token", "CLOUDFLARE_API_TOKEN"))
    cloudflare_r2_access_key_id: str = field(default_factory=lambda: setting("cloudflare_r2_access_key_id", "CLOUDFLARE_R2_ACCESS_KEY_ID"))
    cloudflare_r2_secret_access_key: str = field(default_factory=lambda: setting("cloudflare_r2_secret_access_key", "CLOUDFLARE_R2_SECRET_ACCESS_KEY"))
    cloudflare_r2_endpoint: str = field(default_factory=lambda: setting("cloudflare_r2_endpoint", "CLOUDFLARE_R2_ENDPOINT"))

    timeout: int = 35

    def available(self) -> Dict[str, bool]:
        return {
            "ScraperAPI": bool(self.scraperapi),
            "ScrapingBee": bool(self.scrapingbee),
            "Scrape.do": bool(self.scrapedo),
            "Bright Data": bool(self.brightdata and self.brightdata_zone),
            "Apify": bool(self.apify),
            "Firecrawl": bool(self.firecrawl),
            "Hyperbrowser": bool(self.hyperbrowser),
            "Browserless": bool(self.browserless and self.browserless_endpoint),
            "Browserbase": bool(self.browserbase),
            "ScrapingAnt": bool(self.scrapingant),
            "SerpAPI": bool(self.serpapi),
            "SearchAPI": bool(self.searchapi),
            "Crawlbase": bool(self.crawlbase),
            "Decodo": bool(self.decodo),
            "Brave Search": bool(self.brave_search),
            "OpenWebNinja": bool(self.openwebninja and self.openwebninja_endpoint),
            "Scrapfly": bool(self.scrapfly),
            "WebScraping.AI": bool(self.webscraping_ai),
            "ZenRows": bool(self.zenrows),
            "AlterLab": bool(self.alterlab),
            "Scavio": bool(self.scavio),
            "Exa": bool(self.exa),
            "Tavily": bool(self.tavily),
            "You.com": bool(self.youcom),
            "WolframAlpha": bool(self.wolfram),
            "DeepSeek": bool(self.deepseek),
            "OpenRouter": bool(self.openrouter),
            "Groq": bool(self.groq),
            "Mistral": bool(self.mistral),
            "Gemini": bool(self.gemini),
            "Fireworks": bool(self.fireworks),
            "Cohere": bool(self.cohere),
            "NLPCloud": bool(self.nlpcloud),
            "Jina AI": bool(self.jina),
            "Voyage AI": bool(self.voyage),
            "Replicate": bool(self.replicate),
            "Roboflow": bool(self.roboflow),
            "SimpleScraper": bool(self.simplescraper),
            "Browse AI": bool(self.browseai),
            "AbstractAPI": bool(self.abstractapi),
            "Ollama": bool(self.ollama),
            "Cloudflare API Token": bool(self.cloudflare_api_token),
            "Cloudflare R2": bool(self.cloudflare_r2_access_key_id and self.cloudflare_r2_secret_access_key and self.cloudflare_r2_endpoint),
        }

    def enabled_names(self) -> list[str]:
        return [name for name, ok in self.available().items() if ok]

    def has_search_discovery(self) -> bool:
        return bool(self.searchapi or self.brave_search or self.openwebninja or self.exa or self.tavily or self.youcom or self.scavio or self.jina)

    def has_ai_insights(self) -> bool:
        return bool(self.deepseek or self.openrouter or self.groq or self.mistral or self.gemini or self.fireworks or self.cohere or self.nlpcloud)


@dataclass
class RunConfig:
    scope: str = "TODAS"
    level: str = "SIMPLES"
    profile: str = "TODOS"
    quantity: int = 25
    detail_limit: Optional[int] = 25
    reviews_per_app: int = 0
    use_external_apis: bool = False
    use_developer_site: bool = False
    open_html: bool = True
    country: str = "br"
    lang: str = "pt"
    delay: float = 0.20
    max_categories: Optional[int] = None
    output_dir: str = field(default_factory=output_target)
    db_path: str = field(default_factory=database_target)
    exchange_rate_brl: float = 5.40
    include_paid_apps: bool = True
    # CSV de códigos de categorias. Vazio = todas do escopo selecionado.
    category_codes: str = ""
    # CSV de tokens "CATEGORIA::SUBCATEGORIA". Vazio = categoria inteira, sem refinar por subcategoria.
    subcategory_codes: str = ""
    # Busca livre por nome/palavra-chave de app. Quando preenchida, ignora categorias
    # e faz scraping completo (detalhes + reviews, conforme o nível) de todos os apps encontrados.
    search_query: str = ""

    @property
    def financial_enabled(self) -> bool:
        return self.level in {"FINANCEIRO", "FULL", "ULTRA_FULL"}

    @property
    def deep_enabled(self) -> bool:
        return self.level in {"PROFUNDO", "FINANCEIRO", "FULL", "ULTRA_FULL"}

    @property
    def ultra(self) -> bool:
        return self.level == "ULTRA_FULL"

    @property
    def output_path(self) -> Path:
        return Path(self.output_dir)

    @property
    def is_remote_database(self) -> bool:
        value = str(self.db_path or "").lower()
        return value.startswith("postgresql://") or value.startswith("postgres://")

    @property
    def database_path(self) -> Path:
        # Compatibilidade com chamadas locais antigas. Em PostgreSQL não existe pasta de banco.
        return DEFAULT_DB_PATH if self.is_remote_database else Path(self.db_path)

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)

    def to_json(self) -> str:
        return json.dumps(self.to_dict(), ensure_ascii=False, indent=2)

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "RunConfig":
        clean = {k: v for k, v in data.items() if k in cls.__dataclass_fields__}
        # HTML forms mandam string vazia. A gente limpa para o padrão fazer sua mágica.
        for key in ("quantity", "detail_limit", "reviews_per_app", "max_categories"):
            if clean.get(key) == "":
                clean[key] = None
        for key in ("quantity", "detail_limit", "reviews_per_app", "max_categories"):
            if clean.get(key) is not None:
                try:
                    clean[key] = int(clean[key])
                except (TypeError, ValueError):
                    clean.pop(key, None)
        for key in ("delay", "exchange_rate_brl"):
            if clean.get(key) is not None:
                try:
                    clean[key] = float(clean[key])
                except (TypeError, ValueError):
                    clean.pop(key, None)
        for key in ("use_external_apis", "use_developer_site", "open_html", "include_paid_apps"):
            if key in clean:
                clean[key] = str(clean[key]).lower() in {"1", "true", "on", "sim", "s", "yes"}
        cfg = cls(**clean)
        cfg.apply_level_defaults()
        return cfg

    def apply_level_defaults(self, api: Optional[ApiConfig] = None) -> None:
        """Ajusta os controles extras conforme o nível escolhido."""
        self.scope = (self.scope or "TODAS").upper()
        self.level = (self.level or "SIMPLES").upper()
        self.profile = (self.profile or "TODOS").upper()
        self.search_query = str(self.search_query or "").strip()
        self.category_codes = ",".join([c.strip().upper() for c in str(self.category_codes or "").replace(";", ",").split(",") if c.strip()])
        self.subcategory_codes = ",".join([c.strip().upper() for c in str(self.subcategory_codes or "").replace(";", ",").split(",") if c.strip() and "::" in c])
        if self.scope == "TODAS":
            self.category_codes = ""
            self.subcategory_codes = ""
        if self.quantity <= 0:
            self.quantity = 25

        if self.level == "SIMPLES":
            self.detail_limit = self.detail_limit or min(self.quantity, 25)
            self.reviews_per_app = self.reviews_per_app or 0
            self.use_external_apis = False
            self.use_developer_site = False
            self.delay = max(self.delay, 0.15)
        elif self.level == "PROFUNDO":
            self.detail_limit = self.detail_limit or self.quantity
            self.reviews_per_app = self.reviews_per_app or 20
            self.use_external_apis = False
            self.use_developer_site = False
            self.delay = max(self.delay, 0.22)
        elif self.level == "FINANCEIRO":
            self.detail_limit = self.detail_limit or self.quantity
            self.reviews_per_app = self.reviews_per_app or 25
            if api:
                self.use_external_apis = bool(api.serpapi or api.firecrawl)
            self.delay = max(self.delay, 0.26)
        elif self.level == "FULL":
            self.detail_limit = self.detail_limit or self.quantity
            self.reviews_per_app = self.reviews_per_app or 50
            if api:
                self.use_external_apis = any(api.available().values())
            self.delay = max(self.delay, 0.32)
        elif self.level == "ULTRA_FULL":
            self.detail_limit = None
            self.reviews_per_app = self.reviews_per_app or 150
            if api:
                self.use_external_apis = any(api.available().values())
            self.use_developer_site = True
            self.delay = max(self.delay, 0.38)
        else:
            self.level = "SIMPLES"
            self.apply_level_defaults(api)


def default_config_for_level(level: str, api: Optional[ApiConfig] = None) -> RunConfig:
    cfg = RunConfig(level=level)
    cfg.apply_level_defaults(api)
    return cfg
