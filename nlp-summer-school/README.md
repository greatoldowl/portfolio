# NLP — анализ данных поисково-спасательных операций

Прикладной проект по обработке текстовых данных поисково-спасательного отряда: парсинг постов о пропавших людях, очистка и нормализация датасета, визуальная аналитика и базовый ML-классификатор исхода поиска.

## Что внутри

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

## Парсинг и нормализация

- Регулярные выражения вытаскивают статус (`жив(а)` / `погиб(ла)` / `пропал(а)`) из текста объявлений.
- Гендерные метки сводятся к единому словарю `{муж, жен, мн}`.
- Поле возраста (бывает строкой, числом, списком вида `"[7, 18]"` или свободным текстом) парсится в список целых; затем датафрейм разворачивается «по возрастам».
- CSV-загрузчик умеет переключаться между utf-8 и cp1251.

## Визуализация

Три графика, каждый возвращает `matplotlib.figure.Figure`:
- круговая диаграмма по полу;
- стэкбары «возраст × статус»;
- демографическая пирамида с разбивкой по статусу.

## ML-классификация

Бинарная задача «жив(а) vs погиб(ла)»:
- препроцессинг через `ColumnTransformer` (median-импутация и стандартизация для числовых, OneHot для категориальных);
- модели: Logistic Regression, KNN, Decision Tree, Random Forest;
- дисбаланс классов — через `class_weight="balanced"`;
- метрики: ROC-AUC, F1, classification_report, confusion matrix.

## Как запустить

```bash
pip install -r requirements.txt
python -m scripts.run_pipeline path/to/filled_all_data.csv --plots-dir plots --classify
```

В `plots/` появятся: `gender_pie.png`, `age_status_bars.png`, `demographic_pyramid.png`. С флагом `--classify` также будет напечатано сравнение моделей по ROC-AUC и F1.

## Стек
Python (pandas, numpy, scikit-learn, matplotlib), регулярные выражения.
