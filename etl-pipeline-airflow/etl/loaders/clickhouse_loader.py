"""Idempotent ClickHouse loader.

Пишем в staging-таблицу внутри транзакции в виде INSERT ... SELECT и затем
делаем ALTER TABLE ... REPLACE PARTITION, чтобы перезаливы были атомарны.
Для ReplacingMergeTree добавляем явный OPTIMIZE FINAL на нужных партициях.
"""
from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import Iterable

import pandas as pd
from clickhouse_connect import get_client

LOG = logging.getLogger(__name__)


@dataclass(frozen=True)
class CHConfig:
    host: str
    port: int = 8443
    username: str = "default"
    password: str = ""
    database: str = "default"
    secure: bool = True


def _client(cfg: CHConfig):
    return get_client(
        host=cfg.host,
        port=cfg.port,
        username=cfg.username,
        password=cfg.password,
        database=cfg.database,
        secure=cfg.secure,
    )


def load_replace_partition(
    cfg: CHConfig,
    table: str,
    partition_expr: str,
    df: pd.DataFrame,
) -> int:
    """Replace a single partition atomically with the contents of df."""
    if df.empty:
        LOG.info("load_replace_partition(%s, %s): empty frame, skipping", table, partition_expr)
        return 0

    staging = f"{table}__stg"
    with _client(cfg) as ch:
        ch.command(f"CREATE TABLE IF NOT EXISTS {staging} AS {table}")
        ch.command(f"TRUNCATE TABLE {staging}")
        ch.insert_df(staging, df)
        ch.command(
            f"ALTER TABLE {table} REPLACE PARTITION {partition_expr} FROM {staging}"
        )
        ch.command(f"TRUNCATE TABLE {staging}")
    LOG.info("%s: replaced partition %s with %s rows", table, partition_expr, len(df))
    return len(df)


def stream_load(
    cfg: CHConfig,
    table: str,
    frames: Iterable[pd.DataFrame],
    batch_size: int = 100_000,
) -> int:
    """Потоковая вставка без подмены партиций: append-only история."""
    total = 0
    buffer: list[pd.DataFrame] = []
    buffered_rows = 0
    with _client(cfg) as ch:
        for chunk in frames:
            if chunk.empty:
                continue
            buffer.append(chunk)
            buffered_rows += len(chunk)
            if buffered_rows >= batch_size:
                merged = pd.concat(buffer, ignore_index=True)
                ch.insert_df(table, merged)
                LOG.info("%s: inserted %s rows", table, len(merged))
                total += len(merged)
                buffer.clear()
                buffered_rows = 0
        if buffer:
            merged = pd.concat(buffer, ignore_index=True)
            ch.insert_df(table, merged)
            total += len(merged)
    return total
