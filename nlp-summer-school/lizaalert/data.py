"""Loading and normalisation of the LizaAlert dataset.

The original CSV in the summer-school project mixed encodings (utf-8 vs
cp1251), used inconsistent gender labels and stored `age` as anything
from a single int to a Python-list-as-string. This module wraps all of
that mess into one tidy loader.
"""

from __future__ import annotations

from pathlib import Path
from typing import Iterable

import pandas as pd

from .parsing import detect_status, normalise_gender, parse_age


DATE_COLUMNS_DEFAULT = (
    "date_search",
    "date_of_loss",
    "last_search_date",
)


def read_csv_safely(path: str | Path, **kwargs) -> pd.DataFrame:
    """Read a CSV with utf-8 first, fall back to cp1251."""
    path = Path(path)
    for enc in ("utf-8", "cp1251"):
        try:
            return pd.read_csv(path, encoding=enc, **kwargs)
        except UnicodeDecodeError:
            continue
    raise UnicodeDecodeError(
        "utf-8", b"", 0, 1, f"Could not decode {path} with utf-8 or cp1251"
    )


def normalise(
    df: pd.DataFrame,
    *,
    text_col: str = "content",
    age_col: str = "age",
    gender_col: str = "gender",
    status_col: str = "status",
    date_columns: Iterable[str] = DATE_COLUMNS_DEFAULT,
) -> pd.DataFrame:
    """Apply all common cleanup steps and return a fresh dataframe.

    Steps:
      - infer missing 'status' from the post body via regex,
      - unify gender into {муж, жен, мн, None},
      - parse 'age' to numeric (one row per age via explode),
      - parse date columns to pandas datetimes and split into y/m/d/h.
    """
    df = df.copy()

    # status
    if status_col in df.columns:
        df[status_col] = df[status_col].where(
            df[status_col].notna(), df.get(text_col, "").apply(detect_status)
        )
    elif text_col in df.columns:
        df[status_col] = df[text_col].apply(detect_status)

    # gender
    if gender_col in df.columns:
        df["gender_norm"] = df[gender_col].apply(normalise_gender)

    # age
    if age_col in df.columns:
        df["age_list"] = df[age_col].apply(parse_age)

    # dates
    for col in date_columns:
        if col in df.columns:
            df[col] = pd.to_datetime(df[col], errors="coerce")
            df[f"{col}_year"] = df[col].dt.year
            df[f"{col}_month"] = df[col].dt.month
            df[f"{col}_day"] = df[col].dt.day
            df[f"{col}_hour"] = df[col].dt.hour

    return df


def explode_ages(df: pd.DataFrame, age_list_col: str = "age_list") -> pd.DataFrame:
    """Long-format: one row per parsed age."""
    df = df.copy()
    df = df.explode(age_list_col).dropna(subset=[age_list_col])
    df["age"] = df[age_list_col].astype(int)
    return df
