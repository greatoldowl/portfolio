"""Plots for the search-and-rescue dataset.

Each public function returns a `matplotlib.figure.Figure`, making it
trivial to either display interactively or save to a file.
"""

from __future__ import annotations

import matplotlib.colors as mcolors
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
from matplotlib.figure import Figure

# ---------------------------------------------------------------------------
# Palette
# ---------------------------------------------------------------------------

MALE_BASE = "#97CCE8"
FEMALE_BASE = "#FAA4B0"
MISC_BASE = "#9E9E9E"

STATUS_ALPHA = {
    "жив": 1.0,
    "пропал/nan": 0.6,
    "мертв": 0.3,
}


def _palette(base: str) -> dict[str, tuple]:
    return {s: mcolors.to_rgba(base, alpha=a) for s, a in STATUS_ALPHA.items()}


# ---------------------------------------------------------------------------
# Gender pie chart
# ---------------------------------------------------------------------------

def gender_pie(df: pd.DataFrame, gender_col: str = "gender_norm") -> Figure:
    """Pie chart of {муж, жен, мн} counts."""
    labels_map = {"муж": "Мужчины", "жен": "Женщины", "мн": "Несколько человек"}
    colors_map = {"муж": MALE_BASE, "жен": FEMALE_BASE, "мн": MISC_BASE}

    counts = (
        df[gender_col]
        .dropna()
        .pipe(lambda s: s[s.isin(labels_map)])
        .value_counts()
    )

    fig, ax = plt.subplots(figsize=(8, 8))
    ax.pie(
        counts.values,
        labels=[labels_map[g] for g in counts.index],
        colors=[colors_map[g] for g in counts.index],
        autopct="%1.1f%%",
        startangle=90,
        counterclock=False,
        textprops={"fontsize": 13},
        pctdistance=0.75,
    )
    ax.set_title("Гендерное распределение")
    return fig


# ---------------------------------------------------------------------------
# Age × status bar chart
# ---------------------------------------------------------------------------

def age_status_bars(
    df_long: pd.DataFrame,
    age_col: str = "age",
    status_col: str = "status",
) -> Figure:
    """Stacked bar chart: count by integer age, split by status."""
    pivot = (
        df_long.groupby([age_col, status_col]).size().unstack(fill_value=0)
    )
    for col in ("пропал(а)", "жив(а)", "погиб(ла)"):
        if col not in pivot.columns:
            pivot[col] = 0
    pivot = pivot[["пропал(а)", "жив(а)", "погиб(ла)"]]

    fig, ax = plt.subplots(figsize=(14, 6))
    pivot.plot(
        kind="bar",
        stacked=True,
        ax=ax,
        color=["#9E9E9E", "#7BB661", "#C0392B"],
        width=0.9,
    )
    ax.set_xlabel("Возраст")
    ax.set_ylabel("Кол-во записей")
    ax.set_title("Распределение по возрасту и статусу")
    ax.legend(title="Статус")
    fig.tight_layout()
    return fig


# ---------------------------------------------------------------------------
# Demographic pyramid
# ---------------------------------------------------------------------------

def _simplify_status(s: str) -> str:
    if s == "жив(а)":
        return "жив"
    if s == "погиб(ла)":
        return "мертв"
    return "пропал/nan"


def demographic_pyramid(
    df_long: pd.DataFrame,
    age_col: str = "age",
    gender_col: str = "gender_norm",
    status_col: str = "status",
) -> Figure:
    """Demographic pyramid: men on the right, women on the left."""
    df = df_long.copy()
    df = df[df[gender_col].isin(["муж", "жен"])]
    df["_status"] = df[status_col].fillna("nan").map(_simplify_status)

    grouped = df.groupby([age_col, gender_col, "_status"]).size().reset_index(name="n")
    pivot = grouped.pivot_table(
        index=age_col,
        columns=[gender_col, "_status"],
        values="n",
        fill_value=0,
    )
    ages = sorted(pivot.index.unique())

    fig, ax = plt.subplots(figsize=(12, 16))
    male_pal = _palette(MALE_BASE)
    female_pal = _palette(FEMALE_BASE)

    widths_male = np.zeros(len(ages))
    widths_female = np.zeros(len(ages))

    for status in ("жив", "пропал/nan", "мертв"):
        m = pivot.get(("муж", status), pd.Series(0, index=ages)).reindex(ages, fill_value=0)
        f = pivot.get(("жен", status), pd.Series(0, index=ages)).reindex(ages, fill_value=0)

        ax.barh(ages, m, left=widths_male, color=male_pal[status], label=f"муж · {status}")
        ax.barh(ages, -f, left=-widths_female, color=female_pal[status], label=f"жен · {status}")
        widths_male += m.values
        widths_female += f.values

    ax.axvline(0, color="black", linewidth=0.8)
    ax.set_xlabel("Кол-во (← женщины · мужчины →)")
    ax.set_ylabel("Возраст")
    ax.set_title("Демографическая пирамида")
    ax.legend(loc="lower right", fontsize=9)
    fig.tight_layout()
    return fig
