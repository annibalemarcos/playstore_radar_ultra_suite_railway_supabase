"""Integrações opcionais com APIs externas.

A ideia aqui não é depender dessas APIs para tudo: google-play-scraper já resolve a base.
As APIs extras entram para: pegar HTML/render, completar metadados, acessar SERP e enriquecer descrição.
"""
from __future__ import annotations

import json
import time
from typing import Any, Dict, List, Tuple
from urllib.parse import parse_qs, quote_plus, urlparse

import requests
from bs4 import BeautifulSoup

from .config import ApiConfig, RunConfig
from .scoring import app_link


class ExternalClient:
    def __init__(self, api: ApiConfig):
        self.api = api
        self.session = requests.Session()
        self.session.headers.update(
            {
                "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/126 Safari/537.36",
                "Accept-Language": "pt-BR,pt;q=0.9,en-US;q=0.8,en;q=0.7",
            }
        )

    def _safe_get(self, *args: Any, **kwargs: Any) -> requests.Response:
        kwargs.setdefault("timeout", self.api.timeout)
        return self.session.get(*args, **kwargs)

    def _safe_post(self, *args: Any, **kwargs: Any) -> requests.Response:
        kwargs.setdefault("timeout", self.api.timeout)
        return self.session.post(*args, **kwargs)

    def fetch_html(self, url: str, cfg: RunConfig) -> Tuple[str, str, Dict[str, Any]]:
        """Tenta buscar HTML/texto por providers. Retorna (provider, text, meta)."""
        providers = []
        if self.api.firecrawl:
            providers.append(self._firecrawl)
        if self.api.hyperbrowser:
            providers.append(self._hyperbrowser)
        if self.api.browserless and self.api.browserless_endpoint:
            providers.append(self._browserless)
        if self.api.browserbase:
            providers.append(self._browserbase)
        if self.api.scrapingbee:
            providers.append(self._scrapingbee)
        if self.api.scrapingant:
            providers.append(self._scrapingant)
        if self.api.scrapedo:
            providers.append(self._scrapedo)
        if self.api.scraperapi:
            providers.append(self._scraperapi)
        if self.api.crawlbase:
            providers.append(self._crawlbase)
        if self.api.decodo:
            providers.append(self._decodo)
        if self.api.scrapfly:
            providers.append(self._scrapfly)
        if self.api.webscraping_ai:
            providers.append(self._webscraping_ai)
        if self.api.zenrows:
            providers.append(self._zenrows)
        if self.api.alterlab:
            providers.append(self._alterlab)
        if self.api.jina:
            providers.append(self._jina_reader)
        if self.api.brightdata and self.api.brightdata_zone:
            providers.append(self._brightdata)
        # OpenWebNinja tem endpoints específicos (ex.: search). Só entra aqui se o endpoint
        # informado parecer ser de fetch/scrape; endpoint de busca é usado em openwebninja_play_search().
        if self.api.openwebninja and self.api.openwebninja_endpoint and "/search" not in self.api.openwebninja_endpoint.lower():
            providers.append(self._openwebninja)
        providers.append(self._direct)

        errors: Dict[str, str] = {}
        for provider in providers:
            name = provider.__name__.replace("_", "").replace("firecrawl", "Firecrawl")
            try:
                p_name, text, meta = provider(url, cfg)
                if text and len(text.strip()) > 120:
                    return p_name, text, meta
                errors[p_name] = "resposta vazia/curta"
            except Exception as exc:  # noqa: BLE001
                errors[name] = str(exc)[:300]
        return "none", "", {"errors": errors}

    def _direct(self, url: str, cfg: RunConfig) -> Tuple[str, str, Dict[str, Any]]:
        res = self._safe_get(url)
        return "Direct", res.text, {"status": res.status_code}

    def _scraperapi(self, url: str, cfg: RunConfig) -> Tuple[str, str, Dict[str, Any]]:
        params = {
            "api_key": self.api.scraperapi,
            "url": url,
            "country_code": cfg.country,
            "render": "true" if cfg.level in {"FULL", "ULTRA_FULL"} else "false",
        }
        res = self._safe_get("https://api.scraperapi.com/", params=params)
        return "ScraperAPI", res.text, {"status": res.status_code}

    def _scrapingbee(self, url: str, cfg: RunConfig) -> Tuple[str, str, Dict[str, Any]]:
        params = {
            "api_key": self.api.scrapingbee,
            "url": url,
            "render_js": "true" if cfg.level in {"FULL", "ULTRA_FULL"} else "false",
            "country_code": cfg.country,
        }
        res = self._safe_get("https://app.scrapingbee.com/api/v1", params=params)
        return "ScrapingBee", res.text, {"status": res.status_code}

    def _scrapedo(self, url: str, cfg: RunConfig) -> Tuple[str, str, Dict[str, Any]]:
        params = {
            "token": self.api.scrapedo,
            "url": url,
            "render": "true" if cfg.level in {"FULL", "ULTRA_FULL"} else "false",
        }
        res = self._safe_get("https://api.scrape.do/", params=params)
        return "Scrape.do", res.text, {"status": res.status_code}

    def _brightdata(self, url: str, cfg: RunConfig) -> Tuple[str, str, Dict[str, Any]]:
        headers = {"Authorization": f"Bearer {self.api.brightdata}", "Content-Type": "application/json"}
        payload = {"zone": self.api.brightdata_zone, "url": url, "format": "raw"}
        res = self._safe_post("https://api.brightdata.com/request", headers=headers, json=payload)
        return "Bright Data", res.text, {"status": res.status_code}

    def _firecrawl(self, url: str, cfg: RunConfig) -> Tuple[str, str, Dict[str, Any]]:
        headers = {"Authorization": f"Bearer {self.api.firecrawl}", "Content-Type": "application/json"}
        payload = {"url": url, "formats": ["markdown", "html"]}
        # v2 é o caminho atual; se a conta/lib estiver em v1, tenta v1 em seguida.
        for endpoint in ("https://api.firecrawl.dev/v2/scrape", "https://api.firecrawl.dev/v1/scrape"):
            res = self._safe_post(endpoint, headers=headers, json=payload)
            try:
                data = res.json()
            except Exception:
                data = {}
            text = ""
            if isinstance(data, dict):
                inner = data.get("data") or data
                if isinstance(inner, dict):
                    text = inner.get("markdown") or inner.get("html") or inner.get("content") or ""
            if text:
                return "Firecrawl", text, {"status": res.status_code, "endpoint": endpoint, "json": data}
        return "Firecrawl", "", {"status": 0}

    def _scrapingant(self, url: str, cfg: RunConfig) -> Tuple[str, str, Dict[str, Any]]:
        params = {"url": url, "x-api-key": self.api.scrapingant}
        if cfg.level in {"FULL", "ULTRA_FULL"}:
            params["browser"] = "true"
        res = self._safe_get("https://api.scrapingant.com/v2/general", params=params)
        return "ScrapingAnt", res.text, {"status": res.status_code}

    def _crawlbase(self, url: str, cfg: RunConfig) -> Tuple[str, str, Dict[str, Any]]:
        params = {"token": self.api.crawlbase, "url": url, "country": cfg.country.upper()}
        res = self._safe_get("https://api.crawlbase.com/", params=params)
        return "Crawlbase", res.text, {"status": res.status_code, "remaining": res.headers.get("remaining")}


    def _decodo(self, url: str, cfg: RunConfig) -> Tuple[str, str, Dict[str, Any]]:
        """Decodo Web Scraping API síncrona.

        A Decodo usa Authorization: Basic <TOKEN> e retorna JSON com results[0].content.
        Mantemos o payload mínimo para evitar custo extra com renderização até o usuário pedir.
        """
        headers = {
            "Accept": "application/json",
            "Authorization": f"Basic {self.api.decodo}",
            "Content-Type": "application/json",
        }
        payload: Dict[str, Any] = {"url": url}
        res = self._safe_post("https://scraper-api.decodo.com/v2/scrape", headers=headers, json=payload, timeout=max(45, self.api.timeout))
        text = res.text
        meta: Dict[str, Any] = {"status": res.status_code}
        try:
            data = res.json()
            meta["json"] = data
            results = data.get("results") if isinstance(data, dict) else None
            if isinstance(results, list) and results:
                first = results[0] if isinstance(results[0], dict) else {}
                text = str(first.get("content") or text)
                meta["target_status_code"] = first.get("status_code")
                meta["task_id"] = first.get("task_id")
        except Exception:
            pass
        return "Decodo", text, meta


    def _scrapfly(self, url: str, cfg: RunConfig) -> Tuple[str, str, Dict[str, Any]]:
        params = {
            "key": self.api.scrapfly,
            "url": url,
            "render_js": "true" if cfg.level in {"FULL", "ULTRA_FULL"} else "false",
            "country": cfg.country.lower(),
        }
        res = self._safe_get("https://api.scrapfly.io/scrape", params=params)
        text = res.text
        meta: Dict[str, Any] = {"status": res.status_code}
        try:
            data = res.json()
            meta["json"] = data
            result = data.get("result") if isinstance(data, dict) else None
            if isinstance(result, dict):
                content = result.get("content") or result.get("browser_data", {}).get("html")
                if content:
                    text = str(content)
        except Exception:
            pass
        return "Scrapfly", text, meta

    def _webscraping_ai(self, url: str, cfg: RunConfig) -> Tuple[str, str, Dict[str, Any]]:
        params = {
            "api_key": self.api.webscraping_ai,
            "url": url,
            "js": "true" if cfg.level in {"FULL", "ULTRA_FULL"} else "false",
            "timeout": min(max(self.api.timeout, 10), 60),
        }
        res = self._safe_get("https://api.webscraping.ai/html", params=params)
        return "WebScraping.AI", res.text, {"status": res.status_code}

    def _zenrows(self, url: str, cfg: RunConfig) -> Tuple[str, str, Dict[str, Any]]:
        params = {
            "apikey": self.api.zenrows,
            "url": url,
            "js_render": "true" if cfg.level in {"FULL", "ULTRA_FULL"} else "false",
        }
        if cfg.country:
            params["proxy_country"] = cfg.country.lower()
        res = self._safe_get("https://api.zenrows.com/v1/", params=params)
        return "ZenRows", res.text, {"status": res.status_code}

    def _alterlab(self, url: str, cfg: RunConfig) -> Tuple[str, str, Dict[str, Any]]:
        headers = {"X-API-Key": self.api.alterlab, "Content-Type": "application/json", "Accept": "application/json"}
        payload: Dict[str, Any] = {"url": url, "mode": "auto"}
        if cfg.level in {"FULL", "ULTRA_FULL"}:
            payload["advanced"] = {"markdown": True, "render_js": True}
        res = self._safe_post("https://api.alterlab.io/api/v1/scrape", headers=headers, json=payload, timeout=max(45, self.api.timeout))
        text = res.text
        meta: Dict[str, Any] = {"status": res.status_code}
        try:
            data = res.json()
            meta["json"] = data
            content = data.get("content") if isinstance(data, dict) else None
            if isinstance(content, dict):
                text = content.get("markdown") or content.get("html") or json.dumps(content, ensure_ascii=False)
            elif content:
                text = str(content)
            meta["billing"] = data.get("billing") if isinstance(data, dict) else None
        except Exception:
            pass
        return "AlterLab", text, meta

    @classmethod
    def _payload_text(cls, data: Any) -> str:
        if isinstance(data, str):
            return data
        if isinstance(data, dict):
            for key in ("markdown", "html", "content", "text"):
                value = data.get(key)
                if isinstance(value, str) and value.strip():
                    return value
            for key in ("data", "result", "page", "document"):
                value = data.get(key)
                text = cls._payload_text(value)
                if text:
                    return text
        if isinstance(data, list):
            for item in data:
                text = cls._payload_text(item)
                if text:
                    return text
        return ""

    def _hyperbrowser(self, url: str, cfg: RunConfig) -> Tuple[str, str, Dict[str, Any]]:
        headers = {"x-api-key": self.api.hyperbrowser, "Content-Type": "application/json", "Accept": "application/json"}
        payload: Dict[str, Any] = {
            "url": url,
            "formats": ["markdown", "html"],
            "scrapeOptions": {"onlyMainContent": False},
        }
        res = self._safe_post("https://api.hyperbrowser.ai/api/scrape", headers=headers, json=payload, timeout=max(45, self.api.timeout))
        meta: Dict[str, Any] = {"status": res.status_code}
        text = res.text
        try:
            data = res.json()
            meta["json"] = data
            text = self._payload_text(data) or text
            job_id = (data.get("id") or data.get("jobId")) if isinstance(data, dict) else ""
            if job_id and len(str(text).strip()) <= 120:
                for _attempt in range(8):
                    time.sleep(1.5)
                    poll = self._safe_get(f"https://api.hyperbrowser.ai/api/scrape/{job_id}", headers={"x-api-key": self.api.hyperbrowser, "Accept": "application/json"}, timeout=max(45, self.api.timeout))
                    meta["poll_status"] = poll.status_code
                    try:
                        poll_data = poll.json()
                    except Exception:
                        poll_data = {"text": poll.text}
                    meta["poll_json"] = poll_data
                    text = self._payload_text(poll_data) or text
                    status = str(poll_data.get("status") or "").lower() if isinstance(poll_data, dict) else ""
                    if text and len(text.strip()) > 120:
                        break
                    if status in {"failed", "stopped", "completed"}:
                        break
        except Exception:
            pass
        return "Hyperbrowser", text, meta

    def _browserless(self, url: str, cfg: RunConfig) -> Tuple[str, str, Dict[str, Any]]:
        endpoint = (self.api.browserless_endpoint or "https://production-sfo.browserless.io").rstrip("/")
        payload = {"url": url, "formats": ["html", "markdown"]}
        res = self._safe_post(f"{endpoint}/smart-scrape", params={"token": self.api.browserless}, headers={"Content-Type": "application/json", "Accept": "application/json"}, json=payload, timeout=max(45, self.api.timeout))
        text = res.text
        meta: Dict[str, Any] = {"status": res.status_code}
        try:
            data = res.json()
            meta["json"] = data
            text = self._payload_text(data) or text
        except Exception:
            pass
        return "Browserless", text, meta

    def _browserbase(self, url: str, cfg: RunConfig) -> Tuple[str, str, Dict[str, Any]]:
        headers = {"X-BB-API-Key": self.api.browserbase, "Content-Type": "application/json", "Accept": "application/json"}
        payload: Dict[str, Any] = {
            "url": url,
            "allowRedirects": True,
            "allowInsecureSsl": False,
            "proxies": False,
            "format": "markdown",
        }
        res = self._safe_post("https://api.browserbase.com/v1/fetch", headers=headers, json=payload, timeout=max(45, self.api.timeout))
        text = res.text
        meta: Dict[str, Any] = {"status": res.status_code}
        try:
            data = res.json()
            meta["json"] = data
            text = self._payload_text(data) or text
        except Exception:
            pass
        return "Browserbase", text, meta

    def _jina_reader(self, url: str, cfg: RunConfig) -> Tuple[str, str, Dict[str, Any]]:
        headers = {"Accept": "text/plain"}
        if self.api.jina:
            headers["Authorization"] = f"Bearer {self.api.jina}"
        # Jina Reader: basta prefixar https://r.jina.ai/ ao URL alvo.
        res = self._safe_get("https://r.jina.ai/" + url, headers=headers, timeout=max(45, self.api.timeout))
        return "Jina AI", res.text, {"status": res.status_code, "endpoint": "r.jina.ai"}

    def _brave_headers(self) -> Dict[str, str]:
        return {
            "Accept": "application/json",
            "Accept-Encoding": "gzip",
            "X-Subscription-Token": self.api.brave_search,
        }

    def brave_web_search(self, query: str, cfg: RunConfig, count: int = 10) -> Dict[str, Any]:
        if not self.api.brave_search:
            return {}
        params = {
            "q": query,
            "count": max(1, min(int(count or 10), 20)),
            "safesearch": "moderate",
            "result_filter": "web",
            "text_decorations": "false",
        }
        # A API aceita localidade via parâmetros/headers; manter simples é mais estável.
        if cfg.lang:
            params["search_lang"] = "pt-br" if cfg.lang.lower().startswith("pt") else cfg.lang.lower()
        if cfg.country:
            params["country"] = cfg.country.upper()
        res = self._safe_get("https://api.search.brave.com/res/v1/web/search", params=params, headers=self._brave_headers())
        try:
            return res.json()
        except Exception:
            return {"_brave_error": res.text[:500], "status_code": res.status_code}

    def brave_play_search(self, query: str, cfg: RunConfig) -> List[Dict[str, Any]]:
        """Usa Brave Search como radar de Play Store, não como fonte principal."""
        if not self.api.brave_search:
            return []
        search_query = f'site:play.google.com/store/apps/details {query}'
        data = self.brave_web_search(search_query, cfg, count=min(max(cfg.quantity, 5), 20))
        results = []
        if isinstance(data, dict):
            web = data.get("web") or {}
            if isinstance(web, dict) and isinstance(web.get("results"), list):
                results = web.get("results") or []
        out: List[Dict[str, Any]] = []
        for item in results:
            if not isinstance(item, dict):
                continue
            url = str(item.get("url") or item.get("link") or "")
            app_id = self._extract_app_id_from_url(url)
            if not app_id:
                continue
            title = str(item.get("title") or app_id)
            normalized = {
                "appId": app_id,
                "title": title.replace(" - Apps on Google Play", "").replace(" – Apps no Google Play", ""),
                "summary": item.get("description") or item.get("snippet"),
                "url": url,
                "_brave_raw_preview": json.dumps(item, ensure_ascii=False)[:1500],
            }
            out.append({k: v for k, v in normalized.items() if v not in (None, "", [], {})})
        return out

    def _openwebninja_headers(self) -> Dict[str, str]:
        return {"X-API-Key": self.api.openwebninja, "Accept": "application/json"}

    def _openwebninja(self, url: str, cfg: RunConfig) -> Tuple[str, str, Dict[str, Any]]:
        """Fetch genérico via OpenWebNinja, quando o endpoint configurado aceitar URL.

        Para endpoints específicos de busca, como /play-store-apps/search, use
        openwebninja_play_search().
        """
        headers = {**self._openwebninja_headers(), "Content-Type": "application/json"}
        payload = {"url": url}
        res = self._safe_post(self.api.openwebninja_endpoint, headers=headers, json=payload)
        try:
            data = res.json()
            text = json.dumps(data, ensure_ascii=False)[:200_000]
        except Exception:
            data = {}
            text = res.text
        return "OpenWebNinja", text, {"status": res.status_code, "json": data}

    @staticmethod
    def _extract_app_id_from_url(value: str) -> str:
        if not value:
            return ""
        try:
            parsed = urlparse(value)
            qs = parse_qs(parsed.query)
            if qs.get("id"):
                return qs["id"][0]
        except Exception:
            pass
        return ""

    @classmethod
    def _normalize_openwebninja_results(cls, data: Any) -> List[Dict[str, Any]]:
        """Converte formatos comuns do OpenWebNinja em candidatos compatíveis com o motor."""
        if isinstance(data, list):
            raw_items = data
        elif isinstance(data, dict):
            raw_items = []
            for key in ("items", "apps", "results", "data", "organic_results"):
                value = data.get(key)
                if isinstance(value, list):
                    raw_items = value
                    break
                if isinstance(value, dict):
                    for nested_key in ("items", "apps", "results"):
                        nested = value.get(nested_key)
                        if isinstance(nested, list):
                            raw_items = nested
                            break
                    if raw_items:
                        break
        else:
            raw_items = []

        out: List[Dict[str, Any]] = []
        for item in raw_items:
            if not isinstance(item, dict):
                continue
            url = item.get("url") or item.get("link") or item.get("appUrl") or item.get("app_url") or ""
            app_id = (
                item.get("appId")
                or item.get("app_id")
                or item.get("packageName")
                or item.get("package_name")
                or cls._extract_app_id_from_url(str(url))
            )
            if not app_id:
                continue
            normalized = {
                "appId": app_id,
                "title": item.get("title") or item.get("name") or item.get("appName") or item.get("app_name") or app_id,
                "developer": item.get("developer") or item.get("developerName") or item.get("developer_name"),
                "summary": item.get("summary") or item.get("description") or item.get("snippet"),
                "score": item.get("score") or item.get("rating") or item.get("stars"),
                "ratings": item.get("ratings") or item.get("reviews") or item.get("reviewsCount"),
                "installs": item.get("installs") or item.get("downloads"),
                "free": item.get("free"),
                "price": item.get("price"),
                "url": url or f"https://play.google.com/store/apps/details?id={app_id}",
                "_openwebninja_raw_preview": json.dumps(item, ensure_ascii=False)[:1500],
            }
            out.append({k: v for k, v in normalized.items() if v not in (None, "", [], {})})
        return out

    def openwebninja_play_search(self, query: str, cfg: RunConfig) -> List[Dict[str, Any]]:
        """Busca apps no endpoint: https://api.openwebninja.com/play-store-apps/search?q=..."""
        if not self.api.openwebninja or not self.api.openwebninja_endpoint:
            return []
        endpoint = self.api.openwebninja_endpoint.strip()
        if not endpoint:
            return []
        headers = self._openwebninja_headers()
        params = {"q": query}
        res = self._safe_get(endpoint, params=params, headers=headers)
        try:
            data = res.json()
        except Exception:
            return []
        return self._normalize_openwebninja_results(data)


    @classmethod
    def _normalize_searchapi_results(cls, data: Any) -> List[Dict[str, Any]]:
        raw_items: List[Any] = []
        if isinstance(data, dict):
            for key in ("items", "apps", "results"):
                value = data.get(key)
                if isinstance(value, list):
                    raw_items.extend(value)
            organic = data.get("organic_results")
            if isinstance(organic, list):
                for group in organic:
                    if isinstance(group, dict) and isinstance(group.get("items"), list):
                        raw_items.extend(group.get("items") or [])
                    elif isinstance(group, dict):
                        raw_items.append(group)
            highlights = data.get("highlights")
            if isinstance(highlights, list):
                raw_items.extend(highlights)
        elif isinstance(data, list):
            raw_items = data

        out: List[Dict[str, Any]] = []
        for item in raw_items:
            if not isinstance(item, dict):
                continue
            product = item.get("product") if isinstance(item.get("product"), dict) else {}
            url = str(item.get("link") or item.get("url") or product.get("link") or "")
            app_id = item.get("product_id") or item.get("id") or product.get("product_id") or cls._extract_app_id_from_url(url)
            if not app_id:
                continue
            title = str(item.get("title") or product.get("title") or app_id)
            author = product.get("author") if isinstance(product.get("author"), dict) else {}
            normalized = {
                "appId": app_id,
                "title": title.replace(" - Apps on Google Play", "").replace(" – Apps no Google Play", ""),
                "developer": item.get("developer") or item.get("author") or author.get("name"),
                "summary": item.get("description") or item.get("snippet") or item.get("subtitle"),
                "score": item.get("rating") or item.get("score"),
                "genre": item.get("category"),
                "icon": item.get("thumbnail") or item.get("icon"),
                "url": url or f"https://play.google.com/store/apps/details?id={app_id}",
                "_searchapi_raw_preview": json.dumps(item, ensure_ascii=False)[:1500],
            }
            out.append({k: v for k, v in normalized.items() if v not in (None, "", [], {})})
        return out

    def searchapi_play_search(self, query: str, cfg: RunConfig) -> List[Dict[str, Any]]:
        if not self.api.searchapi:
            return []
        params = {
            "engine": "google_play_store",
            "store": "apps",
            "q": query,
            "hl": cfg.lang,
            "gl": cfg.country,
            "api_key": self.api.searchapi,
        }
        res = self._safe_get("https://www.searchapi.io/api/v1/search", params=params, timeout=max(45, self.api.timeout))
        try:
            data = res.json()
        except Exception:
            return []
        return self._normalize_searchapi_results(data)

    def searchapi_product(self, app_id: str, cfg: RunConfig) -> Dict[str, Any]:
        if not self.api.searchapi or not app_id:
            return {}
        params = {
            "engine": "google_play_product",
            "store": "apps",
            "product_id": app_id,
            "hl": cfg.lang,
            "gl": cfg.country,
            "api_key": self.api.searchapi,
        }
        res = self._safe_get("https://www.searchapi.io/api/v1/search", params=params, timeout=max(45, self.api.timeout))
        try:
            return res.json()
        except Exception:
            return {"_searchapi_error": res.text[:500], "status_code": res.status_code}


    @classmethod
    def _normalize_web_results(cls, data: Any, source_key: str = "_search_raw_preview") -> List[Dict[str, Any]]:
        """Normaliza resultados de buscadores genéricos para candidatos Play Store."""
        raw_items: List[Any] = []
        if isinstance(data, list):
            raw_items = data
        elif isinstance(data, dict):
            for key in ("results", "organic_results", "items", "data"):
                value = data.get(key)
                if isinstance(value, list):
                    raw_items = value
                    break
            if not raw_items:
                for parent in ("web", "response", "answer"):
                    value = data.get(parent)
                    if isinstance(value, dict):
                        for key in ("results", "organic_results", "items"):
                            nested = value.get(key)
                            if isinstance(nested, list):
                                raw_items = nested
                                break
                    if raw_items:
                        break
        out: List[Dict[str, Any]] = []
        for item in raw_items:
            if not isinstance(item, dict):
                continue
            url = str(item.get("url") or item.get("link") or item.get("href") or "")
            app_id = cls._extract_app_id_from_url(url)
            if not app_id:
                continue
            title = str(item.get("title") or item.get("name") or app_id)
            desc = item.get("description") or item.get("snippet") or item.get("content") or item.get("text")
            out.append({
                "appId": app_id,
                "title": title.replace(" - Apps on Google Play", "").replace(" – Apps no Google Play", ""),
                "summary": desc,
                "url": url,
                source_key: json.dumps(item, ensure_ascii=False)[:1500],
            })
        return out

    def exa_play_search(self, query: str, cfg: RunConfig) -> List[Dict[str, Any]]:
        if not self.api.exa:
            return []
        headers = {"x-api-key": self.api.exa, "Content-Type": "application/json", "Accept": "application/json"}
        payload = {
            "query": f'site:play.google.com/store/apps/details {query}',
            "numResults": min(max(cfg.quantity, 5), 10),
            "contents": {"text": {"maxCharacters": 400}},
        }
        res = self._safe_post("https://api.exa.ai/search", headers=headers, json=payload, timeout=max(45, self.api.timeout))
        try:
            return self._normalize_web_results(res.json(), "_exa_raw_preview")
        except Exception:
            return []

    def tavily_play_search(self, query: str, cfg: RunConfig) -> List[Dict[str, Any]]:
        if not self.api.tavily:
            return []
        headers = {"Authorization": f"Bearer {self.api.tavily}", "Content-Type": "application/json", "Accept": "application/json"}
        payload = {
            "query": f'site:play.google.com/store/apps/details {query}',
            "max_results": min(max(cfg.quantity, 5), 10),
            "search_depth": "basic",
            "include_answer": False,
            "include_raw_content": False,
        }
        res = self._safe_post("https://api.tavily.com/search", headers=headers, json=payload, timeout=max(45, self.api.timeout))
        try:
            return self._normalize_web_results(res.json(), "_tavily_raw_preview")
        except Exception:
            return []

    def you_play_search(self, query: str, cfg: RunConfig) -> List[Dict[str, Any]]:
        if not self.api.youcom:
            return []
        headers = {"X-API-Key": self.api.youcom, "Accept": "application/json"}
        params = {"query": f'site:play.google.com/store/apps/details {query}', "count": min(max(cfg.quantity, 5), 10), "safesearch": "moderate"}
        if cfg.country:
            params["country"] = cfg.country.upper()
        if cfg.lang:
            params["language"] = "pt" if cfg.lang.lower().startswith("pt") else cfg.lang.lower()
        res = self._safe_get("https://api.ydc-index.io/search", headers=headers, params=params, timeout=max(45, self.api.timeout))
        try:
            return self._normalize_web_results(res.json(), "_you_raw_preview")
        except Exception:
            return []

    def scavio_play_search(self, query: str, cfg: RunConfig) -> List[Dict[str, Any]]:
        if not self.api.scavio:
            return []
        headers = {"Authorization": f"Bearer {self.api.scavio}", "Content-Type": "application/json", "Accept": "application/json"}
        payload = {"query": f'site:play.google.com/store/apps/details {query}', "hl": cfg.lang, "gl": cfg.country, "device": "desktop"}
        # v2 é a referência atual, v1 é mantido como fallback porque apareceu na quickstart pública.
        for endpoint in ("https://api.scavio.dev/api/v2/google", "https://api.scavio.dev/api/v1/google"):
            try:
                res = self._safe_post(endpoint, headers=headers, json=payload, timeout=max(45, self.api.timeout))
                data = res.json()
                normalized = self._normalize_web_results(data, "_scavio_raw_preview")
                if normalized:
                    return normalized
            except Exception:
                continue
        return []

    def jina_play_search(self, query: str, cfg: RunConfig) -> List[Dict[str, Any]]:
        if not self.api.jina:
            return []
        headers = {"Authorization": f"Bearer {self.api.jina}", "Accept": "application/json"}
        search_query = quote_plus(f'site:play.google.com/store/apps/details {query}')
        res = self._safe_get(f"https://s.jina.ai/{search_query}", headers=headers, timeout=max(45, self.api.timeout))
        try:
            data = res.json()
        except Exception:
            data = {"results": []}
            # Fallback texto: extrai URLs da resposta markdown.
            text = res.text or ""
            items = []
            for match in set(__import__('re').findall(r'https://play\.google\.com/store/apps/details\?[^\s)]+', text)):
                items.append({"url": match, "title": self._extract_app_id_from_url(match), "description": "Jina Search"})
            data["results"] = items
        return self._normalize_web_results(data, "_jina_search_raw_preview")

    def ai_app_insight(self, app_data: Dict[str, Any], cfg: RunConfig) -> Dict[str, Any]:
        """Gera um mini parecer de oportunidade com o primeiro LLM configurado.

        É propositalmente curto para não queimar token à toa.
        """
        prompt = (
            "Analise este app da Google Play em português do Brasil. Responda em 5 linhas curtas: "
            "1) o que parece ser, 2) público-alvo, 3) monetização provável, "
            "4) oportunidade para copiar/melhorar, 5) risco/alerta.\n\n"
            + json.dumps({
                "title": app_data.get("title"),
                "developer": app_data.get("developer"),
                "category": app_data.get("categoria") or app_data.get("genre"),
                "summary": app_data.get("summary"),
                "description": str(app_data.get("description") or "")[:1200],
                "score": app_data.get("score"),
                "installs": app_data.get("installs") or app_data.get("realInstalls"),
                "reviews_keywords": app_data.get("review_keywords"),
                "financial_notes": app_data.get("financial_notes"),
            }, ensure_ascii=False)
        )
        providers = [
            ("DeepSeek", self.api.deepseek, "https://api.deepseek.com/chat/completions", "deepseek-chat"),
            ("OpenRouter", self.api.openrouter, "https://openrouter.ai/api/v1/chat/completions", "openai/gpt-4.1-mini"),
            ("Groq", self.api.groq, "https://api.groq.com/openai/v1/chat/completions", "llama-3.1-8b-instant"),
            ("Mistral", self.api.mistral, "https://api.mistral.ai/v1/chat/completions", "mistral-small-latest"),
            ("Fireworks", self.api.fireworks, "https://api.fireworks.ai/inference/v1/chat/completions", "accounts/fireworks/models/llama-v3p1-8b-instruct"),
        ]
        for name, key, endpoint, model in providers:
            if not key:
                continue
            try:
                headers = {"Authorization": f"Bearer {key}", "Content-Type": "application/json"}
                if name == "OpenRouter":
                    headers.update({"HTTP-Referer": "http://127.0.0.1:5892", "X-Title": "PlayStore Radar Ultra"})
                payload = {"model": model, "messages": [{"role": "user", "content": prompt}], "temperature": 0.2, "max_tokens": 360}
                res = self._safe_post(endpoint, headers=headers, json=payload, timeout=max(45, self.api.timeout))
                data = res.json()
                choices = data.get("choices") if isinstance(data, dict) else None
                if isinstance(choices, list) and choices:
                    msg = choices[0].get("message") or {}
                    content = msg.get("content") or choices[0].get("text")
                    if content:
                        return {"ai_provider_used": name, "ai_opportunity_brief": str(content).strip(), "ai_meta": json.dumps({"status": res.status_code}, ensure_ascii=False)}
            except Exception:
                continue
        # Gemini tem formato diferente; tenta por último.
        if self.api.gemini:
            try:
                endpoint = f"https://generativelanguage.googleapis.com/v1beta/models/gemini-1.5-flash:generateContent?key={self.api.gemini}"
                res = self._safe_post(endpoint, json={"contents": [{"parts": [{"text": prompt}]}]}, timeout=max(45, self.api.timeout))
                data = res.json()
                candidates = data.get("candidates") if isinstance(data, dict) else None
                if isinstance(candidates, list) and candidates:
                    parts = candidates[0].get("content", {}).get("parts", [])
                    text = "\n".join([p.get("text", "") for p in parts if isinstance(p, dict)]).strip()
                    if text:
                        return {"ai_provider_used": "Gemini", "ai_opportunity_brief": text, "ai_meta": json.dumps({"status": res.status_code}, ensure_ascii=False)}
            except Exception:
                pass
        return {}

    def serpapi_play_search(self, query: str, cfg: RunConfig) -> Dict[str, Any]:
        if not self.api.serpapi:
            return {}
        params = {
            "engine": "google_play",
            "q": query,
            "store": "apps",
            "hl": cfg.lang,
            "gl": cfg.country,
            "api_key": self.api.serpapi,
        }
        res = self._safe_get("https://serpapi.com/search", params=params)
        try:
            return res.json()
        except Exception:
            return {"_serpapi_error": res.text[:500]}

    def serpapi_product(self, app_id: str, cfg: RunConfig) -> Dict[str, Any]:
        if not self.api.serpapi or not app_id:
            return {}
        params = {
            "engine": "google_play_product",
            "product_id": app_id,
            "store": "apps",
            "hl": cfg.lang,
            "gl": cfg.country,
            "api_key": self.api.serpapi,
        }
        res = self._safe_get("https://serpapi.com/search", params=params)
        try:
            return res.json()
        except Exception:
            return {"_serpapi_error": res.text[:500]}

    def apify_google_play(self, query_or_url: str, cfg: RunConfig) -> List[Dict[str, Any]]:
        if not self.api.apify:
            return []
        actor_id = (self.api.apify_actor_id or "oneary/google-play-store-scraper").replace("/", "~")
        endpoint = f"https://api.apify.com/v2/acts/{actor_id}/run-sync-get-dataset-items"
        params = {"token": self.api.apify}
        payload = {
            "search": query_or_url,
            "country": cfg.country,
            "language": cfg.lang,
            "maxItems": max(10, cfg.quantity),
        }
        res = self._safe_post(endpoint, params=params, json=payload, timeout=max(60, self.api.timeout))
        try:
            data = res.json()
            return data if isinstance(data, list) else []
        except Exception:
            return []


