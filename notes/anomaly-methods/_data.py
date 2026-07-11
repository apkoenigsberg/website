# Shared loader for the anomaly-methods teaching series.
import re
from pathlib import Path

import numpy as np
import pandas as pd
import matplotlib.pyplot as plt

HERE = Path(__file__).parent
CSV = (HERE / "../../posts/2026-04-17-imts-exploratory/"
       "dataset_2026-04-19T01_51_08.510445992Z_DEFAULT_INTEGRATION_IMF.STA_IMTS_1.0.0.csv")

NAMES = {"UKR": "Ukraine", "VEN": "Venezuela", "YEM": "Yemen", "MEX": "Mexico"}

EVENTS = {  # for orienting charts
    "UKR": [("2022-02", "invasion")],
    "VEN": [("2019-01", "sanctions")],
    "MEX": [("2020-03", "COVID")],
}


def load_levels(countries=("UKR", "VEN", "YEM", "MEX")):
    """Monthly goods exports to world (XG_FOB_USD, partner G001), USD millions."""
    cols = pd.read_csv(CSV, nrows=0).columns.tolist()
    mcols = [c for c in cols if re.match(r"^\d{4}-M\d{2}$", c)]
    raw = pd.read_csv(CSV, usecols=["SERIES_CODE"] + mcols, dtype=str)
    parts = raw["SERIES_CODE"].str.split(".", n=3, expand=True)
    parts.columns = ["reporter", "indicator", "partner", "freq"]
    df = pd.concat([parts, raw[mcols]], axis=1)
    df = df[(df["freq"] == "M") & (df["indicator"] == "XG_FOB_USD")
            & (df["partner"] == "G001") & (df["reporter"].isin(countries))]
    df[mcols] = df[mcols].apply(pd.to_numeric, errors="coerce")
    dates = pd.to_datetime([c.replace("-M", "-") + "-01" for c in mcols])
    out = pd.DataFrame(
        {c: df[df["reporter"] == c][mcols].sum().values for c in countries},
        index=dates,
    )
    return out.replace(0, np.nan)


def setup_plots():
    plt.rcParams.update({
        "figure.dpi": 150, "axes.spines.top": False, "axes.spines.right": False,
        "font.size": 9, "axes.titlesize": 11, "axes.titleweight": "bold",
        "figure.facecolor": "#fafafa", "axes.facecolor": "#fafafa",
    })


def mark_events(ax, code):
    for date, label in EVENTS.get(code, []):
        ax.axvline(pd.Timestamp(date + "-01"), color="#e45756", ls="--", lw=1.0, alpha=0.7)
        ax.text(pd.Timestamp(date + "-01"), ax.get_ylim()[1], f" {label}",
                fontsize=7, color="#e45756", va="top")
