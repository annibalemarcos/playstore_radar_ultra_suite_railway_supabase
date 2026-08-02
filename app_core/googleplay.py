"""Wrapper em volta de google-play-scraper com fallbacks."""
from __future__ import annotations

import time
from typing import Any, Dict, Iterable, List, Optional

from .config import RunConfig


class GooglePlayUnavailable(RuntimeError):
    pass


class GooglePlayClient:
    def __init__(self) -> None:
        try:
            from google_play_scraper import app as gp_app
            from google_play_scraper import reviews as gp_reviews
            from google_play_scraper import search as gp_search
            from google_play_scraper import Sort
        except ImportError as exc:  # pragma: no cover
            raise GooglePlayUnavailable(
                "Biblioteca google-play-scraper não encontrada. Rode: pip install -r requirements.txt"
            ) from exc

        self.gp_app = gp_app
        self.gp_reviews = gp_reviews
        self.gp_search = gp_search
        self.Sort = Sort
        try:  # versões diferentes da lib têm assinaturas diferentes
            from google_play_scraper import Category, Collection, collection as gp_collection
        except Exception:  # noqa: BLE001
            Category = None
            Collection = None
            gp_collection = None
        self.Category = Category
        self.Collection = Collection
        self.gp_collection = gp_collection

    @staticmethod
    def dedup(apps: Iterable[Dict[str, Any]]) -> List[Dict[str, Any]]:
        out: List[Dict[str, Any]] = []
        seen = set()
        for item in apps:
            app_id = item.get("appId") or item.get("id") or item.get("url")
            if not app_id:
                app_id = str(item)[:250]
            if app_id in seen:
                continue
            seen.add(app_id)
            out.append(item)
        return out

    def buscar_por_collection(self, categoria_codigo: str, quantidade: int, cfg: RunConfig) -> List[Dict[str, Any]]:
        if not self.gp_collection or not self.Collection or not self.Category:
            return []
        cat = getattr(self.Category, categoria_codigo, None)
        if not cat:
            return []
        collections = []
        for attr in ("TOP_FREE", "TOP_GROSSING", "TRENDING", "NEW_FREE", "TOP_PAID"):
            col = getattr(self.Collection, attr, None)
            if col:
                collections.append(col)
        if not collections:
            return []
        limit_collections = 1
        if cfg.profile in {"CRESCENDO", "OPORTUNIDADE"} or cfg.ultra:
            limit_collections = 4
        agregados: List[Dict[str, Any]] = []
        for col in collections[:limit_collections]:
            tentativas = [
                {"collection": col, "category": cat, "results": quantidade, "lang": cfg.lang, "country": cfg.country},
                {"collection": col, "category": cat, "num": quantidade, "lang": cfg.lang, "country": cfg.country},
                {"collection": col, "category": cat, "lang": cfg.lang, "country": cfg.country},
            ]
            for kwargs in tentativas:
                try:
                    res = self.gp_collection(**kwargs)
                    if res:
                        agregados.extend(res)
                        break
                except TypeError:
                    continue
                except Exception:
                    break
        return self.dedup(agregados)[:quantidade]

    def consultas_por_perfil(self, codigo: str, nome: str, termo: str, cfg: RunConfig) -> List[str]:
        base = [termo, nome, codigo.replace("_", " ").lower()]
        if cfg.profile == "PEQUENOS_INDIE":
            extras = [
                f"{termo} indie", f"{termo} solo developer", f"{termo} open source", f"{termo} simples",
                f"{termo} leve", f"{termo} minimalista", f"{nome} indie app", f"{termo} sem anúncios",
            ]
        elif cfg.profile == "CRESCENDO":
            extras = [
                f"{termo} novo", f"{termo} trending", f"{termo} popular novo", f"{termo} 2026",
                f"{nome} novos apps", f"{nome} app crescendo", f"{termo} recém lançado",
            ]
        elif cfg.profile == "OPORTUNIDADE":
            extras = [
                f"{termo} pro", f"{termo} premium", f"{termo} subscription", f"{termo} ads",
                f"{termo} small business", f"{termo} produtividade", f"{nome} oportunidade app",
            ]
        elif cfg.profile == "SEM_GIGANTES":
            extras = [f"{termo} alternativa", f"{termo} app leve", f"{termo} pequeno", f"{nome} alternatives"]
        else:
            extras = []
        if cfg.ultra:
            extras += [f"{termo} melhores", f"{termo} grátis", f"{termo} pago", f"{termo} Brasil"]
        return list(dict.fromkeys(extras + base))

    def buscar_apps_categoria(self, codigo: str, nome: str, termo: str, cfg: RunConfig) -> List[Dict[str, Any]]:
        multiplier = 2.8 if cfg.profile != "TODOS" else 1.35
        if cfg.level in {"FULL", "ULTRA_FULL"}:
            multiplier += 0.5
        quantidade_busca = max(cfg.quantity, int(cfg.quantity * multiplier))
        agregados = self.buscar_por_collection(codigo, quantidade_busca, cfg)
        consultas = self.consultas_por_perfil(codigo, nome, termo, cfg)
        for consulta in consultas:
            try:
                res = self.gp_search(consulta, lang=cfg.lang, country=cfg.country, n_hits=quantidade_busca)
                if res:
                    agregados.extend(res)
            except Exception:
                continue
            if len(self.dedup(agregados)) >= quantidade_busca:
                break
            time.sleep(0.08)
        return self.dedup(agregados)[:quantidade_busca]

    def buscar_por_termo(self, termo: str, cfg: RunConfig) -> List[Dict[str, Any]]:
        """Busca livre por nome/palavra-chave, sem passar pelas categorias.

        Usada pelo campo 'Nova busca' quando o usuário digita um termo: retorna
        os resultados do Google Play para aquele termo, para depois fazer o
        scraping completo (detalhes + reviews) de cada app encontrado.
        """
        termo = (termo or "").strip()
        if not termo:
            return []
        quantidade = max(int(cfg.quantity or 25), 1)
        agregados: List[Dict[str, Any]] = []
        try:
            res = self.gp_search(termo, lang=cfg.lang, country=cfg.country, n_hits=quantidade)
            if res:
                agregados.extend(res)
        except Exception:
            pass
        return self.dedup(agregados)[:quantidade]

    def buscar_detalhes(self, app_id: str, cfg: RunConfig, tentativas: int = 2) -> Dict[str, Any]:
        for tentativa in range(1, tentativas + 1):
            try:
                return self.gp_app(app_id, lang=cfg.lang, country=cfg.country) or {}
            except Exception as exc:  # noqa: BLE001
                if tentativa >= tentativas:
                    return {"_detail_error": str(exc)}
                time.sleep(0.6 * tentativa)
        return {}

    def coletar_reviews(self, app_id: str, cfg: RunConfig) -> Dict[str, Any]:
        from .scoring import extract_keywords

        if cfg.reviews_per_app <= 0:
            return {}
        try:
            result, _token = self.gp_reviews(
                app_id,
                lang=cfg.lang,
                country=cfg.country,
                sort=self.Sort.NEWEST,
                count=cfg.reviews_per_app,
                filter_score_with=None,
            )
        except Exception as exc:  # noqa: BLE001
            return {"_reviews_error": str(exc), "review_count_collected": 0}

        scores = [int(r.get("score") or 0) for r in result if r.get("score")]
        texts = [str(r.get("content") or "") for r in result if r.get("content")]
        dist = {str(i): scores.count(i) for i in range(1, 6)}
        pos = sum(1 for s in scores if s >= 4)
        neg = sum(1 for s in scores if s <= 2)
        total = len(scores) or 1
        samples = [
            {
                "score": r.get("score"),
                "at": str(r.get("at")) if r.get("at") else None,
                "thumbsUpCount": r.get("thumbsUpCount"),
                "content": str(r.get("content") or "")[:800],
            }
            for r in result[: min(12, len(result))]
        ]
        return {
            "review_count_collected": len(result),
            "review_score_avg_recent": round(sum(scores) / len(scores), 2) if scores else 0,
            "review_distribution_recent": dist,
            "review_positive_pct": round(pos * 100 / total, 1),
            "review_negative_pct": round(neg * 100 / total, 1),
            "review_keywords": extract_keywords("\n".join(texts), limit=16),
            "review_samples": samples,
        }
