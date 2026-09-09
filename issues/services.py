"""(Listing 3.3) Django helper that calls the AI micro-service, with a safe
fallback so reporting keeps working even if the AI service is down.
"""

import math
import re

import requests

from django.conf import settings

from fallback import classify as fallback_classify

DEFAULT_DUPLICATE_RADIUS_M = 100.0


def classify_issue(description, *, platform=None, api_key=None, model=None, photo=None):
    """Return {category, priority, summary, description}.

    Attempts the FastAPI /classify endpoint with optional per-user LLM config
    and an optional photo (readable file object); if unavailable, falls back
    to the local rule-based classifier so reporting never simply fails.
    """
    payload = {"description": description}
    if photo is not None:
        try:
            raw = photo.read()
            photo.seek(0)
        except Exception:
            raw = None
        if raw:
            import base64
            mime = getattr(photo, "content_type", None) or "image/jpeg"
            payload["photo"] = "data:%s;base64,%s" % (
                mime,
                base64.b64encode(raw).decode("ascii"),
            )
    if platform:
        payload["platform"] = platform
    if api_key:
        payload["api_key"] = api_key
    if model:
        payload["model"] = model
    try:
        r = requests.post(
            settings.AI_SERVICE_URL + "/classify",
            json=payload,
            timeout=15,
        )
        r.raise_for_status()
        return r.json()
    except Exception:
        # Text fallback keeps reporting working even if the AI service is down.
        result = fallback_classify(description)
        result["description"] = description
        result["source"] = "fallback"
        return result


def find_duplicate(description, latitude, longitude, radius_m=DEFAULT_DUPLICATE_RADIUS_M):
    """Return an existing Issue likely duplicating the reported one, or None.

    Detects reports for the same kind of problem within a small radius using
    a simple equirectangular distance formula (adequate for local areas).
    """
    from .models import Issue

    lat_deg = radius_m / 111320.0
    lon_deg = radius_m / (111320.0 * math.cos(math.radians(latitude)))

    candidates = Issue.objects.filter(
        latitude__range=(latitude - lat_deg, latitude + lat_deg),
        longitude__range=(longitude - lon_deg, longitude + lon_deg),
        status__in=["open", "progress"],
    ).exclude(pk=None).select_related("category")[:50]

    # Prioritise a reasonable degree of overlap in the wording.
    def words(text):
        return {w for w in re.split(r"\W+", text.lower()) if len(w) > 4}

    haystack = words(description)
    best, best_score = None, 0
    for cand in candidates:
        if not cand.description:
            continue
        cwords = words(cand.description)
        common = len(haystack & cwords)
        if common > best_score:
            best_score, best = common, cand
    if best is not None and best_score >= 2:
        return best
    return None