"""Offline, zero-config civic-issue classifier.

Shared by the FastAPI micro-service and the Django app as a text-based
fallback so reporting keeps working when no LLM is configured or reachable.
"""

import re

CATEGORY_KEYWORDS = {
    "Pothole": [
        "pothole", "pot hole", "hole in the road", "road damage", "crater",
        "broken road", "dip in the road",
    ],
    "Garbage": [
        "garbage", "trash", "rubbish", "waste", "litter", "dumped",
        "garbage pile", "uncollected", "bin overflowing", "waste pile",
        "garbage bin",
    ],
    "Streetlight": [
        "streetlight", "street light", "light not working", "dark street",
        "lamppost", "lamp post", "street lamp", "lighting", "no street lights",
        "burned out light", "broken light",
    ],
    "Water": [
        "water leak", "leaking pipe", "water line", "leakage", "pipe burst",
        "water supply", "no water", "overflowing drain", "drain overflow",
        "sewage", "manhole", "water logging", "waterlogging", "flooded",
    ],
    "Sanitation": [
        "toilet", "unhygienic", "sanitation", "smell", "stagnant", "mosquito",
        "open drain", "dirty water",
    ],
    "Road": [
        "road", "broken footpath", "footpath", "sidewalk", "road damage",
        "barricade", "construction", "traffic signal", "speed breaker",
    ],
}

PRIORITY_HIGH_KEYWORDS = [
    "accident", "injured", "dangerous", "immediate", "emergency", "risk",
    "urgent", "serious", "children", "school", "electrical", "wire", "shock",
    "sewage", "flood", "collapse", "fallen", "blocking", "major",
]

PRIORITY_LOW_KEYWORDS = [
    "minor", "small", "cosmetic", "cleaning", "paint", "notice",
]


def _score_category(description):
    text = description.lower()
    best = ("Other", 0)
    for category, keywords in CATEGORY_KEYWORDS.items():
        score = 0
        for kw in keywords:
            if kw in text:
                score += 1
        if score > best[1]:
            best = (category, score)
    return best[0]


def _score_priority(description):
    text = description.lower()
    if any(kw in text for kw in PRIORITY_HIGH_KEYWORDS):
        return "High"
    if any(kw in text for kw in PRIORITY_LOW_KEYWORDS):
        return "Low"
    return "Medium"


def classify(description):
    """Return {category, priority, summary} without any LLM."""
    category = _score_category(description)
    priority = _score_priority(description)
    if category == "Other":
        summary = "Reported civic issue (%s priority)" % priority.lower()
    else:
        summary = "Reported %s issue (%s priority)" % (category.lower(), priority.lower())
    if not summary:
        summary = "No description provided."
    return {
        "category": category,
        "priority": priority,
        "summary": summary,
    }