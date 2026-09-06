"""CivicSense AI micro-service (Listing 3.2).

Exposes POST /classify. Uses LiteLLM when an LLM provider is configured
via environment variables, otherwise falls back to the offline rule-based
classifier so the system never depends on a reachable LLM.
"""

import json
import os
import time

from fastapi import FastAPI
from pydantic import BaseModel

from fallback import classify as fallback_classify

app = FastAPI(title="CivicSense AI Service")

CATEGORIES = ("Pothole", "Garbage", "Streetlight", "Water", "Sanitation", "Road", "Other")
PRIORITIES = ("High", "Medium", "Low")


class IssueIn(BaseModel):
    description: str
    photo: str | None = None
    latitude: float | None = None
    longitude: float | None = None


class ClassifyOut(BaseModel):
    category: str
    priority: str
    summary: str
    description: str


_SYSTEM_PROMPT = (
    "You are a civic issue triage assistant. Given a citizen's description of a "
    "local problem, reply with ONLY valid JSON and nothing else — no markdown, "
    "no prose. The JSON object must use exactly these keys:\n"
    '{"category": "...", "priority": "...", "summary": "...", "description": "..."}\n'
    f"- \"category\" must be exactly one of: {', '.join(CATEGORIES)}.\n"
    f"- \"priority\" must be exactly one of: {', '.join(PRIORITIES)}.\n"
    '- "summary" is a short one-line headline (max 255 chars).\n'
    '- "description" is a clear, factual, well-written citizen report of 2-3 '
    "sentences (max 2000 chars). Never invent details that are not mentioned.\n"
)


def _extract_json(content):
    """Return the first parseable JSON object in the model output."""
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


def _classify_with_llm(issue: IssueIn):
    import litellm

    model = os.environ["LLM_MODEL"]
    if os.environ.get("LLM_API_KEY"):
        os.environ["GEMINI_API_KEY"] = os.environ["LLM_API_KEY"]

    data = {}
    last_error = None
    for attempt in range(3):
        try:
            resp = litellm.completion(
                model=model,
                messages=[
                    {"role": "system", "content": _SYSTEM_PROMPT},
                    {"role": "user", "content": issue.description},
                ],
                max_tokens=1000,
                temperature=0,
            )
            data = _extract_json(resp.choices[0].message.content)
            if "category" in data:
                break
        except (litellm.ServiceUnavailableError, litellm.InternalServerError) as exc:
            last_error = exc
            time.sleep(1.5 * (attempt + 1))
        except Exception as exc:
            raise RuntimeError("LLM unavailable") from exc
    if "category" not in data:
        raise RuntimeError("LLM returned no valid classification") from last_error

    category = str(data.get("category", "Other")).strip()
    if category not in CATEGORIES:
        category = "Other"
    priority = str(data.get("priority", "Medium")).strip()
    if priority not in PRIORITIES:
        priority = "Medium"
    summary = str(data.get("summary", issue.description[:200])).strip()[:255]
    description = str(data.get("description", issue.description)).strip()[:2000] or issue.description
    return {
        "category": category,
        "priority": priority,
        "summary": summary,
        "description": description,
    }


@app.post("/classify", response_model=ClassifyOut)
def classify(issue: IssueIn):
    if os.environ.get("LLM_MODEL"):
        try:
            return _classify_with_llm(issue)
        except Exception:
            # Never let an LLM failure break reporting.
            pass
    result = fallback_classify(issue.description)
    result["description"] = issue.description
    return result