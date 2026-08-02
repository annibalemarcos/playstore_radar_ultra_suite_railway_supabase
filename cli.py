from __future__ import annotations

import argparse
import os
import sys
import webbrowser
from pathlib import Path
from typing import Any, Dict

from rich import box
from rich.align import Align
from rich.console import Console
from rich.panel import Panel
from rich.progress import BarColumn, Progress, SpinnerColumn, TextColumn, TimeElapsedColumn
from rich.prompt import Prompt
from rich.table import Table
from rich.text import Text

from app_core.categories import CATEGORIAS_APPS, CATEGORIAS_JOGOS
from app_core.config import ApiConfig, LEVELS, PROFILES, SCOPES, RunConfig
from app_core.runner import run_scraper

console = Console()


def clear() -> None:
    os.system("cls" if os.name == "nt" else "clear")


def banner() -> None:
    clear()
    title = Text("🚀 PlayStore Radar Ultra", style="bold cyan")
    subtitle = Text("Google Play BR • indie radar • crescimento • dinheiro no faro", style="white")
    console.print(Panel(Align.center(title + "\n" + subtitle), border_style="cyan", box=box.ROUNDED))


def show_api_table(api: ApiConfig) -> None:
    table = Table(title="APIs detectadas no .env/ambiente", box=box.ROUNDED, border_style="magenta")
    table.add_column("API", style="cyan")
    table.add_column("Status", justify="center")
    for name, ok in api.available().items():
        table.add_row(name, "[green]ativa[/green]" if ok else "[dim]sem key[/dim]")
    console.print(table)


def prompt_choice(prompt: str, choices: Dict[str, str], default: str) -> str:
    table = Table(show_header=False, box=box.ROUNDED, border_style="cyan")
    table.add_column("Opção", style="bold cyan", width=14, justify="center")
    table.add_column("Descrição", style="yellow")
    for key, desc in choices.items():
        table.add_row("ENTER" if key == default else key, desc)
    console.print(table)
    raw = Prompt.ask(f"[bold cyan]{prompt}[/bold cyan]", default=default).strip()
    return raw or default


def prompt_int(prompt: str, default: int, minimo: int = 1, maximo: int | None = None) -> int:
    while True:
        raw = Prompt.ask(f"[bold cyan]{prompt}[/bold cyan]", default=str(default)).strip()
        if not raw:
            return default
        try:
            value = int(raw)
        except ValueError:
            console.print("[red]Digite um número. O terminal ainda não lê pensamento, infelizmente.[/red]")
            continue
        if value < minimo:
            console.print(f"[red]Mínimo: {minimo}.[/red]")
            continue
        if maximo is not None and value > maximo:
            console.print(f"[red]Máximo: {maximo}.[/red]")
            continue
        return value



def prompt_categories(scope: str) -> str:
    """Permite escolher categorias no terminal. ENTER = todas."""
    if scope == "TODAS":
        return ""
    source = CATEGORIAS_APPS if scope == "APPS" else CATEGORIAS_JOGOS
    table = Table(title="Categorias disponíveis — ENTER = todas", box=box.ROUNDED, border_style="cyan")
    table.add_column("Nº", style="bold cyan", width=5)
    table.add_column("Código", style="yellow")
    table.add_column("Nome")
    for idx, (code, name, _term) in source.items():
        table.add_row(str(idx), code, name)
    console.print(table)
    raw = Prompt.ask("[bold cyan]Escolha categorias por número/código, separadas por vírgula[/bold cyan]", default="").strip()
    if not raw:
        return ""
    selected = []
    reverse = {str(idx): code for idx, (code, _name, _term) in source.items()}
    valid_codes = {code for code, _name, _term in source.values()}
    for part in raw.replace(";", ",").split(","):
        token = part.strip().upper()
        if not token:
            continue
        code = reverse.get(token) or token
        if code in valid_codes:
            selected.append(code)
        else:
            console.print(f"[yellow]Ignorando categoria inválida: {token}[/yellow]")
    return ",".join(dict.fromkeys(selected))

