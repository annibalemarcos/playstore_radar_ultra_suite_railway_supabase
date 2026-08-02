"""Exportação HTML/JSON/CSV do resultado salvo no SQLite.

O HTML exportado é pensado para leitura humana: tabela compacta, filtros rápidos
E modal por app. Cada linha abre uma ficha completa com descrição, reviews,
screenshots, financeiro, fontes externas e JSON bruto completo.
"""
from __future__ import annotations

import csv
import json
import zipfile
from datetime import datetime
from html import escape
from pathlib import Path
from typing import Any, Dict, List, Optional

from .database import get_run, list_apps, list_runs
from .scoring import compact_num, money

ALL_RUNS_BASENAME = "playstore_all_runs"

CSV_FIELDS = [
    "categoria", "rank", "title", "app_id", "developer", "developer_email", "developer_website", "genre",
    "score", "ratings", "reviews", "installs", "min_installs", "real_installs", "free", "price", "currency",
    "contains_ads", "offers_iap", "iap_price", "content_rating", "released", "updated", "version", "android_version",
    "summary", "url", "indie_score", "growth_score", "opportunity_score", "perfil_detectado",
    "estimated_mau", "revenue_monthly_usd_low", "revenue_monthly_usd_base", "revenue_monthly_usd_high",
    "profit_monthly_usd_base", "revenue_monthly_brl_base", "profit_monthly_brl_base", "financial_confidence",
    "review_count_collected", "review_score_avg_recent", "review_positive_pct", "review_negative_pct", "external_sources_used",
]


def h(value: Any) -> str:
    if value is None:
        return ""
    return escape(str(value), quote=True)


def json_script(value: Any) -> str:
    """JSON seguro para embutir dentro de <script type=application/json>."""
    text = json.dumps(value, ensure_ascii=False, default=str)
    return (
        text.replace("&", "\\u0026")
        .replace("<", "\\u003c")
        .replace(">", "\\u003e")
        .replace("\u2028", "\\u2028")
        .replace("\u2029", "\\u2029")
    )


def as_float(value: Any, default: float = 0.0) -> float:
    try:
        if value is None or value == "":
            return default
        return float(value)
    except (TypeError, ValueError):
        return default


def as_int(value: Any, default: int = 0) -> int:
    try:
        if value is None or value == "":
            return default
        return int(float(value))
    except (TypeError, ValueError):
        return default


def compact_text(value: Any, limit: int = 180) -> str:
    text = " ".join(str(value or "").replace("\r", " ").replace("\n", " ").split())
    if len(text) <= limit:
        return text
    return text[: max(0, limit - 1)].rstrip() + "…"


def load_apps(db_path: str | Path, run_id: int) -> List[Dict[str, Any]]:
    # Export visual abre por oportunidade. O usuário ainda pode reorganizar no HTML.
    return list_apps(db_path, run_id=run_id, order="opportunity_score", limit=20_000)


def load_all_apps(db_path: str | Path) -> List[Dict[str, Any]]:
    # Mesma lógica de load_apps, mas sem filtrar por run_id: junta os apps de todas as buscas.
    return list_apps(db_path, run_id=None, order="opportunity_score", limit=200_000)


def export_run_json(db_path: str | Path, run_id: int, output_dir: Path) -> str:
    output_dir.mkdir(parents=True, exist_ok=True)
    run = get_run(db_path, run_id) or {}
    apps = load_apps(db_path, run_id)
    path = output_dir / f"playstore_run_{run_id}.json"
    with path.open("w", encoding="utf-8") as f:
        json.dump({"run": run, "apps": apps}, f, ensure_ascii=False, indent=2, default=str)
    return str(path)


def export_run_csv(db_path: str | Path, run_id: int, output_dir: Path) -> str:
    output_dir.mkdir(parents=True, exist_ok=True)
    apps = load_apps(db_path, run_id)
    path = output_dir / f"playstore_run_{run_id}.csv"
    with path.open("w", encoding="utf-8-sig", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=CSV_FIELDS, extrasaction="ignore")
        writer.writeheader()
        for app in apps:
            writer.writerow(app)
    return str(path)


def export_all_json(db_path: str | Path, output_dir: Path) -> str:
    """Exporta todas as buscas (runs) e todos os apps salvos num único JSON."""
    output_dir.mkdir(parents=True, exist_ok=True)
    runs = list_runs(db_path, 10_000)
    apps = load_all_apps(db_path)
    path = output_dir / f"{ALL_RUNS_BASENAME}.json"
    with path.open("w", encoding="utf-8") as f:
        json.dump(
            {
                "exported_at": datetime.now().isoformat(timespec="seconds"),
                "total_runs": len(runs),
                "total_apps": len(apps),
                "runs": runs,
                "apps": apps,
            },
            f,
            ensure_ascii=False,
            indent=2,
            default=str,
        )
    return str(path)


def export_all_csv(db_path: str | Path, output_dir: Path) -> str:
    """Exporta os apps de todas as buscas num único CSV, com a run de origem em cada linha."""
    output_dir.mkdir(parents=True, exist_ok=True)
    apps = load_all_apps(db_path)
    fields = ["run_id"] + CSV_FIELDS
    path = output_dir / f"{ALL_RUNS_BASENAME}.csv"
    with path.open("w", encoding="utf-8-sig", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=fields, extrasaction="ignore")
        writer.writeheader()
        for app in apps:
            writer.writerow(app)
    return str(path)


def _badges(app: Dict[str, Any]) -> str:
    badges: List[str] = []
    if app.get("perfil_detectado"):
        badges.append(f'<span class="badge-soft primary">{h(app.get("perfil_detectado"))}</span>')
    if app.get("contains_ads"):
        badges.append('<span class="badge-soft warn">ads</span>')
    if app.get("offers_iap"):
        badges.append('<span class="badge-soft good">IAP</span>')
    if app.get("financial_confidence"):
        badges.append(f'<span class="badge-soft light">conf. {h(app.get("financial_confidence"))}</span>')
    return "".join(badges)


