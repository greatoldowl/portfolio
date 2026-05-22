# Прогнозирование банкротства компаний

Кейс из стажировки в **НИФИ** + воспроизводимый пример на открытом датасете [RFSD](https://huggingface.co/datasets/irlspbru/RFSD) (Russian Financial Statements Database, ~60M строк).

## Идея
В RFSD нет явной метки «банкрот / не банкрот», но есть `dissolution_date`. Мы используем её как прокси: фирма помечается как «вышедшая» (`exited=1`), если она была ликвидирована не позже горизонта прогноза (например, `year + 3`). Такой подход к выживаемости фирм — классика финансовой эконометрики.

## Что внутри
- `train.py` — end-to-end скрипт:
  - стриминговая загрузка нужного количества строк из HF (`datasets` + `streaming=True`),
  - построение бинарной метки `exited` на заданный год и горизонт,
  - feature engineering: ликвидность (current/cash ratio), леверидж (debt-to-assets/equity), рентабельность (ROA, ROE, маржи), оборачиваемость, лог-размер,
  - обучение **Logistic Regression / Random Forest / Gradient Boosting** через `Pipeline` + `ColumnTransformer`,
  - оценка по ROC-AUC, F1, classification_report, confusion matrix.
- `requirements.txt` — зависимости.

## Как запустить

```bash
pip install -r requirements.txt
python train.py --sample-rows 200000 --year 2018 --horizon 3
```

Опции:
- `--sample-rows` — сколько строк подтянуть из HF (по умолчанию 200k, чтобы влезало в память ноутбука).
- `--year` — отчётный год.
- `--horizon` — горизонт прогноза в годах.

Результаты моделей сохраняются в `results.csv`.

## Из реального опыта (НИФИ)
- Работал с датасетом ~600 млн строк бухгалтерской и финансовой отчётности.
- Оптимизировал тяжёлые SQL-запросы: CTE, оконные функции, индексы, партиционирование, `EXPLAIN ANALYZE`.
- Делал предобработку и feature engineering в Python (pandas, numpy).
- Обучал ML-модели (sklearn): logreg, деревья, бустинги; сравнивал по ROC-AUC, precision/recall, F1.
- Готовил витрины данных для BI-отчётов и входные наборы для ML.

## Стек
Python (pandas, numpy, scikit-learn, matplotlib), SQL (PostgreSQL, ClickHouse), Hugging Face Datasets, Git.
