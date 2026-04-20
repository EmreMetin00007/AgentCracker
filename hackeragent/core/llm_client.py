"""OpenRouter API client.

OpenAI-uyumlu chat completion endpoint'ini kullanır (OpenRouter = OpenAI API
proxy'si). Tool/function calling desteği OpenAI şemasıyla aynıdır.

Kullanım:
    client = LLMClient(api_key=..., model="qwen/qwen3.6-plus")
    reply = client.chat(messages, tools=[...])
"""

from __future__ import annotations

import json
import time
from dataclasses import dataclass
from typing import Any

import requests

from hackeragent.utils.logger import get_logger

log = get_logger(__name__)


@dataclass
class LLMReply:
    """LLM yanıtının yapılandırılmış hali."""

    content: str = ""
    tool_calls: list[dict] = None  # type: ignore
    finish_reason: str = ""
    usage: dict = None  # type: ignore
    raw: dict = None  # type: ignore

    def has_tool_calls(self) -> bool:
        return bool(self.tool_calls)


class LLMClient:
    """Thin OpenRouter client (OpenAI-compatible chat completions)."""

    def __init__(
        self,
        api_key: str,
        model: str = "qwen/qwen3.6-plus",
        base_url: str = "https://openrouter.ai/api/v1",
        timeout: int = 120,
        max_tokens: int = 4096,
        temperature: float = 0.3,
    ):
        if not api_key:
            raise ValueError(
                "OpenRouter API key boş. OPENROUTER_API_KEY env var'ını ayarlayın "
                "veya ~/.hackeragent/config.yaml içine llm.openrouter_api_key ekleyin."
            )
        self.api_key = api_key
        self.model = model
        self.base_url = base_url.rstrip("/")
        self.timeout = timeout
        self.max_tokens = max_tokens
        self.temperature = temperature

    def _headers(self) -> dict:
        return {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json",
            "HTTP-Referer": "https://hackeragent.local",
            "X-Title": "HackerAgent Orchestrator",
        }

    def chat(
        self,
        messages: list[dict],
        tools: list[dict] | None = None,
        model: str | None = None,
        max_tokens: int | None = None,
        temperature: float | None = None,
        retries: int = 2,
    ) -> LLMReply:
        """Tek turlu chat completion. Tool kullanacaksa `tools` gönderin."""
        payload: dict[str, Any] = {
            "model": model or self.model,
            "messages": messages,
            "max_tokens": max_tokens or self.max_tokens,
            "temperature": self.temperature if temperature is None else temperature,
        }
        if tools:
            payload["tools"] = tools
            payload["tool_choice"] = "auto"

        url = f"{self.base_url}/chat/completions"
        last_err: Exception | None = None

        for attempt in range(retries + 1):
            try:
                log.debug("LLM call: model=%s tools=%d msgs=%d", payload["model"], len(tools or []), len(messages))
                resp = requests.post(url, headers=self._headers(), json=payload, timeout=self.timeout)
                if resp.status_code == 429:
                    wait = 2 ** attempt
                    log.warning("Rate limited (429), %ss bekleniyor", wait)
                    time.sleep(wait)
                    continue
                resp.raise_for_status()
                data = resp.json()
                return self._parse(data)
            except requests.exceptions.HTTPError as e:
                last_err = e
                log.error("HTTP %s from OpenRouter: %s", resp.status_code, resp.text[:500])
                if resp.status_code in (400, 401, 402, 404):
                    break  # retry'dan fayda yok
                time.sleep(1 + attempt)
            except (requests.exceptions.Timeout, requests.exceptions.ConnectionError) as e:
                last_err = e
                log.warning("Network error (attempt %d): %s", attempt + 1, e)
                time.sleep(1 + attempt)
            except Exception as e:
                last_err = e
                log.exception("Unexpected LLM error: %s", e)
                break

        raise RuntimeError(f"LLM call failed after {retries + 1} attempts: {last_err}")

    @staticmethod
    def _parse(data: dict) -> LLMReply:
        try:
            choice = data["choices"][0]
            msg = choice.get("message", {})
            tool_calls_raw = msg.get("tool_calls") or []
            # OpenAI schema: [{id, type:"function", function:{name, arguments}}]
            tool_calls = []
            for tc in tool_calls_raw:
                fn = tc.get("function", {})
                args_raw = fn.get("arguments", "{}")
                try:
                    args = json.loads(args_raw) if isinstance(args_raw, str) else args_raw
                except json.JSONDecodeError:
                    args = {"_raw": args_raw}
                tool_calls.append({
                    "id": tc.get("id", ""),
                    "name": fn.get("name", ""),
                    "arguments": args,
                })
            return LLMReply(
                content=msg.get("content") or "",
                tool_calls=tool_calls,
                finish_reason=choice.get("finish_reason", ""),
                usage=data.get("usage") or {},
                raw=data,
            )
        except (KeyError, IndexError, TypeError) as e:
            raise RuntimeError(f"Malformed LLM response: {e} | data={data}")