def app_table_row(app: Dict[str, Any], index: int) -> str:
    icon = app.get("icon") or ""
    img = f'<img src="{h(icon)}" class="app-icon" loading="lazy" alt="ícone de {h(app.get("title") or "app")}">' if icon else '<div class="app-icon placeholder">?</div>'
    installs_value = app.get("real_installs") or app.get("min_installs") or app.get("installs") or 0
    summary = compact_text(app.get("summary") or app.get("description") or "", 210)
    external_sources = app.get("external_sources_used") or ""
    if isinstance(external_sources, list):
        sources_text = ", ".join(str(s) for s in external_sources)
    else:
        sources_text = str(external_sources or "")
    score_sum = as_int(app.get("opportunity_score")) + as_int(app.get("growth_score")) + as_int(app.get("indie_score"))
    url = app.get("url") or "#"
    return f"""
      <tr class="app-row" role="button" tabindex="0" data-app-index="{index - 1}"
          data-title="{h(app.get('title'))}"
          data-dev="{h(app.get('developer'))}"
          data-cat="{h(app.get('categoria'))}"
          data-profile="{h(app.get('perfil_detectado'))}"
          data-score="{as_float(app.get('score'))}"
          data-installs="{as_int(installs_value)}"
          data-opp="{as_int(app.get('opportunity_score'))}"
          data-grow="{as_int(app.get('growth_score'))}"
          data-indie="{as_int(app.get('indie_score'))}"
          data-revenue="{as_float(app.get('revenue_monthly_usd_base'))}"
          data-scores="{score_sum}"
          data-date="{h(app.get('created_at') or app.get('run_created_at') or '')}">
        <td class="rank-cell">#{h(app.get('rank') or index)}</td>
        <td class="app-cell">
          <div class="app-inline">
            {img}
            <div class="app-copy">
              <button type="button" class="app-title as-button" data-open-app="{index - 1}">{h(app.get('title') or 'Sem título')}</button>
              <span class="app-dev">{h(app.get('developer') or 'Dev não informado')}</span>
              <span class="app-summary">{h(summary)}</span>
              <span class="badges-line">{_badges(app)}</span>
              <a class="external-link" href="{h(url)}" target="_blank" rel="noopener">abrir na Play Store</a>
            </div>
          </div>
        </td>
        <td class="meta-cell"><b>{h(app.get('categoria') or app.get('genre') or '—')}</b><span>{h(app.get('perfil_detectado') or '—')}</span></td>
        <td class="num-cell"><b>{h(app.get('score') or 'N/A')}</b><span>{compact_num(app.get('ratings') or app.get('reviews') or 0)} aval.</span></td>
        <td class="num-cell"><b>{compact_num(installs_value)}</b><span>{h(app.get('installs') or '')}</span></td>
        <td class="scores-cell">
          <span>opp <b>{h(app.get('opportunity_score') or 0)}</b></span>
          <span>grow <b>{h(app.get('growth_score') or 0)}</b></span>
          <span>indie <b>{h(app.get('indie_score') or 0)}</b></span>
        </td>
        <td class="money-cell"><b>{money(app.get('revenue_monthly_usd_base'))}</b><span>lucro {money(app.get('profit_monthly_usd_base'))}</span></td>
        <td class="date-cell"><b>{h(app.get('created_at') or app.get('run_created_at') or '—')}</b><span>{h(sources_text[:90])}</span></td>
      </tr>
    """


