"""HackerAgent CLI entry point.

Kullanım:
    hackeragent                         # İnteraktif REPL
    hackeragent --task "..."            # Tek görev
    hackeragent --config path.yaml      # Özel config
    hackeragent --list-tools            # Aktif MCP tool'larını listele
"""

from __future__ import annotations

import argparse
import sys

from hackeragent import __version__
from hackeragent.cli.banner import BANNER
from hackeragent.core.config import get_config
from hackeragent.core.orchestrator import Orchestrator
from hackeragent.utils.logger import setup_logging

try:
    from rich.console import Console
    from rich.markdown import Markdown
    from rich.panel import Panel
    from rich.prompt import Prompt
    HAS_RICH = True
except ImportError:  # pragma: no cover
    HAS_RICH = False


def _progress_factory(console):
    """Tool call olaylarını ekrana yazdıran callback üret."""
    def _cb(event: str, data: dict):
        if event == "ready":
            if HAS_RICH and console:
                console.print(
                    f"[green]✓[/green] {len(data.get('servers', []))} MCP server aktif, "
                    f"[cyan]{data.get('tool_count', 0)}[/cyan] tool hazır."
                )
            else:
                print(f"[+] {len(data.get('servers', []))} MCP server aktif, {data.get('tool_count', 0)} tool.")
        elif event == "tool_call":
            name = data.get("name", "?")
            if HAS_RICH and console:
                console.print(f"  [dim]→[/dim] [yellow]{name}[/yellow]")
            else:
                print(f"  -> {name}")
        elif event == "tool_result":
            chars = data.get("chars", 0)
            if HAS_RICH and console:
                console.print(f"  [dim]←[/dim] [green]{chars} char[/green]")
            else:
                print(f"  <- {chars} chars")
    return _cb


def _print_banner(console) -> None:
    if HAS_RICH and console:
        console.print(Panel.fit(BANNER.strip(), border_style="red"))
    else:
        print(BANNER)


def _cmd_list_tools(orch: Orchestrator, console) -> None:
    orch.start()
    tools = orch.available_tools()
    if not tools:
        print("Hiçbir MCP tool yüklenmedi.")
        return
    if HAS_RICH and console:
        from rich.table import Table
        t = Table(title=f"MCP Tools ({len(tools)})", show_lines=False)
        t.add_column("Server", style="cyan")
        t.add_column("Tool", style="yellow")
        for server, name in sorted(tools):
            t.add_row(server, name)
        console.print(t)
    else:
        for s, n in sorted(tools):
            print(f"  {s}.{n}")


def _run_repl(orch: Orchestrator, console) -> int:
    _print_banner(console)
    orch.start()

    if HAS_RICH and console:
        console.print(
            "[dim]Komutlar: [bold]/exit[/bold] çık, [bold]/reset[/bold] sohbeti sıfırla, "
            "[bold]/tools[/bold] araçları listele[/dim]\n"
        )
    else:
        print("Komutlar: /exit  /reset  /tools\n")

    while True:
        try:
            if HAS_RICH and console:
                user = Prompt.ask("[bold red]hackeragent[/bold red]")
            else:
                user = input("hackeragent> ")
        except (EOFError, KeyboardInterrupt):
            print()
            break

        user = user.strip()
        if not user:
            continue
        if user in ("/exit", "/quit", "exit", "quit"):
            break
        if user == "/reset":
            orch.reset()
            if console:
                console.print("[green]✓[/green] Sohbet geçmişi sıfırlandı.")
            continue
        if user == "/tools":
            _cmd_list_tools(orch, console)
            continue

        try:
            reply = orch.ask(user)
        except KeyboardInterrupt:
            print("\n[!] İstek iptal edildi.")
            continue
        except Exception as e:
            if console:
                console.print(f"[red]HATA:[/red] {e}")
            else:
                print(f"HATA: {e}")
            continue

        if HAS_RICH and console:
            console.print(Panel(Markdown(reply), border_style="green", title="HackerAgent"))
        else:
            print("\n--- HackerAgent ---\n" + reply + "\n")

    return 0


def _run_single(orch: Orchestrator, task: str, console) -> int:
    orch.start()
    reply = orch.ask(task)
    if HAS_RICH and console:
        console.print(Markdown(reply))
    else:
        print(reply)
    return 0


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        prog="hackeragent",
        description="HackerAgent v3.0 — Otonom pentest / CTF / bug-bounty orkestratörü",
    )
    p.add_argument("--version", action="version", version=f"hackeragent {__version__}")
    p.add_argument("--config", default=None, help="Ek config.yaml yolu")
    p.add_argument("--task", default=None, help="Tek seferlik görev (REPL açmaz)")
    p.add_argument("--list-tools", action="store_true", help="Aktif MCP tool'larını listele ve çık")
    p.add_argument("--log-level", default=None, help="Log level (DEBUG/INFO/WARNING/ERROR)")
    return p


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)

    cfg = get_config(args.config)
    setup_logging(
        level=args.log_level or cfg.get("logging.level", "INFO"),
        file=cfg.get("logging.file"),
    )
    console = Console(stderr=False) if HAS_RICH else None

    if not cfg.openrouter_api_key:
        msg = (
            "OPENROUTER_API_KEY ayarlı değil. "
            "Lütfen .env veya ~/.hackeragent/config.yaml içine ekleyin."
        )
        if console:
            console.print(f"[red]✗[/red] {msg}")
        else:
            print(f"HATA: {msg}", file=sys.stderr)
        # list-tools config.openrouter_api_key gerektirmez ama orchestrator init
        # sırasında key yoksa patlar — bu yüzden list-tools'a özel dal:
        if not args.list_tools:
            return 2

    try:
        if args.list_tools:
            # list-tools için LLM client'a ihtiyaç yok ama orchestrator init
            # client'ı build ediyor. Key yoksa minimum bir placeholder koyalım.
            import os as _os
            _os.environ.setdefault("OPENROUTER_API_KEY", cfg.openrouter_api_key or "placeholder-for-list-tools")
            cfg.data.setdefault("llm", {})["openrouter_api_key"] = _os.environ["OPENROUTER_API_KEY"]
            orch = Orchestrator(config=cfg)
            orch.progress = _progress_factory(console)
            try:
                _cmd_list_tools(orch, console)
            finally:
                orch.shutdown()
            return 0

        orch = Orchestrator(config=cfg)
        orch.progress = _progress_factory(console)
        try:
            if args.task:
                return _run_single(orch, args.task, console)
            return _run_repl(orch, console)
        finally:
            orch.shutdown()
    except KeyboardInterrupt:
        return 130


if __name__ == "__main__":
    sys.exit(main())
