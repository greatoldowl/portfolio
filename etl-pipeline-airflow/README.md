# ETL Pipeline (Airflow + ClickHouse)

Оркестрация выгрузки из разных источников в ClickHouse с последующей публикацией в BI-витрины.

## Источники
- **Yandex.Metrika Reporting API** — визиты, каналы, goals, retention.
- **Bitrix24 REST (webhook)** — сделки, лиды, задачи, контакты.
- **Excel-файлы** — выгрузки от партнёров и локальные реестры.

## Ключевые решения
- **Идемпотентность через REPLACE PARTITION.** Любой перезапуск за день — атомарно заменяет партицию, без дублей.
- **Retry с backoff** в экстракторах и на уровне Airflow tasks.
- **TaskGroups** на каждый источник — падение одного не валит остальные.
- **DQ-проверки** перед публикацией в витрины.
- **Секреты** в Airflow Variables / Connections, в коде ничего хардкоденного.

## Структура

```
etl-pipeline-airflow/
├── dags/
│   └── multi_source_to_clickhouse.py   # основной DAG (@daily)
├── etl/
│   ├── extractors/
│   │   ├── yandex_metrika.py          # Reporting API + retry
│   │   ├── bitrix24.py                # REST webhook + cursor pagination
│   │   └── excel_files.py             # .xlsx с нормализацией хедеров
│   └── loaders/
│       └── clickhouse_loader.py       # REPLACE PARTITION + stream load
└── requirements.txt
```

## Запуск локально
1. Поднять Airflow (docker compose / astronomer-cosmos / venv — любой вариант).
2. Положить папку `dags/` в AIRFLOW_HOME, а `etl/` — в PYTHONPATH.
3. Завести переменные (Airflow Variables):
   `METRIKA_COUNTER_ID`, `METRIKA_TOKEN`, `BITRIX_WEBHOOK_URL`,
   `EXCEL_INBOX_DIR`, `CH_HOST`, `CH_USER`, `CH_PASSWORD`, `CH_DB`.
4. Включить DAG `multi_source_to_clickhouse`.

## Дальнейшее развитие
- Перевести SQL-витрины под dbt.
- Добавить Great Expectations / Soda для проверок качества.
- Настроить алерты в Telegram из on_failure_callback.
