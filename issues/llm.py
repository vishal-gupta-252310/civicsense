"""LLM platform registry and live model-list fetching.

Each platform's model catalog is fetched from the provider's own public API
(the authoritative "common place"), so the dropdown always shows real models
and stays correct as providers add or retire them.
"""

import requests

PLATFORMS = {
    "groq": {
        "label": "Groq",
        "models_url": "https://api.groq.com/openai/v1/models",
        "auth": "bearer",
        "parser": "openai",
    },
    "gemini": {
        "label": "Google Gemini",
        "models_url": "https://generativelanguage.googleapis.com/v1beta/models",
        "auth": "query",
        "parser": "gemini",
    },
    "openrouter": {
        "label": "OpenRouter",
        "models_url": "https://openrouter.ai/api/v1/models",
        "auth": "none",
        "parser": "openai",
    },
    "openai": {
        "label": "OpenAI",
        "models_url": "https://api.openai.com/v1/models",
        "auth": "bearer",
        "parser": "openai",
    },
    "anthropic": {
        "label": "Anthropic Claude",
        "models_url": "https://api.anthropic.com/v1/models",
        "auth": "anthropic",
        "parser": "anthropic",
    },
    "mistral": {
        "label": "Mistral AI",
        "models_url": "https://api.mistral.ai/v1/models",
        "auth": "bearer",
        "parser": "openai",
    },
    "deepseek": {
        "label": "DeepSeek",
        "models_url": "https://api.deepseek.com/models",
        "auth": "bearer",
        "parser": "openai",
    },
    "together": {
        "label": "Together AI",
        "models_url": "https://api.together.xyz/v1/models",
        "auth": "bearer",
        "parser": "openai",
    },
}

# LiteLLM provider prefix prepended to a model id, e.g. "groq" -> "groq/<id>".
# These must match what LiteLLM expects for each provider.
LITELLM_PREFIX = {
    "groq": "groq/",
    "gemini": "gemini/",
    "openrouter": "openrouter/",
    "openai": "openai/",
    "anthropic": "anthropic/",
    "mistral": "mistral/",
    "deepseek": "deepseek/",
    "together": "together_ai/",
}


def _openai_id_list(data):
    return [m["id"] for m in data.get("data", []) if m.get("id")]


def _anthropic_id_list(data):
    return [m["id"] for m in data.get("data", []) if m.get("id")]


def _gemini_id_list(data):
    ids = []
    for m in data.get("models", []):
        name = m.get("name", "")
        if not name.startswith("models/"):
            continue
        methods = m.get("supportedGenerationMethods", [])
        if "generateContent" not in methods:
            continue
        ids.append(name[len("models/"):])
    return ids


PARSERS = {
    "openai": _openai_id_list,
    "anthropic": _anthropic_id_list,
    "gemini": _gemini_id_list,
}


def fetch_models(platform, api_key):
    """Return sorted model ids for a platform, or raise on invalid input/error."""
    platform_data = PLATFORMS.get(platform)
    if not platform_data:
        raise ValueError("Unknown platform.")
    headers = {}
    params = {}
    if platform_data["auth"] == "bearer":
        headers["Authorization"] = f"Bearer {api_key}"
    elif platform_data["auth"] == "query":
        params["key"] = api_key
    elif platform_data["auth"] == "anthropic":
        headers["x-api-key"] = api_key
        headers["anthropic-version"] = "2023-06-01"
    elif platform_data["auth"] == "none":
        pass
    else:
        raise ValueError("Unsupported auth style.")
    resp = requests.get(platform_data["models_url"], headers=headers, params=params, timeout=15)
    resp.raise_for_status()
    ids = PARSERS[platform_data["parser"]](resp.json())
    return sorted(ids)


def full_model_id(platform, model_id):
    """Return the LiteLLM model string, e.g. groq/<id>."""
    return (LITELLM_PREFIX.get(platform, "") + model_id).strip("/") or model_id