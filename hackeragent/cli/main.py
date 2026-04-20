"""HackerAgent CLI entry point.

Kullanım:
    hackeragent                         # İnteraktif REPL
    hackeragent --task "..."            # Tek görev
    hackeragent --config path.yaml      # Özel config
    hackeragent --list-tools            # Aktif MCP tool'larını listele
    hackeragent --resume last           # Son session'a devam
    hackeragent --resume <id>           # Belirli session
    hackeragent --list-sessions         # Session'ları listele
    hackeragent --budget 5.00           # Session maliyet limiti (USD)
    hackeragent --scope 10.10.10.5      # Scope entry (tekrarlanabilir)
    hackeragent --no-stream             # Streaming kapat
"""

from __future__ import annotations

import argparse
import sys
from datetime import datetime

from hackeragent import __version__
from hackeragent.cli.banner import BANNER
from hackeragent.core.config import get_config
from hackeragent.core.orchestrator import Orchestrator
from hackeragent.core.session import Session
from hackeragent.utils.logger import setup_logging

try:
    from rich.console import Console
    from rich.live import Live
    from rich.markdown import Markdown
    from rich.panel import Panel
    from rich.prompt import Prompt
    from rich.table import Table
    HAS_RICH = True
except ImportError:  # pragma: no cover
    HAS_RICH = False


def _progress_factory(console):
    """Tool call olaylarını ekrana yazdıran callback üret."""
    def _cb(event: str, data: dict):
        if not console:
            print(f"[{event}] {data}")
            return
        if event == "ready":
            console.print(
                f"[green]✓[/green] {len(data.get('servers', []))} MCP server aktif, "
                f"[cyan]{data.get('tool_count', 0)}[/cyan] tool hazır. "
                f"[dim]Session:[/dim] [yellow]{data.get('session_id', '?')}[/yellow]"
            )
            scope = data.get("scope", [])
            if scope:
                console.print(f"  [dim]Scope:[/dim] {', '.join(scope)}")
            else:
                console.print("  [yellow]⚠ Scope boş[/yellow] — `/scope add <hedef>` ile kısıtlayın")
            budget = data.get("budget", 0)
            if budget:
                console.print(f"  [dim]Bütçe limiti:[/dim] [green]${budget:.2f}[/green]")
        elif event == "tool_call":
            console.print(f"  [dim]→[/dim] [yellow]{data.get('name', '?')}[/yellow]")
        elif event == "tool_result":
            console.print(f"  [dim]←[/dim] [green]{data.get('chars', 0)} char[/green]")
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
        t = Table(title=f"MCP Tools ({len(tools)})", show_lines=False)
        t.add_column("Server", style="cyan")
        t.add_column("Tool", style="yellow")
        for server, name in sorted(tools):
            t.add_row(server, name)
        console.print(t)
    else:
        for s, n in sorted(tools):
            print(f"  {s}.{n}")


def _cmd_list_sessions(console) -> None:
    rows = Session.list_all(limit=20)
    if not rows:
        print("Hiç session yok.")
        return
    if HAS_RICH and console:
        t = Table(title="Son Sessionlar", show_lines=False)
        t.add_column("ID", style="cyan")
        t.add_column("Güncellendi", style="dim")
        t.add_column("Tur", justify="right")
        t.add_column("Hedef", style="yellow")
        t.add_column("Maliyet $", justify="right", style="green")
        for r in rows:
            ts = datetime.fromtimestamp(r["updated_at"]).strftime("%Y-%m-%d %H:%M")
            t.add_row(r["id"], ts, str(r["turns"]), r["target"] or "—", f"{r['cost_usd']:.4f}")
        console.print(t)
    else:
        for r in rows:
            print(f"  {r['id']:40} turns={r['turns']:3} target={r['target']}")


