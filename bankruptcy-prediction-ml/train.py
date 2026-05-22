"""
Bankruptcy / firm-exit prediction on the RFSD dataset
=====================================================

Dataset: https://huggingface.co/datasets/irlspbru/RFSD
(Russian Financial Statements Database, ~60M rows, 213 columns).

The dataset does NOT contain an explicit 'bankruptcy' label. Instead, we use
`dissolution_date` as a proxy for firm exit: a company is considered
"exited" if it has a non-null `dissolution_date` within a given snapshot year.
This is a common approximation used in firm-survival research.

Pipeline:
  1. Stream a sample from the HF parquet dataset (we don't load all 60M rows).
  2. Build a binary target (exited within next N years after report date).
  3. Compute classic financial ratios from the 'line_*' balance-sheet items.
  4. Train Logistic Regression, Random Forest and Gradient Boosting baselines.
  5. Evaluate with ROC-AUC, F1, precision/recall and confusion matrix.

Run:
    python train.py --sample-rows 500000 --year 2018 --horizon 3

Note: the full dataset is ~60M rows. Use --sample-rows to keep memory in check.
"""

from __future__ import annotations

import argparse
import warnings
from pathlib import Path

import numpy as np
import pandas as pd
from sklearn.compose import ColumnTransformer
from sklearn.ensemble import GradientBoostingClassifier, RandomForestClassifier
from sklearn.impute import SimpleImputer
from sklearn.linear_model import LogisticRegression
from sklearn.metrics import (
    classification_report,
    confusion_matrix,
    f1_score,
    roc_auc_score,
)
from sklearn.model_selection import train_test_split
from sklearn.pipeline import Pipeline
from sklearn.preprocessing import StandardScaler

warnings.filterwarnings("ignore", category=UserWarning)

RANDOM_STATE = 42


# ---------------------------------------------------------------------------
# Data loading
# ---------------------------------------------------------------------------

def load_rfsd_sample(n_rows: int = 500_000) -> pd.DataFrame:
    """Load a streaming sample from the RFSD dataset on Hugging Face.

    We rely on `datasets.load_dataset(..., streaming=True)` so that we do not
    download all 60M rows. Rows are taken in order; for a more representative
    sample you can pass `shuffle=True` to .shuffle() with a buffer.
    """
    from datasets import load_dataset

    ds = load_dataset(
        "irlspbru/RFSD",
        split="train",
        streaming=True,
    )

    rows = []
    for i, row in enumerate(ds):
        rows.append(row)
        if i + 1 >= n_rows:
            break
    return pd.DataFrame(rows)


# ---------------------------------------------------------------------------
# Target construction
# ---------------------------------------------------------------------------

def build_target(df: pd.DataFrame, year: int, horizon: int) -> pd.DataFrame:
    """Create a binary 'exited' target.

    A firm is labeled 1 if it has a dissolution_date no later than
    `year + horizon` (inclusive). Firms that survived past that horizon — or
    are still active — get label 0.

    We also filter to rows that look like a financial report for `year`.
    """
    df = df.copy()
    df["dissolution_date"] = pd.to_datetime(df["dissolution_date"], errors="coerce")
    df["creation_date"] = pd.to_datetime(df["creation_date"], errors="coerce")

    # Keep only firms that existed during the target year
    mask_existed = (
        (df["creation_date"].dt.year <= year)
        & ((df["dissolution_date"].isna()) | (df["dissolution_date"].dt.year >= year))
    )
    df = df.loc[mask_existed].copy()

    horizon_end = pd.Timestamp(f"{year + horizon}-12-31")
    df["exited"] = (
        df["dissolution_date"].notna() & (df["dissolution_date"] <= horizon_end)
    ).astype(int)
    return df


# ---------------------------------------------------------------------------
# Feature engineering
# ---------------------------------------------------------------------------

# Selected balance-sheet & P&L lines (Russian RAS chart of accounts)
BALANCE_SHEET_LINES = {
    "current_assets":      "line_1200",   # оборотные активы
    "total_assets":        "line_1600",   # итого активы
    "cash":                "line_1250",   # денежные средства
    "inventory":           "line_1210",   # запасы
    "receivables":         "line_1230",   # дебиторская задолженность
    "equity":              "line_1300",   # итого капитал
    "long_term_liab":      "line_1400",   # долгосрочные обязательства
    "short_term_liab":     "line_1500",   # краткосрочные обязательства
    "revenue":             "line_2110",   # выручка
    "gross_profit":        "line_2100",   # валовая прибыль
    "operating_profit":    "line_2200",   # прибыль от продаж
    "net_profit":          "line_2400",   # чистая прибыль
}


def _safe_div(num: pd.Series, den: pd.Series) -> pd.Series:
    return num / den.replace(0, np.nan)


