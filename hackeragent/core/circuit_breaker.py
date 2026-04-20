"""Circuit breaker — tool başarısızlıklarını izler ve kısa süreli "soğutma" uygular.

Her qualified tool (`<server>__<tool>`) için başarısızlık sayacı tutar. Eşik
aşılırsa (varsayılan: 3 ardışık fail) tool belirli bir süre (varsayılan: 60s)
bloklanır; bu sürede tool çağrıları LLM'e "circuit open" mesajı olarak döner
ve LLM başka bir yaklaşım dener.

Ayrıca `server_restart_callback` ile MCP server'ın çökmüş olabileceği durumlarda
MCPManager'dan sunucuyu yeniden başlatmasını isteyebilir.
"""

from __future__ import annotations

import time
from dataclasses import dataclass, field

from hackeragent.utils.logger import get_logger

log = get_logger(__name__)


@dataclass
class _ToolState:
    consecutive_failures: int = 0
    open_until: float = 0.0  # epoch seconds
    last_error: str = ""
    total_calls: int = 0
    total_failures: int = 0


class CircuitBreaker:
    """Per-tool failure tracker + short cooldown."""

    def __init__(
        self,
        failure_threshold: int = 3,
        cooldown_seconds: int = 60,
        restart_server_after: int = 5,
    ):
        self.failure_threshold = failure_threshold
        self.cooldown_seconds = cooldown_seconds
        self.restart_server_after = restart_server_after
        self.states: dict[str, _ToolState] = {}
        # server_failure_counts[server] = kaç tool içinde toplamda ardışık fail
        self.server_failure_counts: dict[str, int] = {}

    def is_open(self, tool_qname: str) -> tuple[bool, str]:
        """(open, reason). Open = bu çağrı yapılmamalı."""
        state = self.states.get(tool_qname)
        if not state:
            return False, ""
        now = time.time()
        if state.open_until > now:
            remaining = int(state.open_until - now)
            return True, (
                f"⚡ CIRCUIT OPEN: '{tool_qname}' son {state.consecutive_failures} "
                f"çağrıda başarısız oldu. {remaining}s sonra tekrar denenebilir. "
                f"Son hata: {state.last_error[:200]}. "
                f"Bu sürede farklı bir yaklaşım/araç deneyin."
            )
        return False, ""

    def record_success(self, tool_qname: str) -> None:
        state = self.states.setdefault(tool_qname, _ToolState())
        state.total_calls += 1
        state.consecutive_failures = 0
        state.open_until = 0.0

    def record_failure(self, tool_qname: str, error: str) -> bool:
        """Başarısızlık kaydet. True dönerse server restart tavsiye edilir."""
        state = self.states.setdefault(tool_qname, _ToolState())
        state.total_calls += 1
        state.total_failures += 1
        state.consecutive_failures += 1
        state.last_error = error[:500]

        if state.consecutive_failures >= self.failure_threshold:
            state.open_until = time.time() + self.cooldown_seconds
            log.warning(
                "Circuit OPENED for '%s' (%d ardışık fail). %ds cooldown.",
                tool_qname, state.consecutive_failures, self.cooldown_seconds,
            )

        # Server-wide sayaç
        server = tool_qname.split("__", 1)[0] if "__" in tool_qname else tool_qname
        self.server_failure_counts[server] = self.server_failure_counts.get(server, 0) + 1
        should_restart = self.server_failure_counts[server] >= self.restart_server_after
        if should_restart:
            self.server_failure_counts[server] = 0  # reset
        return should_restart

    def stats(self) -> dict:
        return {
            qn: {
                "total_calls": s.total_calls,
                "total_failures": s.total_failures,
                "consecutive": s.consecutive_failures,
                "open": time.time() < s.open_until,
            }
            for qn, s in self.states.items()
        }
