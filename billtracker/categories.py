"""Rule-based topic categories for legislation.

The site has no subject field, so we infer one from the text. Two signals:

1. Keywords in the short title, long title and synopsis. Title matches count
   double, because titles are short and deliberate.
2. The Delaware Code titles a bill amends ("AN ACT TO AMEND TITLE 14 ..."),
   which map cleanly onto subject areas.

Ceremonial resolutions ("RECOGNIZING ...", "DESIGNATING ... AS ... DAY") are
detected separately, so they don't inflate the substantive categories.
"""

import re

OTHER = "Other"
CEREMONIAL = "Ceremonial & Recognition"

CATEGORY_KEYWORDS: dict[str, list[str]] = {
    "Education": [
        "school", "student", "teacher", "educat", "universit", "college",
        "curriculum", "scholarship", "early childhood", "literacy", "pre-k",
        "classroom", "academ",
    ],
    "Environment & Energy": [
        "environment", "climate", "energy", "solar", "wind", "emission",
        "greenhouse", "pollut", "recycl", "conservation", "wildlife",
        "water quality", "offshore", "electric vehicle", "utilit", "renewable",
        "flood", "coastal", "forest", "plastic", "waste", "natural resource",
        "electric", "pjm",
    ],
    "Health": [
        "health", "medical", "medicaid", "medicare", "hospital", "physician",
        "nurse", "prescription", "pharmac", "mental", "behavioral", "disease",
        "cancer", "opioid", "overdose", "dental", "patient", "public health",
    ],
    "Public Safety & Justice": [
        "crime", "criminal", "police", "law enforcement", "sentenc", "prison",
        "correction", "firearm", "gun", "weapon", "court", "judge", "judicial",
        "offense", "felony", "misdemeanor", "victim", "probation", "parole",
        "expunge", "attorney general", "emergency management", "fire compan",
        "justice", "homeland security", "fire marshal",
    ],
    "Taxes & Budget": [
        "tax", "budget", "appropriat", "bond and capital", "revenue",
        "fiscal year", "grants-in-aid", "expenditure", "supplementary",
    ],
    "Transportation": [
        "transport", "motor vehicle", "driver", "highway", "road", "traffic",
        "transit", "deldot", "bicycl", "parking", "toll", "railroad",
        "driving", "license plate", "bypass",
    ],
    "Housing & Property": [
        "housing", "landlord", "tenant", "rent", "mortgage", "real property",
        "real estate", "homeown", "evict", "zoning", "manufactured home",
        "foreclos", "property tax",
    ],
    "Labor & Employment": [
        "employ", "wage", "worker", "labor", "workplace", "unemployment",
        "pension", "collective bargaining", "union", "paid leave", "retire",
    ],
    "Business & Commerce": [
        "business", "corporation", "commerce", "consumer", "alcohol", "liquor",
        "bank", "insurance", "gaming", "lottery", "cannabis", "marijuana",
        "limited liability", "partnership", "franchise", "professional", "occupation",
        "contractor", "sports wagering",
    ],
    "Government & Elections": [
        "election", "vote", "voting", "ballot", "candidate", "campaign",
        "general assembly", "state agenc", "county", "municipal", "town of",
        "city of", "public records", "freedom of information", "ethics",
        "constitution", "state employee", "charter", "joint session",
        "senate is organized", "procurement",
    ],
    "Families & Social Services": [
        "child", "famil", "foster", "adopt", "welfare", "senior", "aging",
        "disabilit", "veteran", "food", "poverty", "domestic", "marriage",
        "custody", "social service",
    ],
    "Agriculture & Animals": [
        "agricult", "farm", "animal", "dog", "livestock", "pet", "hunting",
        "fishing", "crop", "poultry", "veterinar",
    ],
}

CATEGORIES = [*CATEGORY_KEYWORDS, CEREMONIAL, OTHER]