def compute_financial_ratios(df: pd.DataFrame) -> pd.DataFrame:
    """Compute classic solvency / profitability / liquidity ratios."""
    df = df.copy()
    cols = BALANCE_SHEET_LINES
    for alias, col in cols.items():
        if col not in df.columns:
            df[col] = np.nan
        df[alias] = pd.to_numeric(df[col], errors="coerce")

    # Liquidity
    df["current_ratio"] = _safe_div(df["current_assets"], df["short_term_liab"])
    df["cash_ratio"] = _safe_div(df["cash"], df["short_term_liab"])

    # Leverage
    total_liab = df["long_term_liab"].fillna(0) + df["short_term_liab"].fillna(0)
    df["debt_to_assets"] = _safe_div(total_liab, df["total_assets"])
    df["debt_to_equity"] = _safe_div(total_liab, df["equity"])

    # Profitability
    df["roa"] = _safe_div(df["net_profit"], df["total_assets"])
    df["roe"] = _safe_div(df["net_profit"], df["equity"])
    df["net_margin"] = _safe_div(df["net_profit"], df["revenue"])
    df["operating_margin"] = _safe_div(df["operating_profit"], df["revenue"])

    # Turnover
    df["asset_turnover"] = _safe_div(df["revenue"], df["total_assets"])

    # Misc
    df["log_assets"] = np.log1p(df["total_assets"].clip(lower=0))
    df["log_revenue"] = np.log1p(df["revenue"].clip(lower=0))

    return df


FEATURE_COLS = [
    "current_ratio",
    "cash_ratio",
    "debt_to_assets",
    "debt_to_equity",
    "roa",
    "roe",
    "net_margin",
    "operating_margin",
    "asset_turnover",
    "log_assets",
    "log_revenue",
    "age",
]


# ---------------------------------------------------------------------------
# Modeling
# ---------------------------------------------------------------------------

def build_models() -> dict[str, Pipeline]:
    pre = ColumnTransformer(
        transformers=[
            ("num", Pipeline([
                ("imputer", SimpleImputer(strategy="median")),
                ("scaler", StandardScaler()),
            ]), FEATURE_COLS),
        ]
    )

    return {
        "logreg": Pipeline([
            ("pre", pre),
            ("clf", LogisticRegression(max_iter=500, class_weight="balanced",
                                        random_state=RANDOM_STATE)),
        ]),
        "random_forest": Pipeline([
            ("pre", pre),
            ("clf", RandomForestClassifier(
                n_estimators=300,
                max_depth=12,
                min_samples_leaf=50,
                class_weight="balanced",
                n_jobs=-1,
                random_state=RANDOM_STATE,
            )),
        ]),
        "grad_boost": Pipeline([
            ("pre", pre),
            ("clf", GradientBoostingClassifier(
                n_estimators=200,
                max_depth=3,
                random_state=RANDOM_STATE,
            )),
        ]),
    }


def evaluate(name: str, model: Pipeline, X_test, y_test) -> dict:
    proba = model.predict_proba(X_test)[:, 1]
    preds = (proba >= 0.5).astype(int)
    auc = roc_auc_score(y_test, proba)
    f1 = f1_score(y_test, preds)
    print(f"\n=== {name} ===")
    print(f"ROC-AUC: {auc:.4f} | F1: {f1:.4f}")
    print(classification_report(y_test, preds, digits=3))
    print("Confusion matrix:")
    print(confusion_matrix(y_test, preds))
    return {"name": name, "roc_auc": auc, "f1": f1}


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--sample-rows", type=int, default=200_000,
                        help="How many rows to pull from the streaming dataset.")
    parser.add_argument("--year", type=int, default=2018,
                        help="Snapshot year for the financial report.")
    parser.add_argument("--horizon", type=int, default=3,
                        help="Horizon (in years) for the 'exited' label.")
    parser.add_argument("--out", type=Path, default=Path("results.csv"),
                        help="Where to save the metrics summary.")
    args = parser.parse_args()

    print(f"Loading {args.sample_rows:,} rows from RFSD ...")
    df = load_rfsd_sample(args.sample_rows)
    print(f"  loaded shape: {df.shape}")

    print(f"Building target for year={args.year}, horizon={args.horizon} ...")
    df = build_target(df, args.year, args.horizon)
    print(f"  positives (exited): {df['exited'].sum():,} / {len(df):,}")

    print("Computing financial ratios ...")
    df = compute_financial_ratios(df)

    X = df[FEATURE_COLS]
    y = df["exited"]

    X_train, X_test, y_train, y_test = train_test_split(
        X, y, test_size=0.25, stratify=y, random_state=RANDOM_STATE
    )

    results = []
    for name, model in build_models().items():
        print(f"\nTraining {name} ...")
        model.fit(X_train, y_train)
        results.append(evaluate(name, model, X_test, y_test))

    pd.DataFrame(results).to_csv(args.out, index=False)
    print(f"\nSaved metrics summary to {args.out}")


if __name__ == "__main__":
    main()
