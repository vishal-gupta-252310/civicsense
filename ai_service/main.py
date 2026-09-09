"""CivicSense AI micro-service (Listing 3.2).

Exposes POST /classify. Sends each provider's own documented chat request
(via ai_service.providers) when an LLM provider is configured, otherwise
falls back to the offline rule-based classifier so the system never depends
on a reachable LLM.
"""

import json
import logging
import os
import re
import time

import requests
from dotenv import load_dotenv
from fastapi import FastAPI
from pydantic import BaseModel

from ai_service import providers
from fallback import classify as fallback_classify

load_dotenv()

app = FastAPI(title="CivicSense AI Service")

logger = logging.getLogger("civicsense.ai")
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(name)s: %(message)s",
)

CATEGORIES = ("Pothole", "Garbage", "Streetlight", "Water", "Sanitation", "Road", "Other")
PRIORITIES = ("High", "Medium", "Low")


class IssueIn(BaseModel):
    description: str
    photo: str | None = None
    latitude: float | None = None
    longitude: float | None = None
    platform: str | None = None
    api_key: str | None = None
    model: str | None = None


class ClassifyOut(BaseModel):
    category: str
    priority: str
    summary: str
    description: str
    source: str = "llm"


_SYSTEM_PROMPT = (
    "You are a civic issue triage assistant. Given a citizen's description of a "
    "local problem, reply with ONLY valid JSON and nothing else — no markdown, "
    "no prose. The JSON object must use exactly these keys:\n"
    '{"category": "...", "priority": "...", "summary": "...", "description": "..."}\n'
    f"- \"category\" must be exactly one of: {', '.join(CATEGORIES)}.\n"
    f"- \"priority\" must be exactly one of: {', '.join(PRIORITIES)}.\n"
    '- "summary" is a short one-line headline (max 255 chars).\n'
    '- "description" is a clear, factual citizen report of 1-2 concise '
    "sentences (aim for ~300 characters, max 400 chars). Be compact. Never "
    "invent details that are not mentioned.\n"
)


def _extract_json(content):
    """Return the first parseable JSON object in the model output."""
    # Some models (e.g. qwen3 on Groq) wrap reasoning in thinking tags
    # before the real answer — drop them so they don't eat the token budget.
    content = re.sub(r"\s*<(thinking|reasoning)[^>]*>.*?</\1>", " ", content, flags=re.DOTALL)
    decoder = json.JSONDecoder()
    for i, ch in enumerate(content):
        if ch == "{":
            try:
                data, _ = decoder.raw_decode(content[i:])
                if isinstance(data, dict):
                    return data
            except json.JSONDecodeError:
                continue
    return {}


def _retry_seconds(resp):
    """Return a safe wait (capped at 30s) from Retry-After or the error body."""
    value = resp.headers.get("Retry-After")
    if value:
        try:
            return min(float(value), 30)
        except ValueError:
            pass
    match = re.search(r"try again in ([0-9.]+)", resp.text or "")
    if match:
        return min(float(match.group(1)), 30)
    return None


def _classify_with_llm(issue: IssueIn):
    # Per-request overrides win; otherwise fall back to environment defaults.
    model = (issue.model or os.environ.get("LLM_MODEL") or "").strip()
    if not model:
        raise RuntimeError("no model configured")
    api_key = issue.api_key or os.environ.get("LLM_API_KEY")
    platform, raw_model = providers.resolve(issue.platform, model)
    if not platform:
        raise RuntimeError(f"cannot determine provider for model {model!r}")
    if not api_key:
        raise RuntimeError("no API key configured")
    logger.info("classify platform=%s model=%s key=%s...%s (len=%d, from_request=%s)",
                platform, raw_model, (api_key or "")[:4], (api_key or "")[-4:],
                len(api_key or ""), bool(issue.api_key))

    url, headers, body = providers.build_request(
        platform, raw_model, api_key, _SYSTEM_PROMPT, issue.description
    )

    data = {}
    last_error = None
    for attempt in range(3):
        try:
            resp = requests.post(url, headers=headers, json=body, timeout=90)
        except requests.RequestException as exc:
            last_error = exc
            logger.warning("LLM request failed (attempt %d): %s", attempt + 1, exc)
            if attempt < 2:
                time.sleep(1.5 * (attempt + 1))
            continue
        if resp.status_code == 429:
            # Provider rate limits (e.g. Groq 1k output-tokens/min) tell us how
            # long to wait via Retry-After / "try again in Ns".
            last_error = RuntimeError("rate limited")
            logger.warning("LLM rate limited (attempt %d): %s",
                           attempt + 1, (resp.text or "")[:150])
            if attempt < 2:
                time.sleep(_retry_seconds(resp) or 1.5 * (attempt + 1))
            continue
        if resp.status_code >= 500:
            last_error = RuntimeError(f"provider error {resp.status_code}")
            logger.warning("LLM provider error (attempt %d): %d %s",
                           attempt + 1, resp.status_code, (resp.text or "")[:150])
            if attempt < 2:
                time.sleep(1.5 * (attempt + 1))
            continue
        if resp.status_code >= 400:
            # Client errors (bad key/model/param) won't heal by retrying.
            raise RuntimeError(f"provider rejected request ({resp.status_code}): "
                               f"{(resp.text or '')[:200]}")
        content, truncated = providers.extract_response(platform, resp.json())
        data = _extract_json(content)
        # A "length" finish means the model hit the token cap and the JSON was
        # truncated/unparseable — treat it as a transient failure and retry.
        if "category" in data and not truncated:
            break
        last_error = RuntimeError("LLM output truncated")
        logger.warning("LLM output truncated (attempt %d): %r", attempt + 1, content[-200:])
        if attempt < 2:
            time.sleep(1.5 * (attempt + 1))
    if "category" not in data:
        raise RuntimeError("LLM returned no valid classification") from last_error

    category = str(data.get("category", "Other")).strip()
    if category not in CATEGORIES:
        category = "Other"
    priority = str(data.get("priority", "Medium")).strip()
    if priority not in PRIORITIES:
        priority = "Medium"
    summary = str(data.get("summary", issue.description[:200])).strip()[:255]
    description = str(data.get("description", issue.description)).strip()[:360] or issue.description
    return {
        "category": category,
        "priority": priority,
        "summary": summary,
        "description": description,
    }


@app.post("/classify", response_model=ClassifyOut)
def classify(issue: IssueIn):
    if os.environ.get("LLM_MODEL") or (issue.model and issue.api_key):
        try:
            result = _classify_with_llm(issue)
            result["source"] = "llm"
            return result
        except Exception as exc:
            # Never let an LLM failure break reporting, but mark it as fallback.
            logger.error("Classification fell back to rules: %s", exc)
    result = fallback_classify(issue.description)
    result["description"] = issue.description
    result["source"] = "fallback"
    return result