"""Bitrix24 REST extractor (webhook auth).

Работает через входящий webhook (URL вида
хhttps://<portal>.bitrix24.ru/rest/<user_id>/<token>/<method>.json),
использует start для курсорной пагинации.
Поддерживается любой метод в стиле *.list: crm.deal.list, crm.lead.list,
crm.contact.list, tasks.task.list, etc.
"""
from __future__ import annotations

import logging
import time
from dataclasses import dataclass
from typing import Any, Iterable

import pandas as pd
import requests

LOG = logging.getLogger(__name__)

PAGE_SIZE = 50  # Bitrix24 hard cap
MAX_RETRIES = 5


@dataclass(frozen=True)
class BitrixConfig:
    webhook_url: str  # ends with a slash
    timeout: int = 60


class BitrixError(RuntimeError):
    pass


def _post_with_retry(cfg: BitrixConfig, method: str, payload: dict) -> dict:
    url = cfg.webhook_url.rstrip("/") + f"/{method}.json"
    for attempt in range(1, MAX_RETRIES + 1):
        resp = requests.post(url, json=payload, timeout=cfg.timeout)
        if resp.status_code == 429 or 500 <= resp.status_code < 600:
            wait = min(2 ** attempt, 30)
            LOG.warning("Bitrix %s, retrying in %ss", resp.status_code, wait)
            time.sleep(wait)
            continue
        if not resp.ok:
            raise BitrixError(f"Bitrix {resp.status_code}: {resp.text[:500]}")
        body = resp.json()
        if "error" in body:
            raise BitrixError(f"{body.get('error')}: {body.get('error_description')}")
        return body
    raise BitrixError("Bitrix: exhausted retries")


def iter_list(
    cfg: BitrixConfig,
    method: str,
    *,
    filter_: dict[str, Any] | None = None,
    select: list[str] | None = None,
    order: dict[str, str] | None = None,
) -> Iterable[dict]:
    """Stream all rows from a *.list endpoint. Avoids materializing huge lists."""
    start = 0
    while True:
        payload: dict[str, Any] = {"start": start}
        if filter_:
            payload["filter"] = filter_
        if select:
            payload["select"] = select
        if order:
            payload["order"] = order

        body = _post_with_retry(cfg, method, payload)
        rows = body.get("result", [])
        for row in rows:
            yield row

        next_start = body.get("next")
        if next_start is None:
            break
        start = next_start


def fetch_deals_changed_since(
    cfg: BitrixConfig,
    since: pd.Timestamp,
    *,
    select: list[str] | None = None,
) -> pd.DataFrame:
    """Инкрементальная выгрузка сделок, изменённых после since."""
    select = select or ["ID", "TITLE", "STAGE_ID", "OPPORTUNITY", "CURRENCY_ID",
                        "DATE_CREATE", "DATE_MODIFY", "ASSIGNED_BY_ID",
                        "CONTACT_ID", "COMPANY_ID"]
    rows = list(iter_list(
        cfg,
        "crm.deal.list",
        filter_={">DATE_MODIFY": since.strftime("%Y-%m-%dT%H:%M:%S")},
        select=select,
        order={"DATE_MODIFY": "ASC"},
    ))
    df = pd.DataFrame(rows)
    for col in ("DATE_CREATE", "DATE_MODIFY"):
        if col in df.columns:
            df[col] = pd.to_datetime(df[col], errors="coerce", utc=True)
    if "OPPORTUNITY" in df.columns:
        df["OPPORTUNITY"] = pd.to_numeric(df["OPPORTUNITY"], errors="coerce")
    df["loaded_at"] = pd.Timestamp.utcnow()
    LOG.info("Bitrix deals: %s rows since %s", len(df), since)
    return df
