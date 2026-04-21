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
import signal
import sys
from datetime import datetime

from hackeragent import __version__
from hackeragent.cli.banner import BANNER
from hackeragent.core.config import get_config
from hackeragent.core.config_validator import format_validation_result, validate_config
from hackeragent.core.crash_reporter import install_excepthook, list_crashes, report_crash
from hackeragent.core.health import check_health, format_health_report
from hackeragent.core.orchestrator import Orchestrator
from hackeragent.core.session import Session
from hackeragent.core.workflow_launcher import list_workflows, load_workflow_prompt
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

    if cmd == "/circuit":
        stats = orch.breaker.stats()
        if not stats:
            if console:
                console.print("[dim]Henüz tool çağrısı yok — circuit breaker boş.[/dim]")
            else:
                print("Circuit breaker boş.")
            return True
        if HAS_RICH and console:
            t = Table(title="🔄 Circuit Breaker", show_lines=False)
            t.add_column("Tool", style="yellow")
            t.add_column("Çağrı", justify="right")
            t.add_column("Fail", justify="right", style="red")
            t.add_column("Ardışık", justify="right")
            t.add_column("Durum")
            for qn, s in sorted(stats.items()):
                status = "[red]OPEN[/red]" if s["open"] else "[green]closed[/green]"
                t.add_row(
                    qn, str(s["total_calls"]), str(s["total_failures"]),
                    str(s["consecutive"]), status,
                )
            console.print(t)
        else:
            for qn, s in sorted(stats.items()):
                status = "OPEN" if s["open"] else "closed"
                print(f"  {qn}: calls={s['total_calls']} fail={s['total_failures']} "
                      f"consec={s['consecutive']} [{status}]")
        return True

    if cmd == "/models":
        tiers = orch.model_router.tiers
        enabled = orch.model_router.enabled
        if HAS_RICH and console:
            t = Table(title=f"🧠 Model Router (enabled={enabled})", show_lines=False)
            t.add_column("Tier", style="cyan")
            t.add_column("Model", style="yellow")
            t.add_column("Kullanım")
            t.add_row("cheap", tiers.cheap, "Basit sohbet, ilk tur, kısa girdi")
            t.add_row("standard", tiers.standard, "Orkestrasyon, tool analizi (default)")
            t.add_row("premium", tiers.premium, "Exploit, rapor, uzun kod üretimi")
            console.print(t)
        else:
            print(f"Model Router (enabled={enabled}):")
            print(f"  cheap:    {tiers.cheap}")
            print(f"  standard: {tiers.standard}")
            print(f"  premium:  {tiers.premium}")
        return True

    if cmd == "/cache":
        sub = parts[1].lower() if len(parts) > 1 else "stats"
        if sub == "clear":
            n = orch.tool_cache.invalidate()
            if console:
                console.print(f"[green]✓[/green] Cache temizlendi — {n} entry silindi.")
            else:
                print(f"Cache temizlendi — {n} entry silindi.")
            return True
        stats = orch.tool_cache.stats()
        top = orch.tool_cache.top_entries(limit=10)
        if HAS_RICH and console:
            console.print(
                f"[bold]♻️  Tool Cache[/bold]  enabled=[cyan]{stats['enabled']}[/cyan]  "
                f"entries=[yellow]{stats['entries']}[/yellow]  "
                f"lookups=[yellow]{stats['lookups']}[/yellow]  "
                f"hits=[green]{stats['hits']}[/green]  "
                f"rate=[green]{stats['hit_rate'] * 100:.1f}%[/green]  "
                f"stores=[yellow]{stats['stores']}[/yellow]"
            )
            if top:
                t = Table(title="Top cache entries", show_lines=False)
                t.add_column("Key", style="yellow")
                t.add_column("Age(s)", justify="right")
                t.add_column("TTL(s)", justify="right")
                t.add_column("Hits", justify="right", style="green")
                t.add_column("Size", justify="right")
                for e in top:
                    t.add_row(e["key"][:60], str(e["age_s"]), str(e["ttl_s"]),
                              str(e["hits"]), str(e["size_chars"]))
                console.print(t)
        else:
            print(f"Cache: {stats}")
        return True

    if cmd == "/plan":
        plan = orch.current_plan
        if not plan:
            if console:
                console.print("[dim]Aktif plan yok.[/dim]")
            else:
                print("Aktif plan yok.")
            return True
        if HAS_RICH and console:
            t = Table(title=f"🗺️  Plan — {plan.task[:60]}", show_lines=False)
            t.add_column("#", style="cyan", justify="right")
            t.add_column("Hedef", style="yellow")
            t.add_column("Araçlar", style="dim")
            t.add_column("Başarı Kriteri", style="green")
            for s in plan.steps:
                t.add_row(str(s.step), s.goal, ", ".join(s.expected_tools)[:50],
                          s.success_criteria[:50])
            console.print(t)
        else:
            for s in plan.steps:
                print(f"  {s.step}. {s.goal} | tools={s.expected_tools}")
        return True

    if cmd == "/report":
        report = orch.cost_report()
        if console:
            console.print(report)
        else:
            print(report)
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

    if cmd == "/health":
        results = check_health(orch.mcp)
        txt = format_health_report(results)
        if console:
            unhealthy = sum(1 for r in results.values() if not r["healthy"])
            color = "red" if unhealthy else "green"
            console.print(f"[{color}]{txt}[/{color}]")
        else:
            print(txt)
        return True

    if cmd == "/crashes":
        crashes = list_crashes(limit=10)
        if not crashes:
            if console:
                console.print("[dim]Kayıtlı crash raporu yok. ✓[/dim]")
            else:
                print("Kayıtlı crash yok.")
            return True
        if HAS_RICH and console:
            t = Table(title="Son Crash Raporları (~/.hackeragent/crashes/)", show_lines=False)
            t.add_column("Zaman", style="dim")
            t.add_column("Component", style="cyan")
            t.add_column("Tip", style="red")
            t.add_column("Mesaj")
            for c in crashes:
                t.add_row(c["timestamp"][:19], c["component"], c["exception_type"], c["message"])
            console.print(t)
        else:
            for c in crashes:
                print(f"  {c['timestamp']} [{c['component']}] {c['exception_type']}: {c['message']}")
        return True

    if cmd == "/notify":
        # Test webhook: /notify test  veya  /notify critical "Başlık" "Özet"
        sub = parts[1] if len(parts) > 1 else "test"
        if sub == "test":
            sent = orch.notifier.send_finding(
                title="HackerAgent notifier test",
                severity="info",
                target="test.local",
                summary="Bu bir test bildirimdir.",
            )
            if console:
                if sent:
                    console.print("[green]✓[/green] Test bildirimi gönderildi.")
                else:
                    console.print("[yellow]⚠[/yellow] Bildirim gönderilmedi (notifier disabled veya severity filtreli).")
            return True
        if console:
            console.print("[dim]Kullanım:[/dim] /notify test")
        return True

    if cmd == "/cancel":
        orch.cancel()
        if console:
            console.print("[yellow]⏸[/yellow] İptal flag'i set edildi — bir sonraki iterasyonda durulacak.")
        return True

    if cmd == "/help":
        help_txt = (
            "[bold]Komutlar:[/bold]\n"
            "  /exit, /quit           Çık\n"
            "  /reset                 Sohbet geçmişini sıfırla\n"
            "  /tools                 Aktif MCP tool'larını listele\n"
            "  /sessions              Geçmiş session'ları göster\n"
            "  /budget                Mevcut maliyet özeti\n"
            "  /circuit               Circuit breaker istatistikleri (tool sağlığı)\n"
            "  /cache [clear]         Tool cache istatistikleri / temizle\n"
            "  /plan                  Aktif görev planını göster\n"
            "  /report                💰 Cost-aware session raporu\n"
            "  /health                🏥 MCP server health check\n"
            "  /crashes               Son crash raporlarını göster\n"
            "  /notify test           Webhook notifier'ı test et\n"
            "  /cancel                Mevcut görev turunu iptal et\n"
            "  /models                Akıllı model router tier'larını göster\n"
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
        console.print("\n" + orch.cost_report())
        console.print(f"\n[dim]Session kaydedildi:[/dim] [cyan]{orch.session.id}[/cyan]")
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
        console.print("\n" + orch.cost_report())
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
    # Faz-E yeni özellikler
    p.add_argument("--workflow", default=None, metavar="NAME",
                   help="Workflow yükle (bug-bounty, ctf, supervisor)")
    p.add_argument("--list-workflows", action="store_true",
                   help="Mevcut workflow'ları listele ve çık")
    p.add_argument("--targets", default=None, metavar="FILE",
                   help="Batch mode: dosyadaki her satır için yeni session ile görev çalıştır")
    p.add_argument("--savings-report", action="store_true",
                   help="Tüm geçmiş session'lar için toplam savings raporu ve çık")
    p.add_argument("--health", action="store_true",
                   help="MCP server health check ve çık")
    p.add_argument("--validate-config", action="store_true",
                   help="Config.yaml şemasını doğrula ve çık")
    p.add_argument("--prompt-cache", action="store_true",
                   help="OpenRouter prompt caching (ephemeral) — %%50+ input token tasarrufu")
    p.add_argument("--replay", default=None, metavar="SESSION_ID",
                   help="Eski session'ın user mesajlarını yeni session'da tekrar oynat (regression test)")
    return p


def _cmd_savings_report(console) -> int:
    """Tüm geçmiş session'lar için toplam savings raporu."""
    # Telemetry MCP server'dan değil, doğrudan telemetry SQLite DB'den oku
    # (MCP başlatmak pahalı olur, ayrıca read-only).
    import sqlite3
    import os as _os
    db_path = _os.path.expanduser(
        _os.environ.get("HACKERAGENT_HOME", "~/.hackeragent")
    ) + "/agent_telemetry.db"
    if not _os.path.isfile(db_path):
        if console:
            console.print("[yellow]Telemetry DB yok — henüz hiç session kaydedilmemiş.[/yellow]")
        else:
            print("Telemetry DB bulunamadı.")
        return 1
    try:
        conn = sqlite3.connect(db_path)
        cur = conn.cursor()
        cur.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='savings_events'")
        if not cur.fetchone():
            if console:
                console.print("[yellow]savings_events tablosu yok — henüz event yok.[/yellow]")
            else:
                print("savings_events tablosu yok.")
            return 1
        cur.execute("""
            SELECT event_type, COUNT(*), SUM(cost_usd), SUM(saved_tokens), SUM(saved_usd)
            FROM savings_events GROUP BY event_type
        """)
        rows = cur.fetchall()
        cur.execute("SELECT COUNT(DISTINCT session_id), COUNT(*) FROM savings_events")
        n_sessions, n_events = cur.fetchone()
        conn.close()
    except Exception as e:
        if console:
            console.print(f"[red]✗[/red] DB okunamadı: {e}")
        else:
            print(f"HATA: {e}")
        return 1

    if HAS_RICH and console:
        console.print(f"\n[bold]💰 Agrega Savings Raporu[/bold]  "
                      f"[dim]({n_sessions} session, {n_events} event)[/dim]")
        t = Table(show_lines=False)
        t.add_column("Event", style="cyan")
        t.add_column("Count", justify="right")
        t.add_column("Overhead ($)", justify="right", style="red")
        t.add_column("Saved Tokens", justify="right", style="yellow")
        t.add_column("Saved ($)", justify="right", style="green")
        total_overhead = 0.0
        total_saved = 0.0
        for event_type, cnt, cost, tokens, saved in rows:
            cost = cost or 0.0
            saved = saved or 0.0
            tokens = tokens or 0
            total_overhead += cost
            total_saved += saved
            t.add_row(event_type, str(cnt), f"{cost:.4f}", f"{tokens:,}", f"{saved:.4f}")
        console.print(t)
        net = total_saved - total_overhead
        sign = "+" if net >= 0 else ""
        color = "green" if net >= 0 else "red"
        console.print(
            f"\n[bold]Net fayda:[/bold] [{color}]{sign}${net:.4f}[/{color}]  "
            f"(overhead ${total_overhead:.4f}, tasarruf ${total_saved:.4f})"
        )
    else:
        print(f"\nAgrega Savings Raporu ({n_sessions} session, {n_events} event):")
        for event_type, cnt, cost, tokens, saved in rows:
            print(f"  {event_type:15s} count={cnt:4} cost=${cost or 0:.4f} "
                  f"saved_tokens={tokens or 0:,} saved=${saved or 0:.4f}")
    return 0


def _cmd_batch_targets(orch: Orchestrator, targets_file: str, base_task: str, console) -> int:
    """Batch mode: dosyadaki her satır için yeni session'la görev çalıştır."""
    import os as _os
    if not _os.path.isfile(targets_file):
        if console:
            console.print(f"[red]✗[/red] Targets dosyası bulunamadı: {targets_file}")
        return 1
    targets = [ln.strip() for ln in open(targets_file, encoding="utf-8")
               if ln.strip() and not ln.strip().startswith("#")]
    if not targets:
        if console:
            console.print("[yellow]Targets dosyası boş.[/yellow]")
        return 1

    if console:
        console.print(f"[bold]🎯 Batch mode:[/bold] {len(targets)} hedef işlenecek\n")

    for i, target in enumerate(targets, 1):
        if console:
            console.print(f"\n[bold cyan]━━━ [{i}/{len(targets)}] {target} ━━━[/bold cyan]")
        # Her hedef için yeni session
        if i > 1:
            orch.reset()
        task = f"{base_task}\n\nHedef: {target}" if base_task else f"{target} için güvenlik taraması yap"
        # Target'ı otomatik scope'a ekle (tek IP/domain ise)
        orch.scope.add(target)
        try:
            _run_turn(orch, console, task)
        except Exception as e:
            report_crash("batch_target", extra={"target": target, "index": i}, exc=e)
            if console:
                console.print(f"[red]✗ {target}:[/red] {e}")
            continue

    if console:
        console.print(f"\n[green]✓[/green] Batch tamamlandı: {len(targets)} hedef")
    return 0


def _install_signal_handlers(orch: Orchestrator, console) -> None:
    """SIGINT/SIGTERM'de graceful shutdown — aktif session kaydedilir."""
    def _handler(signum, _frame):
        name = signal.Signals(signum).name
        if console:
            console.print(f"\n[yellow]⏸ {name} alındı, graceful shutdown...[/yellow]")
        else:
            print(f"\n{name} alındı, graceful shutdown...")
        orch.cancel()
        # İkinci SIGINT hard exit
        signal.signal(signum, signal.SIG_DFL)

    for sig in (signal.SIGINT, signal.SIGTERM):
        try:
            signal.signal(sig, _handler)
        except (ValueError, OSError):
            pass  # main thread dışında çağrıldıysa


def main(argv: list[str] | None = None) -> int:
    install_excepthook()
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
    if args.prompt_cache:
        cfg.data.setdefault("llm", {})["prompt_cache_enabled"] = True

    setup_logging(
        level=args.log_level or cfg.get("logging.level", "INFO"),
        file=cfg.get("logging.file"),
    )
    console = Console(stderr=False) if HAS_RICH else None

    # 🔍 Config validation — her zaman; fatal varsa çıkış
    errors, warnings = validate_config(cfg.data)
    if args.validate_config:
        txt = format_validation_result(errors, warnings)
        if console:
            color = "red" if errors else ("yellow" if warnings else "green")
            console.print(f"[{color}]{txt}[/{color}]")
        else:
            print(txt)
        return 1 if errors else 0
    if errors:
        msg = format_validation_result(errors, warnings)
        if console:
            console.print(f"[red]{msg}[/red]\n\n[dim]Fatal config hatası — düzeltip tekrar çalıştırın.[/dim]")
        else:
            print(msg, file=sys.stderr)
        return 2
    if warnings and console:
        console.print(f"[yellow]{format_validation_result([], warnings)}[/yellow]\n")

    # --list-sessions / --list-workflows / --savings-report config/key gerektirmez
    if args.list_sessions:
        _cmd_list_sessions(console)
        return 0
    if args.list_workflows:
        wfs = list_workflows()
        if console:
            if wfs:
                console.print("[bold]Workflow'lar:[/bold]")
                for w in wfs:
                    console.print(f"  • {w}")
            else:
                console.print("[yellow]Workflow bulunamadı.[/yellow]")
        else:
            for w in wfs:
                print(w)
        return 0
    if args.savings_report:
        return _cmd_savings_report(console)

    if not cfg.openrouter_api_key:
        msg = (
            "OPENROUTER_API_KEY ayarlı değil. "
            "Lütfen .env veya ~/.hackeragent/config.yaml içine ekleyin."
        )
        if console:
            console.print(f"[red]✗[/red] {msg}")
        else:
            print(f"HATA: {msg}", file=sys.stderr)
        if not args.list_tools and not args.health:
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

        if args.health:
            import os as _os
            _os.environ.setdefault("OPENROUTER_API_KEY", cfg.openrouter_api_key or "placeholder-for-health")
            cfg.data.setdefault("llm", {})["openrouter_api_key"] = _os.environ["OPENROUTER_API_KEY"]
            orch = Orchestrator(config=cfg)
            try:
                orch.start()
                results = check_health(orch.mcp)
                txt = format_health_report(results)
                if console:
                    unhealthy = sum(1 for r in results.values() if not r["healthy"])
                    color = "red" if unhealthy else "green"
                    console.print(f"[{color}]{txt}[/{color}]")
                else:
                    print(txt)
                return 0 if all(r["healthy"] for r in results.values()) else 1
            finally:
                orch.shutdown()

        orch = Orchestrator(config=cfg)
        orch.progress = _progress_factory(console)
        _install_signal_handlers(orch, console)

        # --workflow? → orchestrator'a yükle
        if args.workflow:
            wf_prompt = load_workflow_prompt(args.workflow)
            if wf_prompt is None:
                if console:
                    console.print(f"[red]✗[/red] Workflow bulunamadı: {args.workflow}")
                    console.print(f"[dim]Mevcut:[/dim] {', '.join(list_workflows())}")
                return 1
            orch.workflow_prompt = wf_prompt
            if console:
                console.print(f"[green]✓[/green] Workflow yüklendi: [cyan]{args.workflow}[/cyan]")

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
            # Replay mode?
            if args.replay:
                from hackeragent.core.replay import extract_user_messages, replay_summary
                try:
                    orig = Session.load(args.replay)
                except FileNotFoundError:
                    if console:
                        console.print(f"[red]✗[/red] Session bulunamadı: {args.replay}")
                    return 1
                if console:
                    console.print(replay_summary(orig))
                    console.print("\n[yellow]⚠ Replay başlatılıyor — LLM + MCP maliyeti olacak.[/yellow]\n")
                users = extract_user_messages(orig)
                if not users:
                    if console:
                        console.print("[yellow]Replay için user mesajı yok.[/yellow]")
                    return 1
                orch.start()
                for i, msg in enumerate(users, 1):
                    if console:
                        console.print(f"\n[bold cyan]━━━ Replay [{i}/{len(users)}] ━━━[/bold cyan]")
                        console.print(f"[dim]USER:[/dim] {msg[:200]}")
                    _run_turn(orch, console, msg)
                if console:
                    console.print(f"\n[green]✓[/green] Replay tamamlandı ({len(users)} tur)")
                    console.print("\n" + orch.cost_report())
                return 0

            # Batch mode?
            if args.targets:
                orch.start()
                return _cmd_batch_targets(orch, args.targets, args.task or "", console)
            if args.task:
                return _run_single(orch, args.task, console)
            return _run_repl(orch, console)
        finally:
            orch.shutdown()
    except KeyboardInterrupt:
        return 130
    except Exception as e:
        report_crash("cli_main", exc=e)
        if console:
            console.print(f"[red]💥 Beklenmeyen hata:[/red] {e}")
            console.print("[dim]Crash raporu yazıldı. `/crashes` ile inceleyebilirsiniz.[/dim]")
        else:
            print(f"HATA: {e}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    sys.exit(main())
