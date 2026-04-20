"""Vision / multimodal desteği — browser_screenshot sonuçlarını LLM'e image olarak gönder.

`browser.browser_screenshot` JSON string döndürür ve içinde `base64` alanı var.
Normalde bu raw JSON LLM'e text olarak gider → LLM image'ı "göremez".

Bu modül:
  1. Tool sonucunun multimodal image içerip içermediğini tespit eder
  2. İçeriyorsa session'a eklenen `tool` mesajını OpenAI multimodal formatına çevirir:
       content: [
         {"type": "text", "text": "<özet>"},
         {"type": "image_url", "image_url": {"url": "data:image/png;base64,..."}}
       ]
  3. Vision-desteklemeyen model seçildiğinde otomatik olarak DEVRE DIŞI kalır
     (model adına bakılır)

Vision destekleyen OpenRouter modelleri (2026 Q1):
  • anthropic/claude-3.5-sonnet, claude-3.5-haiku, claude-3-opus
  • openai/gpt-4o, gpt-4o-mini, gpt-5-*
  • google/gemini-2.5-*, gemini-3-*
  • qwen/qwen-2.5-vl-*, qwen-vl-plus, qwen-3-vl
  • meta-llama/llama-3.2-90b-vision-*
"""

from __future__ import annotations

import json
import re

from hackeragent.utils.logger import get_logger

log = get_logger(__name__)

# Model adı → vision destekliyor mu (best-effort pattern)
_VISION_MODEL_PATTERNS = [
    r"claude-3",          # 3-opus, 3.5-sonnet, 3.5-haiku — hepsi vision
    r"gpt-4o",
    r"gpt-5",             # GPT-5 ailesi
    r"gpt-image",
    r"gemini-[12]\.",     # gemini-1.5, gemini-2.x
    r"gemini-3",
    r"qwen.*-vl",
    r"vision",            # generic keyword
    r"llama-3\.2.*vision",
]
_VISION_RE = re.compile("|".join(_VISION_MODEL_PATTERNS), re.IGNORECASE)


def model_supports_vision(model: str) -> bool:
    return bool(_VISION_RE.search(model or ""))


def extract_image_from_tool_result(result: str) -> tuple[str | None, str]:
    """Tool sonucundan (browser_screenshot) base64 image + özet metni çıkar.

    Returns: (data_url or None, summary_text)
    """
    if not result or not isinstance(result, str):
        return None, result or ""
    trimmed = result.lstrip()
    if not trimmed.startswith("{"):
        return None, result
    try:
        data = json.loads(trimmed)
    except json.JSONDecodeError:
        return None, result
    if not isinstance(data, dict):
        return None, result

    data_url = data.get("data_url")
    if not data_url or not isinstance(data_url, str) or not data_url.startswith("data:image/"):
        return None, result

    # Image var — summary üret (base64'ü çıkararak)
    summary_parts = []
    if data.get("url"):
        summary_parts.append(f"URL: {data['url']}")
    if data.get("title"):
        summary_parts.append(f"Başlık: {data['title']}")
    if data.get("size_bytes"):
        summary_parts.append(f"Boyut: {data['size_bytes']} bytes")
    if data.get("path"):
        summary_parts.append(f"Yerel dosya: {data['path']}")
    summary_parts.append("(Ekran görüntüsü image olarak ekte — analiz edebilirsin)")
    summary = "\n".join(summary_parts)
    return data_url, summary


def to_multimodal_tool_message(
    tool_call_id: str,
    raw_result: str,
    enabled: bool = True,
) -> dict:
    """tool_call sonucunu multimodal format'a çevir (image varsa).

    Image yoksa veya disabled ise plain-text tool message döner.
    """
    if not enabled:
        return {
            "role": "tool",
            "tool_call_id": tool_call_id,
            "content": raw_result,
        }

    data_url, summary = extract_image_from_tool_result(raw_result)
    if not data_url:
        return {
            "role": "tool",
            "tool_call_id": tool_call_id,
            "content": raw_result,
        }

    log.info("Tool sonucu multimodal image içeriyor → LLM'e data_url ile gönderiliyor")
    return {
        "role": "tool",
        "tool_call_id": tool_call_id,
        "content": [
            {"type": "text", "text": summary},
            {"type": "image_url", "image_url": {"url": data_url}},
        ],
    }
