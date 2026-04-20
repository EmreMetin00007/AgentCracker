"""Planlayıcı — kullanıcı görevini adımlara böler.

Tek bir ucuz LLM çağrısıyla görevi yapılandırılmış plana çevirir:
  [
    {step: 1, goal: "recon", expected_tools: ["nmap", "subdomain_enum"]},
    {step: 2, goal: "web_discovery", ...},
    ...
  ]

Executor (Orchestrator.ask) sonra bu planı system mesajı olarak enjekte eder.
LLM, her turda planın hangi adımında olduğunu bilerek daha odaklı ilerler.

Heuristik: Plan çağrısı SADECE görev "kompleks" göründüğünde yapılır
(uzunluk > 40 karakter VEYA birden fazla fiil/hedef içeriyor). Kısa sohbet
ya da basit komutlar için plan yapılmaz (zaten tek tur bitiyor).
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass

from hackeragent.core.llm_client import LLMClient
from hackeragent.utils.logger import get_logger

log = get_logger(__name__)

# Planner trigger'ı — bu desenler complex görev sinyali
_COMPLEX_HINT = re.compile(
    r"\b(tara|scan|exploit|test|analiz|enumerate|keşf|penetration|bug bounty|"
    r"pentest|writeup|rapor|kapsamlı|comprehensive|attack chain|kill chain|"
    r"ctf|challenge|full|complete)\b",
    re.IGNORECASE,
)


@dataclass
class PlanStep:
    step: int
    goal: str
    expected_tools: list[str]
    success_criteria: str = ""

    def to_dict(self) -> dict:
        return {
            "step": self.step,
            "goal": self.goal,
            "expected_tools": self.expected_tools,
            "success_criteria": self.success_criteria,
        }


@dataclass
class Plan:
    task: str
    steps: list[PlanStep]
    raw_reasoning: str = ""

    def is_empty(self) -> bool:
        return not self.steps

    def to_system_message(self) -> str:
        """LLM'e enjekte edilecek system mesajı formatı."""
        lines = [
            "📋 GÖREV PLANI (planner tarafından üretildi — izlenmesi önerilir)",
            f"Ana Hedef: {self.task}",
            "",
        ]
        for s in self.steps:
            tools = ", ".join(s.expected_tools) if s.expected_tools else "serbest"
            lines.append(f"  Adım {s.step}. {s.goal}")
            lines.append(f"     Araçlar: {tools}")
            if s.success_criteria:
                lines.append(f"     Başarı: {s.success_criteria}")
        lines.append("")
        lines.append(
            "Her adımı sırayla gerçekleştir. Adımı bitirince kısaca özetle, "
            "ardından sonraki adıma geç. Plan dışı iş yapma — eğer zorunlu "
            "yeni adım çıkarsa önce 'Plan değişikliği:' diye belirt."
        )
        return "\n".join(lines)


def is_complex_task(user_input: str) -> bool:
    """Planner tetiklenmeli mi?"""
    if not user_input:
        return False
    if len(user_input) < 40:
        return False
    if _COMPLEX_HINT.search(user_input):
        return True
    # Uzun ve birden fazla fiil → kompleks
    word_count = len(user_input.split())
    return word_count >= 15


class Planner:
    """Ucuz LLM ile görevi adımlara böler."""

    def __init__(
        self,
        llm: LLMClient,
        cheap_model: str | None = None,
        enabled: bool = True,
        max_steps: int = 6,
    ):
        self.llm = llm
        self.cheap_model = cheap_model
        self.enabled = enabled
        self.max_steps = max_steps

    def plan(self, user_input: str, available_tools: list[str] | None = None) -> Plan | None:
        """Görev için plan üret. Başarısızsa None dön."""
        if not self.enabled or not is_complex_task(user_input):
            return None

        tools_hint = ""
        if available_tools:
            sample = ", ".join(available_tools[:30])
            tools_hint = f"\nMevcut tool örnekleri: {sample}" + (
                " ..." if len(available_tools) > 30 else ""
            )

        prompt = [
            {
                "role": "system",
                "content": (
                    "Sen bir saldırgan pentest ajanın planlayıcısısın. "
                    "Kullanıcı görevini SIRALI adımlara böl. Sadece "
                    "geçerli JSON döndür (açıklama yok, markdown yok, sadece JSON):\n\n"
                    "{\n"
                    '  "steps": [\n'
                    '    {"step": 1, "goal": "...", "expected_tools": ["..."], "success_criteria": "..."},\n'
                    "    ...\n"
                    "  ]\n"
                    "}\n\n"
                    f"KURAL: En fazla {self.max_steps} adım. Her adım konkret ve "
                    "ölçülebilir olsun. 'recon → discovery → exploit → post-exploit → "
                    "report' sırasına uy. Tool adlarını gerçek MCP adlarıyla yaz."
                    + tools_hint
                ),
            },
            {"role": "user", "content": user_input},
        ]

        try:
            reply = self.llm.chat(
                messages=prompt,
                tools=None,
                model=self.cheap_model,
                max_tokens=1000,
                temperature=0.2,
            )
        except Exception as e:
            log.warning("Planner LLM çağrı hatası: %s", e)
            return None

        plan = _parse_plan_reply(user_input, reply.content or "")
        if plan and plan.steps:
            log.info("Plan oluşturuldu: %d adım", len(plan.steps))
            return plan
        log.debug("Plan parse edilemedi, atlanıyor")
        return None


def _parse_plan_reply(task: str, raw: str) -> Plan | None:
    """LLM yanıtından JSON plan'ı çıkar."""
    raw = raw.strip()
    if not raw:
        return None

    # Bazen LLM ```json blokla sarar — temizle
    if raw.startswith("```"):
        raw = raw.split("```", 2)[1] if "```" in raw[3:] else raw[3:]
        if raw.lstrip().lower().startswith("json"):
            raw = raw.lstrip()[4:]
        raw = raw.rstrip("`").strip()

    # Bazı yanıtlarda ilk { öncesi bir açıklama olabilir
    first_brace = raw.find("{")
    last_brace = raw.rfind("}")
    if first_brace >= 0 and last_brace > first_brace:
        raw = raw[first_brace:last_brace + 1]

    try:
        data = json.loads(raw)
    except json.JSONDecodeError as e:
        log.debug("Plan JSON parse edilemedi: %s | raw[:200]=%s", e, raw[:200])
        return None

    steps_raw = data.get("steps") if isinstance(data, dict) else None
    if not isinstance(steps_raw, list) or not steps_raw:
        return None

    steps: list[PlanStep] = []
    for idx, s in enumerate(steps_raw, 1):
        if not isinstance(s, dict):
            continue
        tools = s.get("expected_tools") or []
        if not isinstance(tools, list):
            tools = []
        steps.append(PlanStep(
            step=int(s.get("step", idx)),
            goal=str(s.get("goal", "")).strip()[:200],
            expected_tools=[str(t).strip()[:100] for t in tools][:10],
            success_criteria=str(s.get("success_criteria", "")).strip()[:200],
        ))

    return Plan(task=task, steps=steps, raw_reasoning=raw[:500]) if steps else None
