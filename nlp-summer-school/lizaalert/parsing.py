"""Extraction of status, gender and age from raw search-and-rescue posts.

Three groups of helpers:
  - status detection from free text via regex;
  - gender normalisation to a unified vocabulary;
  - age parsing from heterogeneous representations.
"""

from __future__ import annotations

import ast
import re
from typing import Iterable

import pandas as pd


# ---------------------------------------------------------------------------
# Status
# ---------------------------------------------------------------------------

STATUS_ALIVE = "жив(а)"
STATUS_DEAD = "погиб(ла)"
STATUS_MISSING = "пропал(а)"

_STATUS_PATTERNS = [
    (STATUS_ALIVE, re.compile(r"\bжив(?:ая|ой|а|ы)?\b", re.IGNORECASE)),
    (STATUS_DEAD, re.compile(r"\bпогиб(?:ла|ший|шая|ли)?\b|\bгибел", re.IGNORECASE)),
    (STATUS_MISSING, re.compile(r"\bпропал(?:а|и)?\b|\bпропаж[аи]\b|\bпропавш", re.IGNORECASE)),
]


def detect_status(text: object) -> str | None:
    """Return one of {жив(а), погиб(ла), пропал(а)} or None if unknown."""
    if not isinstance(text, str):
        return None
    for label, pattern in _STATUS_PATTERNS:
        if pattern.search(text):
            return label
    return None


# ---------------------------------------------------------------------------
# Gender
# ---------------------------------------------------------------------------

_MALE_TOKENS = ("муж", "мальчик", "мужчина", "парень", "male")
_FEMALE_TOKENS = ("жен", "девочка", "девушка", "женщина", "female")


def normalise_gender(value: object) -> str | None:
    """Normalise mixed gender labels to one of {муж, жен, мн, None}."""
    if value is None:
        return None
    if isinstance(value, list):
        kinds = {normalise_gender(v) for v in value} - {None}
        if not kinds:
            return None
        return next(iter(kinds)) if len(kinds) == 1 else "мн"
    text = str(value).strip().lower()
    if not text or text in {"nan", "none", "неопр"}:
        return None
    if any(tok in text for tok in _MALE_TOKENS):
        return "муж"
    if any(tok in text for tok in _FEMALE_TOKENS):
        return "жен"
    return None


# ---------------------------------------------------------------------------
# Age
# ---------------------------------------------------------------------------

_AGE_NUM_RE = re.compile(r"\d+")


def parse_age(raw: object) -> list[int]:
    """Convert the messy 'age' field into a clean list of ints.

    Handles three forms seen in the dataset:
      - integer or float ages
      - JSON-like lists, e.g. "[7, 18]"
      - free text containing one or more numbers
    """
    if raw is None or (isinstance(raw, float) and pd.isna(raw)):
        return []
    if isinstance(raw, (int,)):
        return [raw]
    if isinstance(raw, float):
        return [int(raw)]
    if isinstance(raw, list):
        return [int(x) for x in raw if str(x).isdigit()]
    if isinstance(raw, str):
        raw = raw.strip()
        if raw.startswith("[") and raw.endswith("]"):
            try:
                value = ast.literal_eval(raw)
                if isinstance(value, (list, tuple)):
                    return [int(x) for x in value if str(x).isdigit()]
                if isinstance(value, int):
                    return [value]
            except (ValueError, SyntaxError):
                pass
        return [int(n) for n in _AGE_NUM_RE.findall(raw)]
    return []


def explode_ages(df: pd.DataFrame, age_col: str = "age") -> pd.DataFrame:
    """Return a long-format dataframe with one row per age value."""
    df = df.copy()
    df["_ages"] = df[age_col].apply(parse_age)
    df = df.explode("_ages").dropna(subset=["_ages"])
    df[age_col] = df["_ages"].astype(int)
    return df.drop(columns=["_ages"])
