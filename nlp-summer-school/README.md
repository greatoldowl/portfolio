# NLP — Летняя школа (LizaAlert)

Проект в рамках **мастерской анализа текстовых данных** (Летняя школа, 2025) по данным поисково-спасательного отряда «ЛизаАлерт». Этот раздел — **рефакторинг** оригинального проекта [greatoldowl/LizaAlertPAnDan](https://github.com/greatoldowl/LizaAlertPAnDan): тот же датасет, но код переписан в виде аккуратного пакета.

## Что улучшено по сравнению с оригиналом
- Один пакет вместо разрозненных `.py` и `.ipynb` файлов.
- Регулярки для статуса вынесены в `parsing.py` и работают через `re.IGNORECASE` + словесные границы.
- Гендерная нормализация — единая функция `normalise_gender`, корректно обрабатывает списки и `мн`.
- Парсинг возраста (`"[7, 18]"`, `"35"`, `"около 40"`) собран в `parse_age` с одним публичным API.
- Чтение CSV умеет автоматически выбирать между utf-8 и cp1251.
- Графики возвращают `Figure`, а не дёргают `plt.show()` посередине функций — удобно для тестов и для сохранения в файл.
- Классификация: вместо `LabelEncoder` на признаках — `OneHotEncoder` через `ColumnTransformer`; вместо ручного даунсэмплинга до 2000 строк — `class_weight="balanced"`; модели обёрнуты в `Pipeline` с правильной импутацией и масштабированием.

## Структура

```
nlp-summer-school/
├── lizaalert/
│   ├── __init__.py
│   ├── parsing.py         # detect_status / normalise_gender / parse_age
│   ├── data.py            # read_csv_safely / normalise / explode_ages
│   ├── visualization.py   # gender_pie / age_status_bars / demographic_pyramid
│   └── classify.py        # train_and_evaluate (logreg / KNN / DT / RF)
├── scripts/
│   └── run_pipeline.py    # CLI: строит графики и (опционально) учит модели
├── requirements.txt
└── README.md
```

## Как запустить

```bash
pip install -r requirements.txt
python -m scripts.run_pipeline path/to/filled_all_data.csv --plots-dir plots --classify
```

В `plots/` появятся: `gender_pie.png`, `age_status_bars.png`, `demographic_pyramid.png`. С флагом `--classify` также напечатается сравнение моделей по ROC-AUC и F1.

## Стек
Python (pandas, numpy, scikit-learn, matplotlib), регулярные выражения.

## Источник данных
Датасет собран в рамках проекта Летней школы по постам отряда «ЛизаАлерт». Исходный код анализа: [greatoldowl/LizaAlertPAnDan](https://github.com/greatoldowl/LizaAlertPAnDan).