def _render_report_html(path: Path, page_title: str, kicker: str, subtitle: str, apps: List[Dict[str, Any]]) -> str:
    """Monta o relatório HTML (tabela + modal por app). Usado tanto pela exportação de
    uma única run quanto pela exportação combinada de todas as runs."""
    total_apps = len(apps)
    categories = sorted({a.get("categoria") for a in apps if a.get("categoria")})
    profiles = sorted({a.get("perfil_detectado") for a in apps if a.get("perfil_detectado")})
    revenue = sum(as_float(a.get("revenue_monthly_usd_base")) for a in apps)
    avg_score = sum(as_float(a.get("score")) for a in apps) / total_apps if total_apps else 0
    rows = "\n".join(app_table_row(a, i + 1) for i, a in enumerate(apps))
    category_options = "\n".join(f'<option value="{h(c)}">{h(c)}</option>' for c in categories)
    profile_options = "\n".join(f'<option value="{h(p)}">{h(p)}</option>' for p in profiles)
    apps_json = json_script(apps)
    html = f"""<!doctype html>
<html lang="pt-BR">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>{h(page_title)}</title>
  <link href="https://cdn.jsdelivr.net/npm/bootstrap@5.3.3/dist/css/bootstrap.min.css" rel="stylesheet">
  <style>
    :root {{ --bg:#f5f7fb; --card:#ffffff; --ink:#13233b; --muted:#667085; --line:#dfe6f2; --brand:#667eea; --brand2:#7c5cff; --good:#067647; --warn:#b54708; --danger:#b42318; --soft:#f8fafc; }}
    * {{ box-sizing:border-box; }}
    body {{ background: radial-gradient(circle at 0 0, #eef2ff, transparent 34%), var(--bg); color:var(--ink); font-family: Inter, ui-sans-serif, system-ui, -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif; }}
    .shell {{ max-width: 1520px; margin: 28px auto; padding: 0 18px; }}
    .hero {{ background: linear-gradient(135deg, rgba(102,126,234,.16), rgba(20,184,166,.11)); border:1px solid var(--line); border-radius:30px; padding:28px; box-shadow:0 18px 50px rgba(31,41,55,.07); }}
    .hero h1 {{ font-weight:950; letter-spacing:-.055em; margin:0; }}
    .hero .sub {{ color:var(--muted); margin-top:.35rem; }}
    .stat-grid {{ display:grid; grid-template-columns:repeat(4,minmax(140px,1fr)); gap:10px; }}
    .stat {{ background:rgba(255,255,255,.82); border:1px solid var(--line); border-radius:20px; padding:14px 16px; }}
    .stat b {{ display:block; font-size:1.36rem; letter-spacing:-.03em; }} .stat span {{ color:var(--muted); font-size:.82rem; }}
    .toolbar {{ background:rgba(255,255,255,.94); border:1px solid var(--line); border-radius:24px; padding:16px; margin:18px 0; position:sticky; top:12px; z-index:10; box-shadow:0 14px 34px rgba(31,41,55,.06); backdrop-filter: blur(10px); }}
    .sort-pills {{ display:flex; flex-wrap:wrap; gap:8px; }}
    .sort-pills button {{ border:1px solid var(--line); background:#fff; border-radius:999px; padding:7px 12px; font-weight:800; font-size:.82rem; }}
    .sort-pills button.active {{ background:linear-gradient(135deg,var(--brand),var(--brand2)); color:#fff; border-color:transparent; }}
    .table-card {{ background:var(--card); border:1px solid var(--line); border-radius:26px; overflow:hidden; box-shadow:0 16px 42px rgba(31,41,55,.065); }}
    .table-wrap {{ overflow:auto; max-height: calc(100vh - 260px); }}
    table {{ min-width:1280px; margin:0!important; }}
    thead th {{ position:sticky; top:0; z-index:3; background:#f8fafc!important; color:#344054; font-size:.76rem; text-transform:uppercase; letter-spacing:.08em; border-bottom:1px solid var(--line)!important; }}
    tbody td {{ vertical-align:middle; border-color:var(--line)!important; }}
    .app-row {{ cursor:pointer; }}
    .app-row:hover td {{ background:#fbfcff; }}
    .app-row:focus {{ outline:3px solid rgba(102,126,234,.25); outline-offset:-3px; }}
    .rank-cell {{ width:70px; color:var(--muted); font-weight:800; }}
    .app-inline {{ display:flex; gap:12px; align-items:flex-start; min-width:430px; }}
    .app-icon {{ width:58px; height:58px; border-radius:16px; object-fit:cover; box-shadow:0 7px 18px rgba(31,41,55,.12); flex:0 0 auto; }}
    .placeholder {{ display:grid; place-items:center; background:#eef2ff; color:var(--brand); font-weight:900; }}
    .app-copy {{ min-width:0; }}
    .app-title {{ color:var(--ink); text-decoration:none; font-weight:900; display:block; line-height:1.15; text-align:left; }}
    .app-title:hover {{ color:var(--brand); }}
    .as-button {{ border:0; background:transparent; padding:0; margin:0; cursor:pointer; }}
    .external-link {{ display:inline-flex; margin-top:6px; color:var(--brand); text-decoration:none; font-weight:800; font-size:.78rem; }}
    .external-link:hover {{ text-decoration:underline; }}
    .app-dev,.app-summary,.meta-cell span,.num-cell span,.money-cell span,.date-cell span {{ display:block; color:var(--muted); font-size:.82rem; }}
    .app-summary {{ margin-top:5px; max-width:600px; }}
    .badges-line {{ display:flex; flex-wrap:wrap; gap:5px; margin-top:6px; }}
    .badge-soft {{ display:inline-flex; border-radius:999px; padding:3px 8px; font-size:.72rem; font-weight:850; border:1px solid transparent; }}
    .badge-soft.primary {{ background:#eef2ff; color:#3538cd; }} .badge-soft.warn {{ background:#fff6e6; color:var(--warn); }} .badge-soft.good {{ background:#ecfdf3; color:var(--good); }} .badge-soft.light {{ background:#f8fafc; color:#344054; border-color:var(--line); }}
    .num-cell,.money-cell {{ white-space:nowrap; }} .num-cell b,.money-cell b {{ font-size:.98rem; }}
    .scores-cell {{ min-width:160px; }} .scores-cell span {{ display:inline-flex; margin:2px; border:1px solid var(--line); border-radius:999px; padding:3px 7px; background:#f8fafc; font-size:.78rem; }}
    .date-cell {{ min-width:210px; max-width:260px; }}
    .meta-cell {{ min-width:150px; }}
    .hidden {{ display:none!important; }}
    .note {{ color:var(--muted); font-size:.88rem; }}
    .modal-backdrop-custom {{ position:fixed; inset:0; z-index:1000; background:rgba(15,23,42,.58); display:none; padding:24px; overflow:auto; }}
    .modal-backdrop-custom.open {{ display:block; }}
    .app-modal {{ max-width:1180px; margin:22px auto; background:#fff; border:1px solid var(--line); border-radius:30px; box-shadow:0 28px 90px rgba(2,8,23,.35); overflow:hidden; }}
    .modal-hero {{ background:linear-gradient(135deg, rgba(102,126,234,.16), rgba(20,184,166,.11)); padding:20px 22px; display:flex; gap:16px; align-items:flex-start; border-bottom:1px solid var(--line); }}
    .modal-icon {{ width:76px; height:76px; border-radius:22px; object-fit:cover; box-shadow:0 14px 30px rgba(31,41,55,.16); flex:0 0 auto; }}
    .modal-title-wrap {{ flex:1; min-width:0; }}
    .modal-title-wrap h2 {{ font-weight:950; letter-spacing:-.04em; margin:0; line-height:1.04; }}
    .modal-sub {{ color:var(--muted); margin-top:4px; }}
    .modal-close {{ border:1px solid var(--line); background:#fff; width:38px; height:38px; border-radius:999px; font-size:22px; line-height:1; font-weight:900; }}
    .modal-body-custom {{ padding:18px 22px 22px; }}
    .metric-grid {{ display:grid; grid-template-columns:repeat(6,minmax(116px,1fr)); gap:10px; margin-bottom:14px; }}
    .metric {{ border:1px solid var(--line); background:#fbfcff; border-radius:18px; padding:11px 12px; }}
    .metric b {{ display:block; font-size:1.05rem; letter-spacing:-.02em; }}
    .metric span {{ color:var(--muted); font-size:.76rem; }}
    .modal-tabs {{ display:flex; flex-wrap:wrap; gap:8px; border-bottom:1px solid var(--line); padding-bottom:10px; margin-bottom:14px; }}
    .modal-tabs button {{ border:1px solid var(--line); background:#fff; border-radius:999px; padding:8px 12px; font-weight:900; font-size:.82rem; }}
    .modal-tabs button.active {{ background:linear-gradient(135deg,var(--brand),var(--brand2)); color:#fff; border-color:transparent; }}
    .tab-panel {{ display:none; }} .tab-panel.active {{ display:block; }}
    .section-title {{ font-weight:950; letter-spacing:-.02em; margin:2px 0 10px; }}
    .kv-grid {{ display:grid; grid-template-columns:repeat(2,minmax(240px,1fr)); gap:8px 14px; }}
    .kv {{ border-bottom:1px dashed var(--line); padding:8px 0; }}
    .kv span {{ display:block; color:var(--muted); font-size:.74rem; text-transform:uppercase; letter-spacing:.08em; font-weight:900; }}
    .kv b,.kv a {{ color:var(--ink); overflow-wrap:anywhere; font-weight:780; text-decoration:none; }}
    .kv a:hover {{ color:var(--brand); text-decoration:underline; }}
    .text-box {{ background:#fbfcff; border:1px solid var(--line); border-radius:18px; padding:14px; max-height:360px; overflow:auto; white-space:pre-wrap; line-height:1.55; }}
    .review-card {{ border:1px solid var(--line); border-radius:16px; padding:12px; background:#fff; margin-bottom:8px; }}
    .review-card header {{ display:flex; justify-content:space-between; gap:12px; color:var(--muted); font-size:.8rem; font-weight:800; margin-bottom:6px; }}
    .chip-list {{ display:flex; flex-wrap:wrap; gap:6px; margin:.35rem 0 1rem; }}
    .chip {{ border:1px solid var(--line); background:#f8fafc; border-radius:999px; padding:4px 9px; font-size:.78rem; font-weight:800; color:#344054; }}
    .shot-grid {{ display:grid; grid-template-columns:repeat(auto-fill,minmax(150px,1fr)); gap:10px; }}
    .shot-grid img {{ width:100%; border-radius:16px; border:1px solid var(--line); background:#f8fafc; }}
    .raw-tools {{ display:flex; justify-content:space-between; gap:10px; align-items:center; margin-bottom:8px; }}
    .copy-json {{ border:1px solid var(--line); background:#fff; border-radius:999px; padding:7px 12px; font-weight:900; }}
    .raw-json {{ background:#0f172a; color:#e5e7eb; border-radius:18px; padding:14px; max-height:520px; overflow:auto; font-family:ui-monospace, SFMono-Regular, Menlo, Consolas, monospace; font-size:.78rem; line-height:1.45; }}
    .empty {{ color:var(--muted); padding:14px; border:1px dashed var(--line); border-radius:16px; background:#fbfcff; }}
    @media(max-width:900px) {{ .stat-grid {{ grid-template-columns:1fr 1fr; }} .toolbar {{ position:static; }} .shell {{ padding:0 10px; }} .metric-grid {{ grid-template-columns:1fr 1fr; }} .kv-grid {{ grid-template-columns:1fr; }} .modal-hero {{ flex-wrap:wrap; }} }}
    @media print {{ .toolbar,.modal-backdrop-custom {{ display:none!important; }} .table-wrap {{ max-height:none; overflow:visible; }} thead th {{ position:static; }} body {{ background:#fff; }} }}
  </style>
</head>
<body>
<div class="shell">
  <section class="hero">
    <div class="d-flex flex-wrap justify-content-between gap-4 align-items-end">
      <div>
        <div class="text-muted fw-bold small text-uppercase">{h(kicker)}</div>
        <h1>PlayStore Radar Ultra</h1>
        <p class="sub mb-0">{h(subtitle)}</p>
      </div>
      <div class="stat-grid">
        <div class="stat"><b>{total_apps}</b><span>apps salvos</span></div>
        <div class="stat"><b>{len(categories)}</b><span>categorias</span></div>
        <div class="stat"><b>{avg_score:.2f}</b><span>nota média</span></div>
        <div class="stat"><b>{money(revenue)}</b><span>receita base/mês</span></div>
      </div>
    </div>
    <p class="note mt-3 mb-0">Clique em qualquer app da tabela para abrir um modal com todas as informações coletadas: ficha, financeiro, descrição, reviews, screenshots, fontes externas e JSON bruto completo.</p>
  </section>

  <section class="toolbar">
    <div class="row g-2 align-items-end">
      <div class="col-xl-4 col-md-6"><label class="form-label small fw-bold">Busca</label><input id="q" class="form-control rounded-4" placeholder="Buscar app, dev, categoria..."></div>
      <div class="col-xl-2 col-md-3"><label class="form-label small fw-bold">Categoria</label><select id="cat" class="form-select rounded-4"><option value="">Todas</option>{category_options}</select></div>
      <div class="col-xl-2 col-md-3"><label class="form-label small fw-bold">Perfil</label><select id="profile" class="form-select rounded-4"><option value="">Todos</option>{profile_options}</select></div>
      <div class="col-xl-2 col-md-3"><label class="form-label small fw-bold">Nota mín.</label><input id="minScore" type="number" step="0.1" min="0" max="5" class="form-control rounded-4" placeholder="0"></div>
      <div class="col-xl-2 col-md-3"><label class="form-label small fw-bold">Visíveis</label><div class="form-control rounded-4 bg-white"><b id="visibleCount">{total_apps}</b> / {total_apps}</div></div>
      <div class="col-12 mt-2">
        <div class="sort-pills" aria-label="Ordenação rápida">
          <button type="button" data-sort="date" data-dir="desc">Pesquisa novas</button>
          <button type="button" data-sort="date" data-dir="asc">Pesquisa antigas</button>
          <button type="button" data-sort="score" data-dir="desc">Nota maior</button>
          <button type="button" data-sort="installs" data-dir="desc">Installs maior</button>
          <button type="button" data-sort="scores" data-dir="desc">Scores maior</button>
          <button type="button" data-sort="revenue" data-dir="desc">Receita maior</button>
        </div>
      </div>
    </div>
  </section>

  <section class="table-card">
    <div class="table-wrap">
      <table class="table table-hover align-middle" id="appsTable">
        <thead>
          <tr>
            <th>#</th>
            <th>App</th>
            <th>Categoria / Perfil</th>
            <th>Nota</th>
            <th>Installs</th>
            <th>Scores</th>
            <th>Receita/mês</th>
            <th>Pesquisa / Fontes</th>
          </tr>
        </thead>
        <tbody>{rows}</tbody>
      </table>
    </div>
  </section>
</div>

<div class="modal-backdrop-custom" id="appModal" aria-hidden="true">
  <div class="app-modal" role="dialog" aria-modal="true" aria-labelledby="modalTitle">
    <div class="modal-hero">
      <img id="modalIcon" class="modal-icon" alt="Ícone do app">
      <div class="modal-title-wrap">
        <div class="text-muted fw-bold small text-uppercase" id="modalCategory"></div>
        <h2 id="modalTitle">App</h2>
        <div class="modal-sub" id="modalDev"></div>
        <div class="badges-line" id="modalBadges"></div>
      </div>
      <button class="modal-close" id="modalClose" type="button" aria-label="Fechar">×</button>
    </div>
    <div class="modal-body-custom">
      <div class="metric-grid" id="modalMetrics"></div>
      <div class="modal-tabs" id="modalTabs">
        <button type="button" class="active" data-tab="overview">Resumo</button>
        <button type="button" data-tab="description">Descrição</button>
        <button type="button" data-tab="reviews">Reviews</button>
        <button type="button" data-tab="media">Mídia</button>
        <button type="button" data-tab="technical">Técnico / JSON</button>
      </div>
      <section class="tab-panel active" data-panel="overview"><div id="overviewPanel"></div></section>
      <section class="tab-panel" data-panel="description"><div id="descriptionPanel"></div></section>
      <section class="tab-panel" data-panel="reviews"><div id="reviewsPanel"></div></section>
      <section class="tab-panel" data-panel="media"><div id="mediaPanel"></div></section>
      <section class="tab-panel" data-panel="technical"><div id="technicalPanel"></div></section>
    </div>
  </div>
</div>
<script type="application/json" id="appsData">{apps_json}</script>
<script>
const q = document.querySelector('#q'), cat = document.querySelector('#cat'), profile = document.querySelector('#profile'), minScore = document.querySelector('#minScore'), visibleCount = document.querySelector('#visibleCount');
const tbody = document.querySelector('#appsTable tbody');
const appsData = JSON.parse(document.querySelector('#appsData').textContent || '[]');
let currentAppJson = null;
function norm(s) {{ return (s||'').toString().toLowerCase(); }}
function rowOk(row) {{
  const qq = norm(q.value); const cc = cat.value; const pp = profile.value; const ms = parseFloat(minScore.value||'0');
  const text = norm(row.dataset.title + ' ' + row.dataset.dev + ' ' + row.dataset.cat);
  return (!qq || text.includes(qq)) && (!cc || row.dataset.cat === cc) && (!pp || row.dataset.profile === pp) && (!ms || parseFloat(row.dataset.score||'0') >= ms);
}}
function filt() {{
  let visible = 0;
  document.querySelectorAll('.app-row').forEach(row => {{ const ok = rowOk(row); row.classList.toggle('hidden', !ok); if(ok) visible++; }});
  visibleCount.textContent = visible;
}}
function sortRows(key, dir='desc') {{
  const rows = [...document.querySelectorAll('.app-row')];
  const numeric = ['score','installs','opp','grow','indie','revenue','scores'];
  rows.sort((a,b) => {{
    let av, bv;
    if(key === 'date') {{ av = a.dataset.date || ''; bv = b.dataset.date || ''; }}
    else {{ av = parseFloat(a.dataset[key] || '0'); bv = parseFloat(b.dataset[key] || '0'); }}
    if(numeric.includes(key)) return dir === 'asc' ? av - bv : bv - av;
    return dir === 'asc' ? String(av).localeCompare(String(bv)) : String(bv).localeCompare(String(av));
  }});
  rows.forEach(row => tbody.appendChild(row));
  document.querySelectorAll('.sort-pills button').forEach(b => b.classList.remove('active'));
  const active = document.querySelector(`.sort-pills button[data-sort="${{key}}"][data-dir="${{dir}}"]`);
  if(active) active.classList.add('active');
  filt();
}}
function esc(value) {{
  if(value === null || value === undefined || value === '') return '';
  return String(value).replace(/[&<>"']/g, ch => ({{'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#039;'}}[ch]));
}}
function parseMaybeJson(value) {{
  if(!value) return value;
  if(typeof value === 'object') return value;
  if(typeof value !== 'string') return value;
  const s = value.trim();
  if(!s || !['{{','['].includes(s[0])) return value;
  try {{ return JSON.parse(s); }} catch(e) {{ return value; }}
}}
function listFromJson(value) {{
  const parsed = parseMaybeJson(value);
  if(Array.isArray(parsed)) return parsed;
  if(parsed && typeof parsed === 'object') return Object.values(parsed);
  if(typeof parsed === 'string' && parsed.includes(',')) return parsed.split(',').map(x => x.trim()).filter(Boolean);
  return parsed ? [parsed] : [];
}}
function cleanText(value) {{
  const parsed = parseMaybeJson(value);
  if(typeof parsed !== 'string') return parsed ? JSON.stringify(parsed, null, 2) : '';
  return parsed.replace(/<br\\s*\\/?>/gi, '\\n').replace(/<[^>]+>/g, '').replace(/\\r\\n/g, '\\n').replace(/\\n/g, '\\n').trim();
}}
function compact(value, empty='—') {{ return (value === null || value === undefined || value === '') ? empty : value; }}
function fmtNum(value) {{
  const n = Number(value || 0);
  if(!Number.isFinite(n)) return esc(value || '0');
  return n.toLocaleString('pt-BR');
}}
function fmtMoney(value) {{
  const n = Number(value || 0);
  if(!Number.isFinite(n)) return 'US$ 0';
  return 'US$ ' + n.toLocaleString('pt-BR', {{maximumFractionDigits:0}});
}}
function yesNo(value) {{
  if(value === true || value === 1 || value === '1' || String(value).toLowerCase() === 'true') return 'sim';
  if(value === false || value === 0 || value === '0' || String(value).toLowerCase() === 'false') return 'não';
  return compact(value);
}}
function linkify(label, value) {{
  if(!value) return '';
  const v = String(value);
  if(v.startsWith('http://') || v.startsWith('https://')) return `<a href="${{esc(v)}}" target="_blank" rel="noopener">${{esc(v)}}</a>`;
  if(label.toLowerCase().includes('email') && v.includes('@')) return `<a href="mailto:${{esc(v)}}">${{esc(v)}}</a>`;
  return `<b>${{esc(v)}}</b>`;
}}
function kv(label, value) {{
  if(value === null || value === undefined || value === '') return '';
  return `<div class="kv"><span>${{esc(label)}}</span>${{linkify(label, value)}}</div>`;
}}
function metric(label, value) {{ return `<div class="metric"><b>${{esc(value)}}</b><span>${{esc(label)}}</span></div>`; }}
function makeBadges(app) {{
  const parts = [];
  if(app.perfil_detectado) parts.push(`<span class="badge-soft primary">${{esc(app.perfil_detectado)}}</span>`);
  if(yesNo(app.contains_ads) === 'sim') parts.push('<span class="badge-soft warn">ads</span>');
  if(yesNo(app.offers_iap) === 'sim') parts.push('<span class="badge-soft good">IAP</span>');
  if(app.financial_confidence) parts.push(`<span class="badge-soft light">conf. ${{esc(app.financial_confidence)}}</span>`);
  if(app.external_sources_used) parts.push(`<span class="badge-soft light">${{esc(app.external_sources_used)}}</span>`);
  return parts.join('');
}}
function rawComplete(app) {{
  const raw = parseMaybeJson(app.raw_json);
  if(raw && typeof raw === 'object' && !Array.isArray(raw)) {{
    return {{...raw, _database_record: app}};
  }}
  return app;
}}
function openAppModal(index) {{
  const app = appsData[index];
  if(!app) return;
  const raw = rawComplete(app);
  currentAppJson = JSON.stringify(raw, null, 2);
  const modal = document.querySelector('#appModal');
  document.querySelector('#modalTitle').textContent = app.title || 'Sem título';
  document.querySelector('#modalDev').innerHTML = `${{esc(app.developer || 'Dev não informado')}}${{app.url ? ` · <a href="${{esc(app.url)}}" target="_blank" rel="noopener">abrir na Play Store</a>` : ''}}`;
  document.querySelector('#modalCategory').textContent = `${{app.categoria || app.genre || 'sem categoria'}} · ${{app.perfil_detectado || 'sem perfil'}}`;
  document.querySelector('#modalBadges').innerHTML = makeBadges(app);
  const icon = document.querySelector('#modalIcon');
  icon.src = app.icon || '';
  icon.style.display = app.icon ? '' : 'none';
  document.querySelector('#modalMetrics').innerHTML = [
    metric('nota', compact(app.score, 'N/A')),
    metric('instalações', fmtNum(app.real_installs || app.min_installs || 0)),
    metric('oportunidade', compact(app.opportunity_score, 0)),
    metric('crescimento', compact(app.growth_score, 0)),
    metric('indie', compact(app.indie_score, 0)),
    metric('receita/mês', fmtMoney(app.revenue_monthly_usd_base))
  ].join('');
  renderOverview(app, raw);
  renderDescription(app, raw);
  renderReviews(app, raw);
  renderMedia(app, raw);
  renderTechnical(app, raw);
  setTab('overview');
  modal.classList.add('open');
  modal.setAttribute('aria-hidden', 'false');
  document.body.style.overflow = 'hidden';
}}
function renderOverview(app, raw) {{
  const aiBrief = raw.ai_opportunity_brief || app.ai_opportunity_brief;
  const fields = [
    ['App ID', app.app_id || raw.appId], ['Categoria', app.categoria || app.genre], ['Categoria código', app.categoria_codigo || app.genre_id], ['Perfil', app.perfil_detectado],
    ['Desenvolvedor', app.developer], ['Email do dev', app.developer_email || raw.developerEmail], ['Site do dev', app.developer_website || raw.developerWebsite], ['Privacidade', app.privacy_policy || raw.privacyPolicy],
    ['Classificação', app.content_rating || raw.contentRating], ['Preço', app.price], ['Moeda', app.currency], ['Grátis', yesNo(app.free)], ['Tem anúncios', yesNo(app.contains_ads || app.ad_supported)], ['Compras no app', yesNo(app.offers_iap)], ['Preço IAP', app.iap_price || raw.inAppProductPrice],
    ['Instalações texto', app.installs], ['Instalações mín.', app.min_installs], ['Instalações reais', app.real_installs], ['Avaliações', app.ratings || app.reviews], ['Reviews coletadas', app.review_count_collected],
    ['MAU estimado', app.estimated_mau], ['Lançado em', app.released], ['Atualizado em', app.updated], ['Versão', app.version], ['Android', app.android_version], ['Coletado em', app.created_at], ['Run', '#' + (app.run_id || '')], ['Fontes externas', app.external_sources_used]
  ];
  const finance = [
    ['Receita baixa', fmtMoney(app.revenue_monthly_usd_low)], ['Receita base', fmtMoney(app.revenue_monthly_usd_base)], ['Receita alta', fmtMoney(app.revenue_monthly_usd_high)],
    ['Lucro base USD', fmtMoney(app.profit_monthly_usd_base)], ['Receita base BRL', 'R$ ' + fmtNum(app.revenue_monthly_brl_base || 0)], ['Lucro base BRL', 'R$ ' + fmtNum(app.profit_monthly_brl_base || 0)], ['Confiança', app.financial_confidence], ['Notas financeiras', app.financial_notes]
  ];
  document.querySelector('#overviewPanel').innerHTML = `
    <h3 class="section-title">Resumo rápido</h3>
    <div class="text-box">${{esc(app.summary || raw.summary || 'Sem resumo coletado.')}}</div>
    ${{aiBrief ? `<h3 class="section-title mt-3">Parecer de oportunidade por IA</h3><div class="text-box">${{esc(cleanText(aiBrief))}}</div>` : ''}}
    <h3 class="section-title mt-3">Ficha completa</h3><div class="kv-grid">${{fields.map(x => kv(x[0], x[1])).join('')}}</div>
    <h3 class="section-title mt-3">Financeiro estimado</h3><div class="kv-grid">${{finance.map(x => kv(x[0], x[1])).join('')}}</div>`;
}}
function renderDescription(app, raw) {{
  const desc = cleanText(app.description || raw.description || app.external_description || raw.external_description || '');
  const changes = cleanText(app.recent_changes || raw.recentChanges || raw.recent_changes || '');
  const ext = cleanText(app.external_markdown_preview || raw.external_markdown_preview || '');
  document.querySelector('#descriptionPanel').innerHTML = `
    <h3 class="section-title">Descrição da loja</h3>${{desc ? `<div class="text-box">${{esc(desc)}}</div>` : '<div class="empty">Sem descrição coletada.</div>'}}
    <h3 class="section-title mt-3">Mudanças recentes</h3>${{changes ? `<div class="text-box">${{esc(changes)}}</div>` : '<div class="empty">Sem changelog coletado.</div>'}}
    <h3 class="section-title mt-3">Preview externo limpo</h3>${{ext ? `<div class="text-box">${{esc(ext)}}</div>` : '<div class="empty">Sem preview externo.</div>'}}`;
}}
function renderReviews(app, raw) {{
  const samples = listFromJson(app.review_samples_json || raw.review_samples || []);
  const keywords = listFromJson(app.review_keywords_json || raw.review_keywords || []);
  const dist = parseMaybeJson(raw.review_distribution_recent || app.review_distribution_recent || null);
  const reviewHtml = samples.length ? samples.map(r => `
    <div class="review-card"><header><span>★ ${{esc(r.score || r.rating || 'N/A')}}</span><span>${{esc(r.at || r.date || '')}}</span></header><div>${{esc(r.content || r.text || JSON.stringify(r))}}</div><small class="text-muted">${{fmtNum(r.thumbsUpCount || 0)}} curtidas</small></div>
  `).join('') : '<div class="empty">Nenhuma review coletada.</div>';
  document.querySelector('#reviewsPanel').innerHTML = `
    <h3 class="section-title">Resumo das reviews</h3>
    <div class="kv-grid">
      ${{kv('Média recente', app.review_score_avg_recent)}}${{kv('Positivas', app.review_positive_pct ? app.review_positive_pct + '%' : '')}}${{kv('Negativas', app.review_negative_pct ? app.review_negative_pct + '%' : '')}}${{kv('Distribuição', dist && typeof dist === 'object' ? JSON.stringify(dist) : '')}}
    </div>
    <h3 class="section-title mt-3">Palavras frequentes</h3>
    ${{keywords.length ? `<div class="chip-list">${{keywords.map(k => `<span class="chip">${{esc(k)}}</span>`).join('')}}</div>` : '<div class="empty">Sem keywords coletadas.</div>'}}
    <h3 class="section-title mt-3">Reviews recentes coletadas</h3>${{reviewHtml}}`;
}}
function renderMedia(app, raw) {{
  const shots = listFromJson(app.screenshots_json || raw.screenshots || []);
  const header = app.header_image || raw.headerImage;
  const video = app.video || raw.video;
  document.querySelector('#mediaPanel').innerHTML = `
    <h3 class="section-title">Mídia</h3>
    <div class="kv-grid">${{kv('Header image', header)}}${{kv('Vídeo', video)}}${{kv('Ícone', app.icon || raw.icon)}}</div>
    <h3 class="section-title mt-3">Screenshots</h3>
    ${{shots.length ? `<div class="shot-grid">${{shots.map(src => `<a href="${{esc(src)}}" target="_blank" rel="noopener"><img loading="lazy" src="${{esc(src)}}" alt="Screenshot"></a>`).join('')}}</div>` : '<div class="empty">Sem screenshots coletados.</div>'}}`;
}}
function renderTechnical(app, raw) {{
  const technical = [
    ['URL', app.url], ['External title', app.external_title], ['External description', app.external_description], ['Sources', app.external_sources_used], ['Raw DB ID', app.id], ['Run criada em', app.run_created_at], ['Run level', app.run_level], ['Run profile', app.run_profile], ['Run scope', app.run_scope]
  ];
  document.querySelector('#technicalPanel').innerHTML = `
    <h3 class="section-title">Dados técnicos</h3><div class="kv-grid">${{technical.map(x => kv(x[0], x[1])).join('')}}</div>
    <div class="raw-tools mt-3"><h3 class="section-title mb-0">JSON bruto completo deste app</h3><button class="copy-json" type="button" id="copyJsonBtn">copiar JSON</button></div>
    <pre class="raw-json"><code>${{esc(currentAppJson || JSON.stringify(raw, null, 2))}}</code></pre>`;
  const btn = document.querySelector('#copyJsonBtn');
  if(btn) btn.addEventListener('click', async () => {{
    try {{ await navigator.clipboard.writeText(currentAppJson || ''); btn.textContent = 'copiado'; setTimeout(() => btn.textContent = 'copiar JSON', 1400); }}
    catch(e) {{ btn.textContent = 'falhou'; setTimeout(() => btn.textContent = 'copiar JSON', 1400); }}
  }});
}}
function setTab(name) {{
  document.querySelectorAll('#modalTabs button').forEach(btn => btn.classList.toggle('active', btn.dataset.tab === name));
  document.querySelectorAll('.tab-panel').forEach(panel => panel.classList.toggle('active', panel.dataset.panel === name));
}}
function closeModal() {{
  const modal = document.querySelector('#appModal');
  modal.classList.remove('open');
  modal.setAttribute('aria-hidden', 'true');
  document.body.style.overflow = '';
}}
[q,cat,profile,minScore].forEach(el => el.addEventListener('input', filt));
document.querySelectorAll('.sort-pills button').forEach(btn => btn.addEventListener('click', () => sortRows(btn.dataset.sort, btn.dataset.dir)));
document.querySelectorAll('.app-row').forEach(row => {{
  row.addEventListener('click', (ev) => {{ if(ev.target.closest('.external-link')) return; openAppModal(Number(row.dataset.appIndex)); }});
  row.addEventListener('keydown', (ev) => {{ if(ev.key === 'Enter' || ev.key === ' ') {{ ev.preventDefault(); openAppModal(Number(row.dataset.appIndex)); }} }});
}});
document.querySelectorAll('[data-open-app]').forEach(btn => btn.addEventListener('click', ev => {{ ev.stopPropagation(); openAppModal(Number(btn.dataset.openApp)); }}));
document.querySelector('#modalClose').addEventListener('click', closeModal);
document.querySelector('#appModal').addEventListener('click', ev => {{ if(ev.target.id === 'appModal') closeModal(); }});
document.addEventListener('keydown', ev => {{ if(ev.key === 'Escape') closeModal(); }});
document.querySelectorAll('#modalTabs button').forEach(btn => btn.addEventListener('click', () => setTab(btn.dataset.tab)));
filt();
</script>
</body>
</html>"""
    path.write_text(html, encoding="utf-8")
    return str(path)


