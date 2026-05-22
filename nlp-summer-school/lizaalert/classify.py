"""Classification baseline: жив(а) vs погиб(ла).

Refactor of `classificstion_dead_alive.ipynb` (sic) into a single
function that returns a trained sklearn Pipeline and a metrics dict.

Improvements over the original notebook:
  - no hard-coded local CSV paths;
  - features are passed in explicitly, no implicit drops;
  - categorical columns go through OneHotEncoder, not LabelEncoder
    (LabelEncoder is for the target, not for features);
  - models are wrapped in Pipelines with proper imputation and scaling;
  - class imbalance is handled via class_weight='balanced'
    instead of arbitrary downsampling to 2000 rows.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Iterable

import numpy as np
import pandas as pd
from sklearn.compose import ColumnTransformer
from sklearn.ensemble import RandomForestClassifier
from sklearn.impute import SimpleImputer
from sklearn.linear_model import LogisticRegression
from sklearn.metrics import (
    classification_report,
    confusion_matrix,
    f1_score,
    roc_auc_score,
)
from sklearn.model_selection import train_test_split
from sklearn.neighbors import KNeighborsClassifier
from sklearn.pipeline import Pipeline
from sklearn.preprocessing import OneHotEncoder, StandardScaler
from sklearn.tree import DecisionTreeClassifier


RANDOM_STATE = 42


@dataclass
class ClassificationResult:
    name: str
    roc_auc: float
    f1: float
    report: str
    confusion: np.ndarray


def build_pipeline(
    model,
    numeric_features: Iterable[str],
    categorical_features: Iterable[str],
) -> Pipeline:
    pre = ColumnTransformer([
        ("num", Pipeline([
            ("imputer", SimpleImputer(strategy="median")),
            ("scaler", StandardScaler()),
        ]), list(numeric_features)),
        ("cat", Pipeline([
            ("imputer", SimpleImputer(strategy="most_frequent")),
            ("onehot", OneHotEncoder(handle_unknown="ignore", min_frequency=10)),
        ]), list(categorical_features)),
    ])
    return Pipeline([("pre", pre), ("clf", model)])


def train_and_evaluate(
    df: pd.DataFrame,
    *,
    target_col: str = "status",
    positive: str = "погиб(ла)",
    negative: str = "жив(а)",
    numeric_features: Iterable[str] = (
        "age",
        "date_search_year",
        "date_search_month",
        "date_search_day",
    ),
    categorical_features: Iterable[str] = ("gender_norm", "location"),
    test_size: float = 0.25,
) -> list[ClassificationResult]:
    """Train baseline classifiers on a balanced binary target.

    Returns a list of :class:`ClassificationResult`, one per model.
    """
    df = df[df[target_col].isin([positive, negative])].copy()
    df["_target"] = (df[target_col] == positive).astype(int)

    feature_cols = list(numeric_features) + list(categorical_features)
    feature_cols = [c for c in feature_cols if c in df.columns]
    numeric_features = [c for c in numeric_features if c in df.columns]
    categorical_features = [c for c in categorical_features if c in df.columns]

    X = df[feature_cols]
    y = df["_target"]

    X_train, X_test, y_train, y_test = train_test_split(
        X, y, test_size=test_size, stratify=y, random_state=RANDOM_STATE
    )

    models = {
        "logreg": LogisticRegression(
            max_iter=500, class_weight="balanced", random_state=RANDOM_STATE
        ),
        "knn": KNeighborsClassifier(n_neighbors=15),
        "decision_tree": DecisionTreeClassifier(
            max_depth=10, class_weight="balanced", random_state=RANDOM_STATE
        ),
        "random_forest": RandomForestClassifier(
            n_estimators=300,
            max_depth=12,
            class_weight="balanced",
            n_jobs=-1,
            random_state=RANDOM_STATE,
        ),
    }

    results: list[ClassificationResult] = []
    for name, model in models.items():
        pipe = build_pipeline(model, numeric_features, categorical_features)
        pipe.fit(X_train, y_train)

        proba = (
            pipe.predict_proba(X_test)[:, 1]
            if hasattr(pipe.named_steps["clf"], "predict_proba")
            else pipe.decision_function(X_test)
        )
        preds = (proba >= 0.5).astype(int) if proba.dtype != int else proba

        results.append(
            ClassificationResult(
                name=name,
                roc_auc=roc_auc_score(y_test, proba),
                f1=f1_score(y_test, preds),
                report=classification_report(y_test, preds, digits=3),
                confusion=confusion_matrix(y_test, preds),
            )
        )

    return results
