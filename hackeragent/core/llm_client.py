"""OpenRouter API client.

OpenAI-uyumlu chat completion endpoint'ini kullanır (OpenRouter = OpenAI API
proxy'si). Tool/function calling desteği OpenAI şemasıyla aynıdır.

Kullanım:
    client = LLMClient(api_key=..., model="qwen/qwen3.6-plus")
    reply = client.chat(messages, tools=[...])
    for chunk in client.chat_stream(messages, tools=[...]): ...
"""

from __future__ import annotations

import json
import re
import time
from dataclasses import dataclass, field
from typing import Any, Iterator

import requests

from hackeragent.utils.logger import get_logger

log = get_logger(__name__)

# OpenRouter 404 "No endpoints found that support tool use" hata mesajında
# problematik tool adını yakalar: Try disabling "kali-tools__parallel_recon"
# resp.text JSON olduğundan quote'lar \" olarak escape'li gelir — her iki format
# (raw quote veya escape'li) için de eşleştir.
_NO_ENDPOINTS_RE = re.compile(
    r'No endpoints found.*?Try disabling \\?"([^"\\]+)\\?"',
    re.IGNORECASE | re.DOTALL,
)


def _extract_bad_tool(err_text: str) -> str | None:
    m = _NO_ENDPOINTS_RE.search(err_text or "")
    return m.group(1) if m else None


def _drop_tool(tools: list[dict], bad_name: str) -> list[dict]:
    return [t for t in tools if (t.get("function") or {}).get("name") != bad_name]


def _apply_prompt_cache(messages: list[dict]) -> list[dict]:
    """OpenRouter / Anthropic prompt caching hint'i ekle.

    Stabil olan ilk system mesajını (ve varsa ikinci system mesajını) "ephemeral"
    cache hint'i ile işaretler. OpenRouter bu hint'i destekleyen provider'lara
    otomatik iletir (Anthropic, OpenAI o1+, Gemini cache API) → 5dk cache,
    %50+ input token tasarrufu.

    Format:
      {"role": "system", "content": [
         {"type": "text", "text": "...", "cache_control": {"type": "ephemeral"}}
      ]}
    """
    if not messages:
        return messages
    out: list[dict] = []
    marked = 0
    for msg in messages:
        # Sadece ilk iki system mesajını cache'le (stabil olanlar)
        if marked < 2 and msg.get("role") == "system":
            content = msg.get("content")
            if isinstance(content, str) and content:
                out.append({
                    "role": "system",
                    "content": [
                        {
                            "type": "text",
                            "text": content,
                            "cache_control": {"type": "ephemeral"},
                        }
                    ],
                })
                marked += 1
                continue
        out.append(msg)
    return out


