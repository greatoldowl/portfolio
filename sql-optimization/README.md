# SQL Optimization

Подборка реальных приёмов, которыми пользуюсь, когда медленный запрос доходит до бэклога. Все примеры — синтетические, но паттерны взяты из рабочей практики.

## Файлы

| Файл | Суть |
|------|------|
| [01_join_optimization.sql](01_join_optimization.sql) | Агрегируем факт до объединения с дименшенами; 8 мин → 30 сек, x7 по памяти. |
| [02_window_functions_vs_self_join.sql](02_window_functions_vs_self_join.sql) | Коррелированный self-join → LAG/LEAD в оконной функции. Бонусом — когорты без лишних join'ов. |
| [03_clickhouse_partitioning_and_skip_index.sql](03_clickhouse_partitioning_and_skip_index.sql) | Правильный PARTITION BY и ORDER BY в MergeTree, bloom-filter, матвью SummingMergeTree. |
| [04_postgres_indexes_and_explain.sql](04_postgres_indexes_and_explain.sql) | EXPLAIN ANALYZE workflow, составные и частичные индексы, BRIN, autovacuum-тюнинг. |

## Общий подход
1. **Сначала измерить.** Смотрю EXPLAIN/EXPLAIN ANALYZE, сравниваю факт и оценку планировщика.
2. **Снижать объём до join'а.** Агрегация и фильтры на факт — раньше, чем объединение с дименшенами.
3. **Индекс под запрос.** Композит + INCLUDE/partial, порядок колонок по селективности.
4. **Окна вместо самосоединений.** LAG/LEAD, ROW_NUMBER, SUM() OVER — один проход вместо N².
5. **Материализованные витрины.** Агрегаты для дашбордов живут в SummingMergeTree / matview, а не пересчитываются каждый раз.
6. **Свежая статистика.** ANALYZE / OPTIMIZE после бэкфиллов.