def _handle_slash(orch: Orchestrator, console, line: str) -> bool:
    """Slash komutlarını işle. True dönerse REPL devam etsin (bu komut handle edildi)."""
    parts = line.split(maxsplit=2)
    cmd = parts[0].lower()

    if cmd in ("/exit", "/quit", "exit", "quit"):
        return False  # çık

    if cmd == "/reset":
        orch.reset()
        if console:
            console.print("[green]✓[/green] Sohbet geçmişi sıfırlandı.")
        return True

    if cmd == "/tools":
        _cmd_list_tools(orch, console)
        return True

    if cmd == "/sessions":
        _cmd_list_sessions(console)
        return True

    if cmd == "/budget":
        if console:
            console.print(orch.budget_summary())
        else:
            print(orch.budget_summary())
        return True

    if cmd == "/scope":
        sub = parts[1].lower() if len(parts) > 1 else "list"
        if sub == "list":
            rules = orch.scope.list_raw()
            if not rules:
                if console:
                    console.print("[yellow]Scope boş.[/yellow] `/scope add <hedef>` ile ekleyin.")
                else:
                    print("Scope boş.")
            else:
                if console:
                    console.print("[bold]Scope:[/bold] " + ", ".join(rules))
                else:
                    print("Scope: " + ", ".join(rules))
        elif sub == "add" and len(parts) > 2:
            orch.scope.add(parts[2])
            if console:
                console.print(f"[green]✓[/green] Scope eklendi: {parts[2]}")
        elif sub in ("rm", "remove") and len(parts) > 2:
            removed = orch.scope.remove(parts[2])
            if console:
                console.print(f"[{'green' if removed else 'red'}]{'✓ Kaldırıldı' if removed else '✗ Bulunamadı'}[/]: {parts[2]}")
        elif sub == "clear":
            orch.scope.rules.clear()
            if console:
                console.print("[green]✓[/green] Scope temizlendi.")
        else:
            if console:
                console.print("[dim]Kullanım:[/dim] /scope list | /scope add <host> | /scope rm <host> | /scope clear")
        return True

    if cmd == "/help":
        help_txt = (
            "[bold]Komutlar:[/bold]\n"
            "  /exit, /quit           Çık\n"
            "  /reset                 Sohbet geçmişini sıfırla\n"
            "  /tools                 Aktif MCP tool'larını listele\n"
            "  /sessions              Geçmiş session'ları göster\n"
            "  /budget                Mevcut maliyet özeti\n"
            "  /scope list            Aktif scope'u göster\n"
            "  /scope add <hedef>     Scope'a host/IP/CIDR ekle\n"
            "  /scope rm <hedef>      Scope'tan kaldır\n"
            "  /scope clear           Scope'u sıfırla\n"
            "  /help                  Bu yardım"
        )
        if console:
            console.print(help_txt)
        else:
            print(help_txt.replace("[bold]", "").replace("[/bold]", ""))
        return True

    # Slash değil → normal kullanıcı girişi
    return None  # type: ignore


def _run_repl(orch: Orchestrator, console) -> int:
    _print_banner(console)
    orch.start()

    if HAS_RICH and console:
        console.print(
            "[dim]Yardım için [bold]/help[/bold] yazın. Çıkış: [bold]/exit[/bold][/dim]\n"
        )
    else:
        print("Yardım: /help, çıkış: /exit\n")

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

        # Slash komut?
        if user.startswith("/") or user in ("exit", "quit"):
            r = _handle_slash(orch, console, user)
            if r is False:
                break
            if r is True:
                continue
            # None → düş, normal mesaj olarak işle
        # Normal LLM turu
        _run_turn(orch, console, user)

    # Session özeti
    if console:
        console.print("\n" + orch.budget_summary())
        console.print(f"[dim]Session kaydedildi:[/dim] [cyan]{orch.session.id}[/cyan]")
    return 0


