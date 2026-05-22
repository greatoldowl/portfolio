"""Yandex.Metrika Reporting API extractor.

Pulls daily dimensions+metrics into a Pandas DataFrame using the
Logs / Reporting API. Handles pagination, retries with exponential backoff,
and light schema normalization so downstream loaders see a stable contract.
Доки: https://yandex.ru/dev/metrika/doc/api2/api_v1/intro.html
"""
from __future__ import annotations

import logging
import time
from dataclasses import dataclass
from datetime import date, timedelta
from typing import Iterable, Sequence

import pandas as pd
import requests

LOG = logging.getLogger(__name__)

API_URL = "https://api-metrika.yandex.net/stat/v1/data"
DEFAULT_LIMIT = 10_000
MAX_RETRIES = 5


@dataclass(frozen=True)
class MetrikaConfig:
    counter_id: int
    oauth_token: str
    timeout: int = 60


class MetrikaError(RuntimeError):
    pass


def _headers(cfg: MetrikaConfig) -> dict[str, str]:
    return {
        "Authorization": f"OAuth {cfg.oauth_token}",
        "Accept": "application/json",
    }


def _request_with_retry(params: dict, cfg: MetrikaConfig) -> dict:
    for attempt in range(1, MAX_RETRIES + 1):
        resp = requests.get(API_URL, params=params, headers=_headers(cfg), timeout=cfg.timeout)
        if resp.status_code == 429 or 500 <= resp.status_code < 600:
            wait = min(2 ** attempt, 30)
            LOG.warning("Metrika %s, retrying in %ss (attempt %s)", resp.status_code, wait, attempt)
            time.sleep(wait)
            continue
        if not resp.ok:
            raise MetrikaError(f"Metrika API {resp.status_code}: {resp.text[:500]}")
        return resp.json()
    raise MetrikaError("Metrika API: exhausted retries")


def fetch_report(
    cfg: MetrikaConfig,
    *,
    dimensions: Sequence[str],
    metrics: Sequence[str],
    date_from: date,
    date_to: date,
    filters: str | None = None,
) -> pd.DataFrame:
    """Fetch a Metrika report paginated by offset."""
    rows: list[dict] = []
    offset = 1
    while True:
        params = {
            "ids": cfg.counter_id,
            "dimensions": ",".join(dimensions),
            "metrics": ",".join(metrics),
            "date1": date_from.isoformat(),
            "date2": date_to.isoformat(),
            "limit": DEFAULT_LIMIT,
            "offset": offset,
            "accuracy": "full",
        }
        if filters:
            params["filters"] = filters

        payload = _request_with_retry(params, cfg)
        chunk = payload.get("data", [])
        if not chunk:
            break

        for item in chunk:
            row = {dim: val["name"] for dim, val in zip(dimensions, item["dimensions"])}
            for metric, value in zip(metrics, item["metrics"]):
                row[metric] = value
            rows.append(row)

        if len(chunk) < DEFAULT_LIMIT:
            break
        offset += DEFAULT_LIMIT

    df = pd.DataFrame(rows)
    df["loaded_at"] = pd.Timestamp.utcnow()
    df["counter_id"] = cfg.counter_id
    LOG.info("Metrika report: %s rows for %s..%s", len(df), date_from, date_to)
    return df


def incremental_daily(
    cfg: MetrikaConfig,
    *,
    dimensions: Sequence[str],
    metrics: Sequence[str],
    start: date,
    end: date,
) -> Iterable[pd.DataFrame]:
    """Yield one DataFrame per day — friendly for chunked loads to ClickHouse."""
    current = start
    while current <= end:
        yield fetch_report(
            cfg,
            dimensions=dimensions,
            metrics=metrics,
            date_from=current,
            date_to=current,
        )
        current += timedelta(days=1)