def export_run_html(db_path: str | Path, run_id: int, output_dir: Path) -> str:
    output_dir.mkdir(parents=True, exist_ok=True)
    run = get_run(db_path, run_id) or {}
    apps = load_apps(db_path, run_id)
    kicker = f"Run #{run_id} · {h(run.get('created_at'))}"
    subtitle = f"{h(run.get('level'))} · {h(run.get('profile'))} · {h(run.get('scope'))} · relatório em tabela com modal completo por app"
    path = output_dir / f"playstore_run_{run_id}.html"
    return _render_report_html(path, f"PlayStore Radar Ultra · Run #{run_id}", kicker, subtitle, apps)


def export_all_html(db_path: str | Path, output_dir: Path) -> str:
    """Exporta um único relatório HTML combinando os apps de todas as buscas."""
    output_dir.mkdir(parents=True, exist_ok=True)
    runs = list_runs(db_path, 10_000)
    apps = load_all_apps(db_path)
    exported_at = datetime.now().strftime("%d/%m/%Y %H:%M")
    kicker = f"Todas as buscas · {len(runs)} runs · exportado em {exported_at}"
    subtitle = f"{len(apps)} apps combinados de todas as buscas · relatório em tabela com modal completo por app"
    path = output_dir / f"{ALL_RUNS_BASENAME}.html"
    return _render_report_html(path, "PlayStore Radar Ultra · Todas as buscas", kicker, subtitle, apps)


