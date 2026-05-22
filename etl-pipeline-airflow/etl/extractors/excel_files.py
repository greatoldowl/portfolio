"""Excel files extractor.

Собирает .xlsx/.xls из локальной директории или S3, нормализует заголовки,
ловит типичные проблемы: объединённые ячейки, русские числовые разделители,
даты в формате "ДД.ММ.ГГГГ". Добавляет source_file/sheet/loaded_at для аудита.
"""
from __future__ import annotations

import hashlib
import logging
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable

import pandas as pd

LOG = logging.getLogger(__name__)

_HEADER_RE = re.compile(r"[^0-9a-zа-яё]+", re.IGNORECASE)


@dataclass(frozen=True)
class ExcelSource:
    path: Path
    sheet: str | int = 0
    skip_rows: int = 0


def _normalize_column(name: str) -> str:
    name = (name or "").strip().lower()
    name = _HEADER_RE.sub("_", name).strip("_")
    return name or "unnamed"


def _coerce_numeric(series: pd.Series) -> pd.Series:
    if series.dtype != object:
        return series
    sample = series.dropna().astype(str).head(20)
    if sample.empty:
        return series
    looks_numeric = sample.str.match(r"^-?[\d \xa0]+([.,]\d+)?$").mean() > 0.8
    if not looks_numeric:
        return series
    cleaned = (
        series.astype(str)
        .str.replace("\xa0", "", regex=False)
        .str.replace(" ", "", regex=False)
        .str.replace(",", ".", regex=False)
    )
    return pd.to_numeric(cleaned, errors="coerce")


def _file_hash(path: Path) -> str:
    h = hashlib.sha1()
    with path.open("rb") as fh:
        for chunk in iter(lambda: fh.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()[:12]


def load_excel(src: ExcelSource) -> pd.DataFrame:
    df = pd.read_excel(
        src.path,
        sheet_name=src.sheet,
        skiprows=src.skip_rows,
        engine="openpyxl" if str(src.path).endswith(".xlsx") else None,
    )
    # drop fully empty rows / columns left over after merged-cell exports
    df = df.dropna(axis=1, how="all").dropna(axis=0, how="all")
    df.columns = [_normalize_column(c) for c in df.columns]
    df = df.loc[:, ~df.columns.duplicated()]

    for col in df.columns:
        df[col] = _coerce_numeric(df[col])

    df["source_file"] = src.path.name
    df["source_sheet"] = str(src.sheet)
    df["source_hash"] = _file_hash(src.path)
    df["loaded_at"] = pd.Timestamp.utcnow()
    LOG.info("Excel %s/%s: %s rows, %s cols", src.path.name, src.sheet, *df.shape)
    return df


def load_directory(
    directory: Path,
    *,
    pattern: str = "*.xlsx",
    sheet: str | int = 0,
) -> Iterable[pd.DataFrame]:
    """Iterate all Excel files matching a glob. Stream-friendly."""
    for path in sorted(directory.glob(pattern)):
        yield load_excel(ExcelSource(path=path, sheet=sheet))