# Delaware Code title number -> category.
CODE_TITLE_CATEGORIES: dict[int, str] = {
    1: "Government & Elections",
    2: "Transportation",
    3: "Agriculture & Animals",
    4: "Business & Commerce",
    5: "Business & Commerce",
    6: "Business & Commerce",
    7: "Environment & Energy",
    8: "Business & Commerce",
    9: "Government & Elections",
    10: "Public Safety & Justice",
    11: "Public Safety & Justice",
    12: "Public Safety & Justice",
    13: "Families & Social Services",
    14: "Education",
    15: "Government & Elections",
    16: "Health",
    17: "Transportation",
    18: "Business & Commerce",
    19: "Labor & Employment",
    20: "Public Safety & Justice",
    21: "Transportation",
    22: "Government & Elections",
    23: "Environment & Energy",
    24: "Business & Commerce",
    25: "Housing & Property",
    26: "Environment & Energy",
    28: "Business & Commerce",
    29: "Government & Elections",
    30: "Taxes & Budget",
    31: "Families & Social Services",
}

TITLE_MATCH_WEIGHT = 2
CODE_TITLE_WEIGHT = 3

_KEYWORD_PATTERNS = {
    category: re.compile(r"\b(?:" + "|".join(map(re.escape, words)) + ")", re.IGNORECASE)
    for category, words in CATEGORY_KEYWORDS.items()
}
_CODE_TITLE_PATTERN = re.compile(r"\bTITLES?\s+(\d+)((?:\s*(?:,|AND)\s*\d+)*)", re.IGNORECASE)
_CEREMONIAL_PATTERN = re.compile(
    r"^\s*(?:A\s+)?(?:RESOLUTION\s+)?(?:"
    r"RECOGNIZ|RESPECTING|COMMEMORAT|HONOR|CONGRATULAT|CELEBRAT|PROCLAIM|MOURN|REMEMBER"
    r"|EXPRESSING\s+(?:CONDOLENCE|SYMPATHY|GRATITUDE|APPRECIATION)"
    r"|DESIGNATING\s+.*\b(?:DAY|WEEK|MONTH|YEAR)\b"
    r")",
    re.IGNORECASE,
)


def _text(value) -> str:
    """Treat None/NaN (missing values from pandas) as empty text."""
    return value if isinstance(value, str) else ""


def code_titles(long_title: str) -> list[int]:
    """Delaware Code title numbers mentioned in a long title, e.g. "TITLES 11 AND 29" -> [11, 29]."""
    numbers = []
    for match in _CODE_TITLE_PATTERN.finditer(long_title or ""):
        numbers.append(int(match.group(1)))
        numbers.extend(int(n) for n in re.findall(r"\d+", match.group(2)))
    return numbers


def is_ceremonial(long_title: str, is_resolution: bool) -> bool:
    return is_resolution and bool(_CEREMONIAL_PATTERN.match(long_title or ""))


def category_scores(title_text: str, synopsis: str, long_title: str) -> dict[str, int]:
    scores = {category: 0 for category in CATEGORY_KEYWORDS}
    for category, pattern in _KEYWORD_PATTERNS.items():
        scores[category] += TITLE_MATCH_WEIGHT * len(pattern.findall(title_text or ""))
        scores[category] += len(pattern.findall(synopsis or ""))
    for title_number in code_titles(long_title):
        category = CODE_TITLE_CATEGORIES.get(title_number)
        if category:
            scores[category] += CODE_TITLE_WEIGHT
    return scores


def categorize(
    short_title: str | None,
    long_title: str | None,
    synopsis: str | None,
    is_resolution: bool = False,
) -> str:
    """Pick the single best-matching category for one piece of legislation."""
    short_title, long_title, synopsis = _text(short_title), _text(long_title), _text(synopsis)
    if is_ceremonial(long_title, is_resolution):
        return CEREMONIAL

    title_text = f"{short_title} {long_title}"
    scores = category_scores(title_text, synopsis, long_title)
    best_category = max(scores, key=scores.get)  # ties go to the earlier category
    return best_category if scores[best_category] > 0 else OTHER