def export_run_all(db_path: str | Path, run_id: int, output_dir: Path) -> Dict[str, str]:
    return {
        "html": export_run_html(db_path, run_id, output_dir),
        "json": export_run_json(db_path, run_id, output_dir),
        "csv": export_run_csv(db_path, run_id, output_dir),
    }


def export_all_formats(db_path: str | Path, output_dir: Path) -> Dict[str, str]:
    """Exporta todas as buscas de uma vez, num único arquivo por formato."""
    return {
        "html": export_all_html(db_path, output_dir),
        "json": export_all_json(db_path, output_dir),
        "csv": export_all_csv(db_path, output_dir),
    }


_SINGLE_RUN_EXPORTERS = {
    "html": export_run_html,
    "json": export_run_json,
    "csv": export_run_csv,
}


def export_all_separate_zip(db_path: str | Path, fmt: str, output_dir: Path) -> Optional[str]:
    """Exporta um arquivo por run (no formato pedido) e empacota tudo num .zip.
    Retorna None se não houver nenhuma run salva."""
    exporter = _SINGLE_RUN_EXPORTERS.get(fmt)
    if not exporter:
        return None
    runs = list_runs(db_path, 10_000)
    if not runs:
        return None
    output_dir.mkdir(parents=True, exist_ok=True)
    zip_path = output_dir / f"{ALL_RUNS_BASENAME}_{fmt}_separado.zip"
    with zipfile.ZipFile(zip_path, "w", zipfile.ZIP_DEFLATED) as zf:
        for run in runs:
            run_id = run.get("id")
            if run_id is None:
                continue
            file_path = exporter(db_path, run_id, output_dir)
            zf.write(file_path, arcname=Path(file_path).name)
    return str(zip_path)
