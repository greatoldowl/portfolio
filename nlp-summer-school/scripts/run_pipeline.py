"""Command-line pipeline for the search-and-rescue dataset.

Usage:
    python -m scripts.run_pipeline data/filled_all_data.csv \
        --plots-dir plots --classify
"""

from __future__ import annotations

import argparse
from pathlib import Path

from lizaalert.classify import train_and_evaluate
from lizaalert.data import explode_ages, normalise, read_csv_safely
from lizaalert.visualization import (
    age_status_bars,
    demographic_pyramid,
    gender_pie,
)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("data", type=Path, help="Path to filled_all_data.csv")
    parser.add_argument("--plots-dir", type=Path, default=Path("plots"))
    parser.add_argument(
        "--classify",
        action="store_true",
        help="Train the жив/погиб classification baseline as well.",
    )
    args = parser.parse_args()

    df = read_csv_safely(args.data)
    df = normalise(df)
    df_long = explode_ages(df)

    args.plots_dir.mkdir(parents=True, exist_ok=True)
    gender_pie(df_long).savefig(args.plots_dir / "gender_pie.png", dpi=150)
    age_status_bars(df_long).savefig(args.plots_dir / "age_status_bars.png", dpi=150)
    demographic_pyramid(df_long).savefig(args.plots_dir / "demographic_pyramid.png", dpi=150)
    print(f"Saved plots to {args.plots_dir.resolve()}")

    if args.classify:
        results = train_and_evaluate(df_long)
        print()
        for r in results:
            print(f"=== {r.name} === ROC-AUC={r.roc_auc:.3f} F1={r.f1:.3f}")
            print(r.report)


if __name__ == "__main__":
    main()