def build_interactive_config(api: ApiConfig) -> RunConfig:
    banner()
    show_api_table(api)

    scope_choice = prompt_choice(
        "Escopo de categorias",
        {
            "0": "📊 Apps + Jogos — padrão",
            "1": "📱 Somente aplicativos",
            "2": "🎮 Somente jogos",
        },
        default="0",
    )
    scope = {"0": "TODAS", "1": "APPS", "2": "JOGOS"}.get(scope_choice, "TODAS")
    category_codes = prompt_categories(scope)

    console.print("\n[bold yellow]Nível da coleta[/bold yellow]")
    level_choice = prompt_choice(
        "Modo",
        {
            "0": LEVELS["SIMPLES"],
            "1": LEVELS["PROFUNDO"],
            "2": LEVELS["FINANCEIRO"],
            "3": LEVELS["FULL"],
            "4": LEVELS["ULTRA_FULL"],
        },
        default="0",
    )
    level = {"0": "SIMPLES", "1": "PROFUNDO", "2": "FINANCEIRO", "3": "FULL", "4": "ULTRA_FULL"}.get(level_choice, "SIMPLES")

    console.print("\n[bold yellow]Perfil de apps[/bold yellow]")
    profile_choice = prompt_choice(
        "Filtro/estratégia",
        {
            "0": PROFILES["TODOS"],
            "1": PROFILES["PEQUENOS_INDIE"],
            "2": PROFILES["CRESCENDO"],
            "3": PROFILES["OPORTUNIDADE"],
            "4": PROFILES["SEM_GIGANTES"],
        },
        default="0",
    )
    profile = {
        "0": "TODOS",
        "1": "PEQUENOS_INDIE",
        "2": "CRESCENDO",
        "3": "OPORTUNIDADE",
        "4": "SEM_GIGANTES",
    }.get(profile_choice, "TODOS")

    quantity = prompt_int("Quantos apps por categoria? ENTER=25", default=25, minimo=1, maximo=500)
    raw_limit_cat = Prompt.ask("[bold cyan]Limitar número de categorias? ENTER=todas[/bold cyan]", default="").strip()
    max_categories = int(raw_limit_cat) if raw_limit_cat.isdigit() and int(raw_limit_cat) > 0 else None
    open_html = Prompt.ask("[bold cyan]Abrir HTML ao finalizar? ENTER=sim / n=não[/bold cyan]", default="s").strip().lower() not in {"n", "nao", "não", "no"}

    cfg = RunConfig(scope=scope, level=level, profile=profile, quantity=quantity, max_categories=max_categories, open_html=open_html, category_codes=category_codes)
    cfg.apply_level_defaults(api)
    show_run_summary(cfg)
    return cfg


def show_run_summary(cfg: RunConfig) -> None:
    table = Table(title="Resumo antes de sair raspando o asfalto", box=box.ROUNDED, border_style="green")
    table.add_column("Item", style="cyan")
    table.add_column("Valor", style="yellow")
    table.add_row("Escopo", SCOPES.get(cfg.scope, cfg.scope))
    table.add_row("Nível", cfg.level)
    table.add_row("Perfil", cfg.profile)
    table.add_row("Apps/categoria", str(cfg.quantity))
    table.add_row("Detalhes", "todos" if cfg.detail_limit is None else str(cfg.detail_limit))
    table.add_row("Reviews/app", str(cfg.reviews_per_app))
    table.add_row("APIs externas", "sim" if cfg.use_external_apis else "não")
    table.add_row("Categorias", "todas" if not cfg.category_codes else cfg.category_codes)
    table.add_row("Limite de categorias", "todas" if cfg.max_categories is None else str(cfg.max_categories))
    table.add_row("Banco", cfg.db_path)
    console.print(table)
    Prompt.ask("[bold green]ENTER para começar[/bold green]", default="")


def parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(description="PlayStore Radar Ultra — CLI Rich + scraper Google Play")
    p.add_argument("--no-interactive", action="store_true", help="Roda sem perguntas, usando argumentos/padrões.")
    p.add_argument("--scope", choices=list(SCOPES.keys()), default="TODAS")
    p.add_argument("--level", choices=list(LEVELS.keys()), default="SIMPLES")
    p.add_argument("--profile", choices=list(PROFILES.keys()), default="TODOS")
    p.add_argument("--quantity", type=int, default=25)
    p.add_argument("--max-categories", type=int, default=None)
    p.add_argument("--categories", default="", help="CSV de códigos de categorias. Ex: PRODUCTIVITY,TOOLS ou GAME_CASUAL,GAME_PUZZLE. Vazio = todas.")
    p.add_argument("--db-path", default=None)
    p.add_argument("--output-dir", default=None)
    p.add_argument("--no-open", action="store_true")
    return p.parse_args()


def main() -> None:
    args = parse_args()
    api = ApiConfig()
    if args.no_interactive:
        cfg = RunConfig(scope=args.scope, level=args.level, profile=args.profile, quantity=args.quantity, max_categories=args.max_categories, category_codes=args.categories)
        if args.db_path:
            cfg.db_path = args.db_path
        if args.output_dir:
            cfg.output_dir = args.output_dir
        cfg.open_html = not args.no_open
        cfg.apply_level_defaults(api)
        banner()
        show_api_table(api)
        show_run_summary(cfg)
    else:
        cfg = build_interactive_config(api)

    progress = Progress(
        SpinnerColumn(),
        TextColumn("[progress.description]{task.description}"),
        BarColumn(),
        TextColumn("{task.completed}/{task.total}"),
        TimeElapsedColumn(),
        console=console,
    )
    cat_task = None
    app_task = None

    def on_event(payload: Dict[str, Any]) -> None:
        nonlocal cat_task, app_task
        ev = payload.get("event")
        if ev == "start":
            console.print(f"[green]Run #{payload.get('run_id')} iniciado.[/green]")
        elif ev == "category_start":
            if cat_task is None:
                cat_task = progress.add_task("Categorias", total=payload.get("total") or 1)
            progress.update(cat_task, description=f"Categoria: {payload.get('category')}")
            if app_task is not None:
                progress.remove_task(app_task)
                app_task = None
        elif ev == "app_start":
            if app_task is None:
                app_task = progress.add_task("Apps", total=payload.get("app_total") or 1)
            progress.update(app_task, completed=(payload.get("app_index") or 1) - 1, total=payload.get("app_total") or 1, description=f"App: {payload.get('title')}")
        elif ev == "app_kept":
            if app_task is not None:
                progress.advance(app_task)
        elif ev == "category_done":
            if cat_task is not None:
                progress.advance(cat_task)
        elif ev == "finish":
            console.print(f"[bold green]Finalizado: {payload.get('kept')} apps salvos.[/bold green]")

    try:
        with progress:
            result = run_scraper(cfg, api=api, callback=on_event)
    except KeyboardInterrupt:
        console.print("\n[red]Interrompido pelo usuário.[/red]")
        sys.exit(130)
    except Exception as exc:  # noqa: BLE001
        console.print(f"[red]Erro: {exc}[/red]")
        sys.exit(1)

    console.print(Panel.fit(
        f"[bold green]✅ Coleta concluída[/bold green]\n\n"
        f"Run: [cyan]#{result.run_id}[/cyan]\n"
        f"Apps escaneados: [yellow]{result.apps_scanned}[/yellow]\n"
        f"Apps salvos: [yellow]{result.apps_kept}[/yellow]\n"
        f"Alertas/erros: [yellow]{len(result.errors)}[/yellow]\n"
        f"HTML: [cyan]{result.output_paths.get('html', 'N/A')}[/cyan]\n"
        f"JSON: [cyan]{result.output_paths.get('json', 'N/A')}[/cyan]\n"
        f"CSV: [cyan]{result.output_paths.get('csv', 'N/A')}[/cyan]",
        border_style="green",
        title="Concluído",
    ))

    html_path = result.output_paths.get("html")
    if cfg.open_html and html_path:
        try:
            webbrowser.open(Path(html_path).resolve().as_uri())
        except Exception:
            pass


if __name__ == "__main__":
    main()
