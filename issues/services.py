"""(Listing 3.3) Django helper that calls the AI micro-service, with a safe
fallback so reporting keeps working even if the AI service is down.
"""

import math
import re

import requests

from django.conf import settings

from fallback import classify as fallback_classify

DEFAULT_DUPLICATE_RADIUS_M = 100.0


def classify_issue(description):
    """Return {category, priority, summary}.

    Attempts the FastAPI /classify endpoint; if unavailable, falls back to
    the local rule-based classifier so reporting never simply fails.
    """
    try:
        r = requests.post(
            settings.AI_SERVICE_URL + "/classify",
            json={"description": description},
            timeout=8,
        )
        r.raise_for_status()
        return r.json()
    except Exception:
        # Text fallback keeps reporting working even if the AI service is down
        return fallback_classify(description)


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