@dataclass
class LLMReply:
    """LLM yanıtının yapılandırılmış hali."""

    content: str = ""
    tool_calls: list[dict] = field(default_factory=list)
    finish_reason: str = ""
    usage: dict = field(default_factory=dict)
    cost_usd: float = 0.0
    raw: dict = field(default_factory=dict)

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
        retries: int = 3,
        prompt_cache: bool = False,
    ) -> LLMReply:
        """Tek turlu chat completion. Tool kullanacaksa `tools` gönderin.

        prompt_cache=True iken system mesajına OpenRouter/Anthropic
        `cache_control: ephemeral` işareti konur → 5dk cache (%50+ input
        token tasarrufu). Sadece system prompt + tools schema stabilse
        faydalıdır.
        """
        payload_messages = _apply_prompt_cache(messages) if prompt_cache else messages
        payload: dict[str, Any] = {
            "model": model or self.model,
            "messages": payload_messages,
            "max_tokens": max_tokens or self.max_tokens,
            "temperature": self.temperature if temperature is None else temperature,
        }
        if tools:
            payload["tools"] = tools
            payload["tool_choice"] = "auto"
            # OpenRouter provider routing — tool use destekleyen provider'a zorla.
            # Bu, "No endpoints found that support tool use" 404 hatasını önler
            # (bazı Qwen provider'ları structured outputs/tool calling desteklemiyor).
            payload["provider"] = {"require_parameters": True}

        url = f"{self.base_url}/chat/completions"
        last_err: Exception | None = None
        active_tools = list(tools) if tools else None
        dropped_tools: list[str] = []
        # Tool drop işlemleri retry sayılmaz — gerçek network hatası için ayrı counter
        # Max 50 tool drop (fazlası sonsuz döngü olur)
        max_tool_drops = 50
        network_attempts = 0

        while network_attempts <= retries:
            try:
                log.debug("LLM call: model=%s tools=%d msgs=%d",
                          payload["model"], len(active_tools or []), len(messages))
                if active_tools is not None:
                    payload["tools"] = active_tools
                resp = requests.post(url, headers=self._headers(), json=payload, timeout=self.timeout)
                if resp.status_code == 429:
                    wait = 2 ** network_attempts
                    log.warning("Rate limited (429), %ss bekleniyor", wait)
                    time.sleep(wait)
                    network_attempts += 1
                    continue
                resp.raise_for_status()
                data = resp.json()
                return self._parse(data)
            except requests.exceptions.HTTPError as e:
                last_err = e
                log.error("HTTP %s from OpenRouter: %s", resp.status_code, resp.text[:500])
                # 404 "No endpoints found that support tool use" → problematik tool'u
                # parse edip exclude et ve retry yap (graceful degradation).
                # Bu retry NETWORK retry sayılmaz — tool sayısı azalana kadar devam.
                if resp.status_code == 404 and active_tools:
                    bad = _extract_bad_tool(resp.text)
                    if bad and bad not in dropped_tools and len(dropped_tools) < max_tool_drops:
                        active_tools = _drop_tool(active_tools, bad)
                        dropped_tools.append(bad)
                        log.warning(
                            "Tool '%s' provider tarafından reddedildi → exclude ederek retry "
                            "(kalan tool: %d)", bad, len(active_tools),
                        )
                        # Akıllı fallback: 10+ tool drop olduysa, provider zaten bu
                        # model için tool use desteklemiyor demektir. Tools'suz metin-
                        # sadece mode'a geç — sonsuz drop chain'inden çık.
                        if len(dropped_tools) >= 10:
                            log.warning(
                                "10+ tool reddedildi → provider tool use desteklemiyor, "
                                "tools'suz text-only fallback'e geçiliyor"
                            )
                            active_tools = None
                            payload.pop("tools", None)
                            payload.pop("tool_choice", None)
                            payload.pop("provider", None)
                        continue  # network_attempts artmıyor
                    # Tool drop edemezsek tool_choice="none" ile metin-sadece fallback
                    if not dropped_tools or active_tools:
                        log.warning("Tool-capable provider bulunamadı → tools'suz retry")
                        active_tools = None
                        payload.pop("tools", None)
                        payload.pop("tool_choice", None)
                        payload.pop("provider", None)
                        network_attempts += 1
                        continue
                if resp.status_code in (400, 401, 402, 404):
                    break  # retry'dan fayda yok
                time.sleep(1 + network_attempts)
                network_attempts += 1
            except (requests.exceptions.Timeout, requests.exceptions.ConnectionError) as e:
                last_err = e
                log.warning("Network error (attempt %d): %s", network_attempts + 1, e)
                time.sleep(1 + network_attempts)
                network_attempts += 1
            except Exception as e:
                last_err = e
                log.exception("Unexpected LLM error: %s", e)
                break

        raise RuntimeError(
            f"LLM call failed after {network_attempts} network attempts "
            f"({len(dropped_tools)} tool dropped): {last_err}"
        )

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
            usage = data.get("usage") or {}
            return LLMReply(
                content=msg.get("content") or "",
                tool_calls=tool_calls,
                finish_reason=choice.get("finish_reason", ""),
                usage=usage,
                cost_usd=float(usage.get("cost", 0.0) or 0.0),
                raw=data,
            )
        except (KeyError, IndexError, TypeError) as e:
            raise RuntimeError(f"Malformed LLM response: {e} | data={data}")

    # ─── Streaming ────────────────────────────────────────────────────────
    def chat_stream(
        self,
        messages: list[dict],
        tools: list[dict] | None = None,
        model: str | None = None,
        max_tokens: int | None = None,
        temperature: float | None = None,
        prompt_cache: bool = False,
    ) -> Iterator[dict]:
        """Token-by-token streaming.

        Yield format (iki event tipi):
          {"type": "delta", "content": "...parça..."}          # yazılacak metin
          {"type": "done", "reply": LLMReply}                   # final LLMReply
        """
        payload_messages = _apply_prompt_cache(messages) if prompt_cache else messages
        payload: dict[str, Any] = {
            "model": model or self.model,
            "messages": payload_messages,
            "max_tokens": max_tokens or self.max_tokens,
            "temperature": self.temperature if temperature is None else temperature,
            "stream": True,
            "usage": {"include": True},  # OpenRouter stream'e usage.cost ekler
        }
        if tools:
            payload["tools"] = tools
            payload["tool_choice"] = "auto"
            # Tool use destekleyen provider'a yönlendir (404 "No endpoints" önlemi)
            payload["provider"] = {"require_parameters": True}

        url = f"{self.base_url}/chat/completions"
        content_buf: list[str] = []
        # tool_calls partial — OpenAI delta format: [{index, id?, function:{name?, arguments?}}]
        tool_calls_partial: dict[int, dict] = {}
        usage: dict = {}
        finish_reason: str = ""

        try:
            with requests.post(
                url, headers=self._headers(), json=payload, timeout=self.timeout, stream=True
            ) as resp:
                resp.raise_for_status()
                # iter_lines yerine byte-level buffer — UTF-8 multi-byte güvenli
                buf = bytearray()
                for chunk in resp.iter_content(chunk_size=None, decode_unicode=False):
                    if not chunk:
                        continue
                    buf.extend(chunk)
                    while b"\n" in buf:
                        raw_line_bytes, _, rest = buf.partition(b"\n")
                        buf = bytearray(rest)
                        try:
                            line = raw_line_bytes.decode("utf-8").strip()
                        except UnicodeDecodeError:
                            # Nadir durum: satır bile UTF-8 parçalanmış; ham olarak atla
                            continue
                        if not line or line.startswith(":"):
                            continue
                        if not line.startswith("data: "):
                            continue
                        data_str = line[6:]
                        if data_str == "[DONE]":
                            buf = bytearray()
                            break
                        try:
                            chunk_data = json.loads(data_str)
                        except json.JSONDecodeError:
                            continue

                        choices = chunk_data.get("choices") or []
                        if choices:
                            delta = choices[0].get("delta") or {}
                            if delta.get("content"):
                                content_buf.append(delta["content"])
                                yield {"type": "delta", "content": delta["content"]}

                            for tc_delta in delta.get("tool_calls") or []:
                                idx = tc_delta.get("index", 0)
                                slot = tool_calls_partial.setdefault(
                                    idx, {"id": "", "name": "", "arguments_raw": ""}
                                )
                                if tc_delta.get("id"):
                                    slot["id"] = tc_delta["id"]
                                fn = tc_delta.get("function") or {}
                                if fn.get("name"):
                                    slot["name"] = fn["name"]
                                if fn.get("arguments"):
                                    slot["arguments_raw"] += fn["arguments"]

                            if choices[0].get("finish_reason"):
                                finish_reason = choices[0]["finish_reason"]

                        if chunk_data.get("usage"):
                            usage = chunk_data["usage"]
        except requests.exceptions.RequestException as e:
            raise RuntimeError(f"LLM stream failed: {e}")

        # Partial tool_calls'ı finalize et
        final_tool_calls: list[dict] = []
        for idx in sorted(tool_calls_partial.keys()):
            slot = tool_calls_partial[idx]
            try:
                args = json.loads(slot["arguments_raw"]) if slot["arguments_raw"] else {}
            except json.JSONDecodeError:
                args = {"_raw": slot["arguments_raw"]}
            final_tool_calls.append({
                "id": slot["id"] or f"call_{idx}",
                "name": slot["name"],
                "arguments": args,
            })

        reply = LLMReply(
            content="".join(content_buf),
            tool_calls=final_tool_calls,
            finish_reason=finish_reason,
            usage=usage,
            cost_usd=float(usage.get("cost", 0.0) or 0.0),
            raw={"streamed": True},
        )
        yield {"type": "done", "reply": reply}