def extract_basic_meta(text: str) -> Dict[str, Any]:
    if not text:
        return {}
    soup = BeautifulSoup(text[:500_000], "html.parser")
    title = soup.title.get_text(" ", strip=True) if soup.title else ""
    desc = ""
    for sel in [
        {"name": "description"},
        {"property": "og:description"},
        {"name": "twitter:description"},
    ]:
        tag = soup.find("meta", attrs=sel)
        if tag and tag.get("content"):
            desc = tag.get("content", "").strip()
            break
    h1 = soup.find("h1")
    h1_text = h1.get_text(" ", strip=True) if h1 else ""
    return {"external_title": title or h1_text, "external_description": desc, "external_h1": h1_text}


def enrich_external(app_data: Dict[str, Any], cfg: RunConfig, client: ExternalClient) -> Dict[str, Any]:
    out: Dict[str, Any] = {}
    sources: List[str] = []
    app_id = app_data.get("appId") or app_data.get("app_id")
    url = app_link(app_data)

    if client.api.searchapi and app_id:
        searchapi = client.searchapi_product(str(app_id), cfg)
        if searchapi:
            sources.append("SearchAPI")
            out["searchapi_json_preview"] = json.dumps(searchapi, ensure_ascii=False)[:2000]
            product = searchapi.get("product") or searchapi.get("product_info") or {}
            if isinstance(product, dict):
                out.setdefault("external_title", product.get("title"))
                out.setdefault("external_description", product.get("description") or product.get("snippet") or product.get("summary"))

    if client.api.serpapi and app_id:
        serp = client.serpapi_product(str(app_id), cfg)
        if serp:
            sources.append("SerpAPI")
            out["serpapi_json_preview"] = json.dumps(serp, ensure_ascii=False)[:2000]
            product = serp.get("product_info") or serp.get("app") or {}
            if isinstance(product, dict):
                out.setdefault("external_title", product.get("title"))
                out.setdefault("external_description", product.get("description") or product.get("snippet"))

    if client.api.brave_search and app_id and (cfg.ultra or not client.api.serpapi):
        title = app_data.get("title") or app_id
        brave = client.brave_web_search(f'site:play.google.com/store/apps/details "{app_id}" "{title}"', cfg, count=5)
        if brave:
            sources.append("Brave Search")
            out["brave_search_json_preview"] = json.dumps(brave, ensure_ascii=False)[:2000]

    provider, text, meta = client.fetch_html(url, cfg)
    if text:
        sources.append(provider)
        meta_basic = extract_basic_meta(text)
        out.update({k: v for k, v in meta_basic.items() if v and not out.get(k)})
        out["external_markdown_preview"] = text[:4000]
        out["external_fetch_meta"] = json.dumps(meta, ensure_ascii=False)[:2000]

    dev_site = app_data.get("developerWebsite") or app_data.get("developer_website")
    if cfg.use_developer_site and dev_site:
        provider_dev, dev_text, dev_meta = client.fetch_html(str(dev_site), cfg)
        if dev_text:
            sources.append(f"DevSite:{provider_dev}")
            meta_dev = extract_basic_meta(dev_text)
            if meta_dev.get("external_description") and not out.get("developer_site_description"):
                out["developer_site_description"] = meta_dev.get("external_description")
            out["developer_site_preview"] = dev_text[:3000]
            out["developer_site_fetch_meta"] = json.dumps(dev_meta, ensure_ascii=False)[:1500]

    out["external_sources_used"] = list(dict.fromkeys(sources))
    return out