def _run_turn(orch: Orchestrator, console, user: str) -> None:
    """Tek bir kullanıcı turunu çalıştır — streaming + panel render."""
    if not orch.streaming_enabled or not HAS_RICH or console is None:
        try:
            reply = orch.ask(user)
        except KeyboardInterrupt:
            print("\n[!] İstek iptal edildi.")
            return
        except Exception as e:
            if console:
                console.print(f"[red]HATA:[/red] {e}")
            else:
                print(f"HATA: {e}")
            return
        if HAS_RICH and console:
            console.print(Panel(Markdown(reply), border_style="green", title="HackerAgent"))
        else:
            print("\n--- HackerAgent ---\n" + reply + "\n")
        return

    # Streaming mode — Live render
    buffer: list[str] = []

    def on_delta(chunk: str) -> None:
        buffer.append(chunk)
        live.update(Panel(Markdown("".join(buffer)), border_style="cyan", title="HackerAgent (streaming...)"))

    orch.stream_callback = on_delta

    try:
        with Live(
            Panel(Markdown("…"), border_style="cyan", title="HackerAgent (streaming...)"),
            console=console, refresh_per_second=12, transient=False,
        ) as live:
            try:
                reply = orch.ask(user)
            finally:
                orch.stream_callback = None
            # Final render — yeşil panel
            live.update(Panel(Markdown(reply or "".join(buffer) or "(boş)"),
                              border_style="green", title="HackerAgent"))
    except KeyboardInterrupt:
        console.print("\n[yellow]İstek iptal edildi.[/yellow]")
    except Exception as e:
        console.print(f"[red]HATA:[/red] {e}")


def _run_single(orch: Orchestrator, task: str, console) -> int:
    orch.start()
    _run_turn(orch, console, task)
    if console:
        console.print("\n" + orch.budget_summary())
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
    p.add_argument("--list-sessions", action="store_true", help="Geçmiş session'ları listele ve çık")
    p.add_argument("--resume", default=None, metavar="ID|last",
                   help="Mevcut session'a devam et (`last` = en son)")
    p.add_argument("--budget", type=float, default=None,
                   help="Session maksimum maliyet limiti (USD)")
    p.add_argument("--scope", action="append", default=[],
                   help="Scope entry (IP/CIDR/domain/*.domain). Birden fazla kez verilebilir")
    p.add_argument("--no-stream", action="store_true", help="Streaming yanıtı kapat")
    p.add_argument("--log-level", default=None, help="Log level (DEBUG/INFO/WARNING/ERROR)")
    return p


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)

    cfg = get_config(args.config)
    # CLI overrides
    if args.budget is not None:
        cfg.data.setdefault("llm", {})["max_session_cost_usd"] = args.budget
    if args.scope:
        existing = cfg.data.setdefault("safety", {}).get("scope", []) or []
        cfg.data["safety"]["scope"] = list(existing) + list(args.scope)
    if args.no_stream:
        cfg.data.setdefault("llm", {})["streaming"] = False

    setup_logging(
        level=args.log_level or cfg.get("logging.level", "INFO"),
        file=cfg.get("logging.file"),
    )
    console = Console(stderr=False) if HAS_RICH else None

    # --list-sessions config/key gerektirmez
    if args.list_sessions:
        _cmd_list_sessions(console)
        return 0

    if not cfg.openrouter_api_key:
        msg = (
            "OPENROUTER_API_KEY ayarlı değil. "
            "Lütfen .env veya ~/.hackeragent/config.yaml içine ekleyin."
        )
        if console:
            console.print(f"[red]✗[/red] {msg}")
        else:
            print(f"HATA: {msg}", file=sys.stderr)
        if not args.list_tools:
            return 2

    try:
        if args.list_tools:
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

        # Resume?
        if args.resume:
            try:
                if args.resume == "last":
                    last = Session.load_last()
                    if not last:
                        if console:
                            console.print("[yellow]Hiç session yok, yeni başlatılıyor.[/yellow]")
                    else:
                        orch.resume(last.id)
                        if console:
                            console.print(f"[green]✓[/green] Session devam ediyor: [cyan]{last.id}[/cyan]")
                else:
                    orch.resume(args.resume)
                    if console:
                        console.print(f"[green]✓[/green] Session devam ediyor: [cyan]{args.resume}[/cyan]")
            except FileNotFoundError as e:
                if console:
                    console.print(f"[red]✗[/red] {e}")
                else:
                    print(f"HATA: {e}")
                return 1

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
