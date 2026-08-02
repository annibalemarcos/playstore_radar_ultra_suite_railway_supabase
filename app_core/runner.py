"""Motor único usado tanto pelo terminal quanto pelo Flask."""
from __future__ import annotations

import time
import traceback
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional

from .categories import selecionar_categorias
from .config import ApiConfig, RunConfig
from .database import (
    create_run,
    delete_run,
    get_run,
    init_db,
    insert_apps,
    log,
    now_iso,
    update_run,
)
from .external_apis import ExternalClient, enrich_external
from .googleplay import GooglePlayClient, GooglePlayUnavailable
from .scoring import compute_scores, estimate_financials, passes_profile

ProgressCallback = Callable[[Dict[str, Any]], None]


@dataclass
class RunResult:
    run_id: int
    apps_scanned: int
    apps_kept: int
    errors: List[str]
    output_paths: Dict[str, str]


class RunCancelled(Exception):
    """Parada segura solicitada pelo dashboard."""


class RunDeleted(Exception):
    """Parada segura + exclusão solicitada pelo dashboard."""


def emit(callback: Optional[ProgressCallback], **payload: Any) -> None:
    if callback:
        callback(payload)


def merge_app_data(base: Dict[str, Any], details: Dict[str, Any]) -> Dict[str, Any]:
    merged = dict(base or {})
    for key, value in (details or {}).items():
        if value not in (None, "", [], {}):
            merged[key] = value
    return merged


def prepare_app(candidate: Dict[str, Any], categoria_codigo: str, categoria_nome: str, rank: int) -> Dict[str, Any]:
    app_data = dict(candidate)
    app_data["categoria"] = categoria_nome
    app_data["categoria_codigo"] = categoria_codigo
    app_data["rank"] = rank
    if "url" not in app_data and app_data.get("appId"):
        app_data["url"] = f"https://play.google.com/store/apps/details?id={app_data['appId']}"
    return app_data


def _run_status(cfg: RunConfig, run_id: int) -> str:
    run = get_run(cfg.db_path, run_id)
    return str((run or {}).get("status") or "")


def _control_checkpoint(cfg: RunConfig, run_id: int, callback: Optional[ProgressCallback] = None) -> None:
    """Obedece comandos do dashboard em pontos seguros.

    Não mata thread à força. Ele para entre categoria/app/review/chamada, que é o jeito
    menos propenso a corromper banco ou deixar request externa pendurada.
    """
    while True:
        status = _run_status(cfg, run_id)
        if not status:
            raise RunDeleted("Run removido do banco.")
        if status in {"cancel_requested", "restart_requested"}:
            raise RunCancelled("Coleta cancelada pelo usuário.")
        if status == "delete_requested":
            raise RunDeleted("Coleta cancelada e enviada para exclusão.")
        if status == "pause_requested":
            update_run(cfg.db_path, run_id, status="paused", last_message="Coleta pausada. Clique em continuar para retomar.")
            log(cfg.db_path, run_id, "⏸️ Coleta pausada pelo usuário", "warning")
            emit(callback, event="paused", run_id=run_id)
            status = "paused"
        if status == "paused":
            time.sleep(0.75)
            continue
        return


def _sleep_controlled(cfg: RunConfig, run_id: int, seconds: float, callback: Optional[ProgressCallback] = None) -> None:
    if seconds <= 0:
        return
    end = time.time() + seconds
    while time.time() < end:
        _control_checkpoint(cfg, run_id, callback)
        time.sleep(min(0.25, max(0, end - time.time())))


