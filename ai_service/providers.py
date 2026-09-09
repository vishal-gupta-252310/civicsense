"""Official per-provider LLM request builders.

Builds the exact request each LLM provider documents for its own chat API and
parses the provider's native response shape, instead of relying on a generic
multi-provider translation layer whose one-size-fits-all payload (e.g. a single
"reasoning_effort" key in ``extra_body``) silently breaks on providers that use
a different schema.

Native shapes used here (from each provider's API reference):
  * OpenAI-schema providers (Groq, OpenRouter, OpenAI, Mistral, DeepSeek,
    Together): ``messages`` + ``max_tokens``/``max_completion_tokens`` +
    ``response_format={"type": "json_object"}``; each controls reasoning with
    its own documented field.
  * Google Gemini: ``contents``/``parts``, ``systemInstruction``, and
    ``generationConfig.maxOutputTokens`` (not ``max_tokens``) plus
    ``responseMimeType: "application/json"`` and ``thinkingConfig``.
  * Anthropic: ``POST /v1/messages``, top-level ``system`` (no "system" role),
    required ``max_tokens``, ``x-api-key`` + ``anthropic-version`` headers.
"""

import re

# Stored model ids carry a provider prefix (kept from the LiteLLM era) so the
# settings dropdown can show where a model lives; strip it before use.
PREFIXES = {
    "groq": "groq/",
    "gemini": "gemini/",
    "openrouter": "openrouter/",
    "openai": "openai/",
    "anthropic": "anthropic/",
    "mistral": "mistral/",
    "deepseek": "deepseek/",
    "together": "together_ai/",
}

_PREFIX_TO_PLATFORM = {pfx: platform for platform, pfx in PREFIXES.items()}

# The provider-specific "disable thinking" knob is only sent to reasoning-
# capable models, so plain chat models never see an unsupported parameter.
_REASONING_MODEL = re.compile(
    r"reason|thinking|qwen3|qwen-?3|qwq|deepseek|r1|kimi|glm-4|\bo[3-5]\b|gpt-5",
    re.IGNORECASE,
)

_OPENAI_URLS = {
    "groq": "https://api.groq.com/openai/v1/chat/completions",
    "openrouter": "https://openrouter.ai/api/v1/chat/completions",
    "openai": "https://api.openai.com/v1/chat/completions",
    "mistral": "https://api.mistral.ai/v1/chat/completions",
    "deepseek": "https://api.deepseek.com/chat/completions",
    "together": "https://api.together.xyz/v1/chat/completions",
}

_ANTHROPIC_URL = "https://api.anthropic.com/v1/messages"

_GEMINI_URL = "https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent"


class UnknownPlatformError(ValueError):
    pass


def resolve(platform, model):
    """Return ``(platform, raw_model_id)`` honoring a stored provider prefix.

    ``platform`` (from the calling app) wins; otherwise the prefix on the model
    id is used, which covers environment-configured models like
    ``gemini/gemini-3.6-flash``.
    """
    model = (model or "").strip()
    if platform in PREFIXES:
        prefix = PREFIXES[platform]
        if model.startswith(prefix):
            model = model[len(prefix):].strip() or model
        return platform, model
    for prefix, known in _PREFIX_TO_PLATFORM.items():
        if model.startswith(prefix):
            return known, model[len(prefix):].strip() or model
    return platform or "", model


def _reasoning_control(platform, model):
    """Official per-provider reasoning control, only for reasoning models."""
    if not _REASONING_MODEL.search(model):
        return {}
    if platform == "groq":
        return {"reasoning_effort": "none"}
    if platform == "mistral":
        return {"reasoning_effort": "none"}
    if platform == "deepseek":
        return {"reasoning_effort": "low"}
    if platform == "together":
        return {"reasoning": {"enabled": False}}
    if platform == "openrouter":
        return {"reasoning": {"effort": "none"}}
    if platform == "openai":
        return {"reasoning_effort": "minimal"}
    return {}


def build_request(platform, model, api_key, system_prompt, user_prompt, max_tokens=400):
    """Return ``(url, headers, body)`` for the provider's documented chat API."""
    if platform == "gemini":
        config = {
            "temperature": 0,
            "maxOutputTokens": max_tokens,
            "responseMimeType": "application/json",
        }
        if _REASONING_MODEL.search(model):
            config["thinkingConfig"] = {"thinkingBudget": 0}
        body = {
            "contents": [{"parts": [{"text": user_prompt}]}],
            "systemInstruction": {"parts": [{"text": system_prompt}]},
            "generationConfig": config,
        }
        return (
            _GEMINI_URL.format(model=model),
            {"x-goog-api-key": api_key, "Content-Type": "application/json"},
            body,
        )

    if platform == "anthropic":
        body = {
            "model": model,
            "max_tokens": max_tokens,
            "temperature": 0,
            "system": system_prompt,
            "messages": [{"role": "user", "content": user_prompt}],
        }
        headers = {
            "x-api-key": api_key,
            "anthropic-version": "2023-06-01",
            "Content-Type": "application/json",
        }
        return _ANTHROPIC_URL, headers, body

    if platform not in _OPENAI_URLS:
        raise UnknownPlatformError(f"Unsupported platform: {platform}")

    body = {
        "model": model,
        "messages": [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_prompt},
        ],
        "temperature": 0,
        "response_format": {"type": "json_object"},
        **_reasoning_control(platform, model),
    }
    # OpenAI prefers max_completion_tokens; the rest use max_tokens natively.
    body["max_completion_tokens" if platform == "openai" else "max_tokens"] = max_tokens
    headers = {"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"}
    if platform == "openrouter":
        headers["X-Title"] = "CivicSense"
    return _OPENAI_URLS[platform], headers, body


def extract_response(platform, data):
    """Return ``(content_text, truncated)`` from a provider's native response."""
    if platform == "gemini":
        candidates = data.get("candidates") or []
        if not candidates:
            return "", False
        parts = candidates[0].get("content", {}).get("parts") or []
        text = "".join(part.get("text", "") for part in parts if part.get("text"))
        return text, (candidates[0].get("finishReason") or "").upper() == "MAX_TOKENS"

    if platform == "anthropic":
        blocks = data.get("content") or []
        text = "".join(block.get("text", "") for block in blocks if block.get("type") == "text")
        return text, data.get("stop_reason") == "max_tokens"

    choices = data.get("choices") or []
    if not choices:
        return "", False
    message = choices[0].get("message", {}) or {}
    text = message.get("content") or ""
    if isinstance(text, list):
        text = "".join(part.get("text", "") for part in text if part.get("text"))
    return text, (choices[0].get("finish_reason") or "") == "length"