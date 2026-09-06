"""CivicSense AI micro-service (Listing 3.2).

Exposes POST /classify. Uses LiteLLM when an LLM provider is configured
via environment variables, otherwise falls back to the offline rule-based
classifier so the system never depends on a reachable LLM.
"""

import json
import os

from fastapi import FastAPI
from pydantic import BaseModel

from fallback import classify as fallback_classify

app = FastAPI(title="CivicSense AI Service")


class IssueIn(BaseModel):
    description: str
    photo: str | None = None
    latitude: float | None = None
    longitude: float | None = None


class ClassifyOut(BaseModel):
    category: str
    priority: str
    summary: str


def _classify_with_llm(issue: IssueIn):
    import litellm

    model = os.environ["LLM_MODEL"]
    prompt = (
        "You are a civic issue triage assistant. Classify the issue below.\n"
        'Reply with ONLY valid JSON: {"category": "...", "priority": "High|Medium|Low", "summary": "..."}.\n'
        "Category must be one of: Pothole, Garbage, Streetlight, Water, Sanitation, Road, Other.\n\n"
        f"Description: {issue.description}\n"
    )
    resp = litellm.completion(
        model=model,
        messages=[{"role": "user", "content": prompt}],
        max_tokens=200,
        temperature=0,
    )
    content = resp.choices[0].message.content
    start = content.find("{")
    end = content.rfind("}") + 1
    data = json.loads(content[start:end]) if start != -1 else {}
    category = str(data.get("category", "Other")).strip()
    priority = str(data.get("priority", "Medium")).strip()
    if priority not in ("High", "Medium", "Low"):
        priority = "Medium"
    summary = str(data.get("summary", issue.description[:200])).strip()[:255]
    return {"category": category, "priority": priority, "summary": summary}


@app.post("/classify", response_model=ClassifyOut)
def classify(issue: IssueIn):
    if os.environ.get("LLM_MODEL"):
        try:
            return _classify_with_llm(issue)
        except Exception:
            # Never let an LLM failure break reporting.
            pass
    return fallback_classify(issue.description)