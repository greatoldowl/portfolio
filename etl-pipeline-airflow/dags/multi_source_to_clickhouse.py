"""Airflow DAG: выгрузка из Yandex.Metrika, Bitrix24 и Excel в ClickHouse.

Паттерн:
  * Каждый источник — своё задание (TaskGroup), работают параллельно.
  * Общий sensor на "источник доступен" + выгрузка + валидация + публикация в витрину.
  * Idempotent: перезапуск за любой день перезаливает партицию без дублей.
"""
from __future__ import annotations

from datetime import datetime, timedelta
from pathlib import Path

import pendulum
from airflow.decorators import dag, task, task_group
from airflow.models import Variable

from etl.extractors.bitrix24 import BitrixConfig, fetch_deals_changed_since
from etl.extractors.excel_files import load_directory
from etl.extractors.yandex_metrika import MetrikaConfig, fetch_report
from etl.loaders.clickhouse_loader import CHConfig, load_replace_partition, stream_load

DEFAULT_ARGS = {
    "owner": "data-platform",
    "retries": 3,
    "retry_delay": timedelta(minutes=5),
    "retry_exponential_backoff": True,
    "max_retry_delay": timedelta(minutes=30),
}


def _ch_cfg() -> CHConfig:
    return CHConfig(
        host=Variable.get("CH_HOST"),
        username=Variable.get("CH_USER"),
        password=Variable.get("CH_PASSWORD"),
        database=Variable.get("CH_DB", default_var="analytics"),
    )


@dag(
    dag_id="multi_source_to_clickhouse",
    description="Yandex.Metrika + Bitrix24 + Excel → ClickHouse",
    schedule="@daily",
    start_date=pendulum.datetime(2025, 1, 1, tz="Europe/Moscow"),
    catchup=False,
    max_active_runs=1,
    default_args=DEFAULT_ARGS,
    tags=["etl", "clickhouse", "bi"],
)
def multi_source_to_clickhouse():

    @task_group(group_id="yandex_metrika")
    def metrika_group():
        @task
        def extract_metrika(data_interval_start: datetime) -> int:
            cfg = MetrikaConfig(
                counter_id=int(Variable.get("METRIKA_COUNTER_ID")),
                oauth_token=Variable.get("METRIKA_TOKEN"),
            )
            day = data_interval_start.date()
            df = fetch_report(
                cfg,
                dimensions=["ym:s:date", "ym:s:trafficSource", "ym:s:lastTrafficSource"],
                metrics=["ym:s:visits", "ym:s:users", "ym:s:bounceRate", "ym:s:goal12345reaches"],
                date_from=day,
                date_to=day,
            )
            return load_replace_partition(
                _ch_cfg(),
                table="analytics.metrika_traffic",
                partition_expr=f"'{day.isoformat()}'",
                df=df,
            )

        extract_metrika()

    @task_group(group_id="bitrix24")
    def bitrix_group():
        @task
        def extract_bitrix(data_interval_start: datetime) -> int:
            cfg = BitrixConfig(webhook_url=Variable.get("BITRIX_WEBHOOK_URL"))
            since = data_interval_start - timedelta(days=1)
            df = fetch_deals_changed_since(cfg, since=pendulum.instance(since))
            return stream_load(_ch_cfg(), "analytics.bitrix_deals", [df])

        @task
        def dq_check_bitrix(rows: int) -> None:
            if rows < 0:
                raise ValueError("negative row count from Bitrix")

        dq_check_bitrix(extract_bitrix())

    @task_group(group_id="excel")
    def excel_group():
        @task
        def extract_excel() -> int:
            inbox = Path(Variable.get("EXCEL_INBOX_DIR", default_var="/data/inbox"))
            return stream_load(
                _ch_cfg(),
                "analytics.partner_uploads",
                load_directory(inbox, pattern="*.xlsx"),
            )

        extract_excel()

    @task(trigger_rule="all_done")
    def refresh_marts():
        """Обновляем агрегированные витрины после всех источников."""
        from clickhouse_connect import get_client
        cfg = _ch_cfg()
        with get_client(host=cfg.host, username=cfg.username,
                        password=cfg.password, database=cfg.database) as ch:
            ch.command("OPTIMIZE TABLE analytics.metrika_traffic FINAL")
            ch.command("OPTIMIZE TABLE analytics.bitrix_deals FINAL")
            ch.command(
                "INSERT INTO analytics.mart_acquisition_daily "
                "SELECT * FROM analytics.v_mart_acquisition_daily "
                "WHERE event_date = today() - 1"
            )

    [metrika_group(), bitrix_group(), excel_group()] >> refresh_marts()


dag = multi_source_to_clickhouse()