def run_scraper(
    cfg: RunConfig,
    api: Optional[ApiConfig] = None,
    run_id: Optional[int] = None,
    callback: Optional[ProgressCallback] = None,
) -> RunResult:
    """Executa uma coleta completa.

    Esta função é o coração do projeto. CLI e Flask chamam exatamente isso.
    """
    api = api or ApiConfig()
    cfg.apply_level_defaults(api)
    cfg.output_path.mkdir(parents=True, exist_ok=True)
    if not cfg.is_remote_database:
        cfg.database_path.parent.mkdir(parents=True, exist_ok=True)
    init_db(cfg.db_path)

    if run_id is None:
        run_id = create_run(cfg, status="running")
    else:
        update_run(cfg.db_path, run_id, status="running")

    update_run(cfg.db_path, run_id, started_at=now_iso(), output_dir=cfg.output_dir)
    log(cfg.db_path, run_id, f"Iniciando coleta: {cfg.level} / {cfg.profile} / {cfg.quantity} apps por categoria")
    emit(callback, event="start", run_id=run_id, cfg=cfg.to_dict())

    errors: List[str] = []
    scanned = 0
    kept_total = 0
    output_paths: Dict[str, str] = {}

    try:
        _control_checkpoint(cfg, run_id, callback)
        try:
            gp = GooglePlayClient()
        except GooglePlayUnavailable as exc:
            log(cfg.db_path, run_id, str(exc), "error")
            update_run(cfg.db_path, run_id, status="failed", finished_at=now_iso(), errors_count=1)
            raise

        external_client = ExternalClient(api)
        search_query = (cfg.search_query or "").strip()
        is_keyword_search = bool(search_query)

        if is_keyword_search:
            # Busca livre por nome/termo: ignora categorias e trata a busca como
            # uma "categoria" única, para reaproveitar todo o pipeline de scraping abaixo.
            categorias = [("BUSCA", f'Busca: "{search_query}"', search_query)]
            log(cfg.db_path, run_id, f'Busca livre por termo ativa: "{search_query}"', "info")
        else:
            categorias = selecionar_categorias(cfg.scope, cfg.category_codes, cfg.subcategory_codes)
            if cfg.category_codes and cfg.scope in {"APPS", "JOGOS"}:
                log(cfg.db_path, run_id, f"Filtro de categorias ativo: {cfg.category_codes}", "info")
            if cfg.subcategory_codes and cfg.scope in {"APPS", "JOGOS"}:
                log(cfg.db_path, run_id, f"Filtro de subcategorias ativo: {cfg.subcategory_codes}", "info")
            if cfg.max_categories:
                categorias = categorias[: cfg.max_categories]
        total_categories = len(categorias)
        update_run(cfg.db_path, run_id, categories_total=total_categories)
        if total_categories == 0:
            raise ValueError("Nenhuma categoria selecionada. Marque pelo menos uma categoria ou use 'Todas'.")

        for cat_index, (codigo, nome, termo) in enumerate(categorias, start=1):
            _control_checkpoint(cfg, run_id, callback)
            msg = f"[{cat_index}/{total_categories}] Buscando {nome}"
            log(cfg.db_path, run_id, msg)
            emit(callback, event="category_start", run_id=run_id, category=nome, index=cat_index, total=total_categories)
            try:
                if is_keyword_search:
                    candidatos = gp.buscar_por_termo(termo, cfg)
                else:
                    candidatos = gp.buscar_apps_categoria(codigo, nome, termo, cfg)
            except Exception as exc:  # noqa: BLE001
                err = f"{nome}: busca falhou: {exc}"
                errors.append(err)
                log(cfg.db_path, run_id, err, "error")
                update_run(cfg.db_path, run_id, categories_done=cat_index, errors_count=len(errors))
                continue

            _control_checkpoint(cfg, run_id, callback)
            if cfg.use_external_apis and api.openwebninja and api.openwebninja_endpoint:
                try:
                    ninja_candidates = external_client.openwebninja_play_search(termo, cfg)
                    if ninja_candidates:
                        before = len(candidatos)
                        candidatos = gp.dedup(candidatos + ninja_candidates)
                        log(cfg.db_path, run_id, f"{nome}: OpenWebNinja adicionou {len(candidatos) - before} candidatos únicos")
                except Exception as exc:  # noqa: BLE001
                    err = f"{nome}: OpenWebNinja falhou: {exc}"
                    errors.append(err)
                    log(cfg.db_path, run_id, err, "warning")

            if cfg.use_external_apis and api.brave_search:
                try:
                    brave_candidates = external_client.brave_play_search(termo, cfg)
                    if brave_candidates:
                        before = len(candidatos)
                        candidatos = gp.dedup(candidatos + brave_candidates)
                        log(cfg.db_path, run_id, f"{nome}: Brave Search adicionou {len(candidatos) - before} candidatos únicos")
                except Exception as exc:  # noqa: BLE001
                    err = f"{nome}: Brave Search falhou: {exc}"
                    errors.append(err)
                    log(cfg.db_path, run_id, err, "warning")

            if cfg.use_external_apis:
                discovery_calls = [
                    ("SearchAPI", api.searchapi, external_client.searchapi_play_search),
                    ("Scavio", api.scavio, external_client.scavio_play_search),
                    ("Exa", api.exa, external_client.exa_play_search),
                    ("Tavily", api.tavily, external_client.tavily_play_search),
                    ("You.com", api.youcom, external_client.you_play_search),
                    ("Jina AI", api.jina, external_client.jina_play_search),
                ]
                for provider_name, enabled, func in discovery_calls:
                    if not enabled:
                        continue
                    _control_checkpoint(cfg, run_id, callback)
                    try:
                        extra_candidates = func(termo, cfg)
                        if extra_candidates:
                            before = len(candidatos)
                            candidatos = gp.dedup(candidatos + extra_candidates)
                            added = len(candidatos) - before
                            if added > 0:
                                log(cfg.db_path, run_id, f"{nome}: {provider_name} adicionou {added} candidatos únicos")
                    except Exception as exc:  # noqa: BLE001
                        err = f"{nome}: {provider_name} falhou: {exc}"
                        errors.append(err)
                        log(cfg.db_path, run_id, err, "warning")

            if not candidatos:
                err = f"{nome}: nenhum app encontrado"
                errors.append(err)
                log(cfg.db_path, run_id, err, "warning")
                update_run(cfg.db_path, run_id, categories_done=cat_index, errors_count=len(errors))
                continue

            apps_to_insert: List[Dict[str, Any]] = []
            if is_keyword_search:
                # Busca por termo: raspa TODAS as informações de TODOS os apps encontrados.
                detail_target = len(candidatos)
                keep_target = len(candidatos)
            else:
                detail_target = len(candidatos) if cfg.detail_limit is None else min(len(candidatos), cfg.detail_limit)
                keep_target = cfg.quantity
            log(cfg.db_path, run_id, f"{nome}: {len(candidatos)} candidatos, detalhando até {detail_target}")

            for idx, candidate in enumerate(candidatos[:detail_target], start=1):
                _control_checkpoint(cfg, run_id, callback)
                app_id = candidate.get("appId") or candidate.get("id")
                if not app_id:
                    continue
                scanned += 1
                emit(
                    callback,
                    event="app_start",
                    run_id=run_id,
                    category=nome,
                    title=candidate.get("title") or app_id,
                    app_index=idx,
                    app_total=detail_target,
                    scanned=scanned,
                    kept=kept_total,
                )

                try:
                    base = prepare_app(candidate, codigo, nome, idx)
                    _control_checkpoint(cfg, run_id, callback)
                    details = gp.buscar_detalhes(str(app_id), cfg) if cfg.deep_enabled or cfg.financial_enabled or cfg.level == "SIMPLES" else {}
                    app_data = merge_app_data(base, details)
                    app_data.setdefault("categoria", nome)
                    app_data.setdefault("categoria_codigo", codigo)
                    app_data.setdefault("rank", idx)
                    app_data.setdefault("url", f"https://play.google.com/store/apps/details?id={app_id}")

                    _control_checkpoint(cfg, run_id, callback)
                    if cfg.reviews_per_app > 0:
                        app_data.update(gp.coletar_reviews(str(app_id), cfg))

                    scores = compute_scores(app_data)
                    app_data.update(scores)

                    if cfg.financial_enabled:
                        app_data.update(estimate_financials(app_data, cfg.exchange_rate_brl))

                    _control_checkpoint(cfg, run_id, callback)
                    if cfg.use_external_apis:
                        app_data.update(enrich_external(app_data, cfg, external_client))

                    if cfg.include_paid_apps is False and app_data.get("free") is False:
                        continue

                    if passes_profile(app_data, cfg.profile):
                        apps_to_insert.append(app_data)
                        kept_total += 1
                        emit(callback, event="app_kept", run_id=run_id, title=app_data.get("title"), kept=kept_total)
                    else:
                        emit(callback, event="app_skipped", run_id=run_id, title=app_data.get("title"), reason="profile_filter")

                    update_run(cfg.db_path, run_id, apps_scanned=scanned, apps_kept=kept_total)
                    if len(apps_to_insert) >= keep_target:
                        break
                    if cfg.delay:
                        _sleep_controlled(cfg, run_id, cfg.delay, callback)
                except (RunCancelled, RunDeleted):
                    raise
                except Exception as exc:  # noqa: BLE001
                    err = f"{nome}/{app_id}: {exc}"
                    errors.append(err)
                    log(cfg.db_path, run_id, err, "error")
                    emit(callback, event="app_error", run_id=run_id, app_id=app_id, error=str(exc))
                    if cfg.ultra:
                        log(cfg.db_path, run_id, traceback.format_exc()[-2000:], "debug")

            _control_checkpoint(cfg, run_id, callback)
            inserted = insert_apps(cfg.db_path, run_id, apps_to_insert)
            log(cfg.db_path, run_id, f"{nome}: {inserted} apps salvos no banco")
            update_run(
                cfg.db_path,
                run_id,
                categories_done=cat_index,
                apps_scanned=scanned,
                apps_kept=kept_total,
                errors_count=len(errors),
            )
            emit(callback, event="category_done", run_id=run_id, category=nome, inserted=inserted)

        _control_checkpoint(cfg, run_id, callback)
        # Exportações ficam no final para a versão web também baixar tudo.
        try:
            from .exports import export_run_all

            output_paths = export_run_all(cfg.db_path, run_id, Path(cfg.output_dir))
            update_run(
                cfg.db_path,
                run_id,
                html_path=output_paths.get("html"),
                json_path=output_paths.get("json"),
                csv_path=output_paths.get("csv"),
            )
            log(cfg.db_path, run_id, "Exports gerados: HTML, JSON e CSV")
        except Exception as exc:  # noqa: BLE001
            errors.append(f"Falha ao exportar: {exc}")
            log(cfg.db_path, run_id, f"Falha ao exportar: {exc}", "error")

        status = "finished" if not errors else "finished_with_warnings"
        update_run(
            cfg.db_path,
            run_id,
            status=status,
            finished_at=now_iso(),
            apps_scanned=scanned,
            apps_kept=kept_total,
            errors_count=len(errors),
        )
        log(cfg.db_path, run_id, f"Finalizado: {kept_total} apps salvos, {len(errors)} alertas/erros")
        emit(callback, event="finish", run_id=run_id, kept=kept_total, scanned=scanned, errors=errors, output_paths=output_paths)
        return RunResult(run_id=run_id, apps_scanned=scanned, apps_kept=kept_total, errors=errors, output_paths=output_paths)

    except RunDeleted as exc:
        try:
            log(cfg.db_path, run_id, f"🗑️ {exc}", "warning")
        finally:
            delete_run(cfg.db_path, run_id)
        emit(callback, event="deleted", run_id=run_id)
        return RunResult(run_id=run_id, apps_scanned=scanned, apps_kept=kept_total, errors=[str(exc)], output_paths={})
    except RunCancelled as exc:
        msg = str(exc) or "Coleta cancelada pelo usuário."
        errors.append(msg)
        log(cfg.db_path, run_id, f"⛔ {msg}", "warning")
        update_run(
            cfg.db_path,
            run_id,
            status="cancelled",
            finished_at=now_iso(),
            apps_scanned=scanned,
            apps_kept=kept_total,
            errors_count=len(errors),
            last_message=msg,
        )
        emit(callback, event="cancelled", run_id=run_id, kept=kept_total, scanned=scanned)
        return RunResult(run_id=run_id, apps_scanned=scanned, apps_kept=kept_total, errors=errors, output_paths={})
