"""Rebuild data/readings.parquet from every logger export in Raw/.

Raw/ is the source of truth: the whole dataset is regenerated on each run, so
overlapping exports, renamed stations and parser fixes never leave stale rows.
"""
from pathlib import Path

import pandas as pd

from . import hobo, zl6
from .common import COLUMNS

ROOT = Path(__file__).resolve().parents[1]
RAW_DIR = ROOT / "Raw"
DATA_DIR = ROOT / "data"
READINGS = DATA_DIR / "readings.parquet"
STATIONS = DATA_DIR / "stations.csv"

PARSERS = [hobo, zl6]

# Readings of one series closer together than this are the same sample: overlapping exports of a
# logger can disagree on a sample's time by a second. Loggers sample every 5 minutes or more.
SAME_SAMPLE = pd.Timedelta("30s")
STATION_COLUMNS = ["station_id", "name", "logger_id", "logger_model", "latitude", "longitude", "description"]


def parse_file(path):
    xl = pd.ExcelFile(path)
    for parser in PARSERS:
        if parser.matches(xl.sheet_names):
            return parser.parse(xl)
    raise ValueError(f"unrecognised export format: {path.name}")


def update_stations(loggers):
    """Add any new logger to stations.csv, keeping edits made by hand to existing rows."""
    if STATIONS.exists():
        stations = pd.read_csv(STATIONS, dtype={"logger_id": str})
    else:
        stations = pd.DataFrame(columns=STATION_COLUMNS)
    new = [lg for lg in loggers.values() if lg["logger_id"] not in set(stations["logger_id"])]
    if new:
        stations = pd.concat([stations, pd.DataFrame(new, columns=STATION_COLUMNS)], ignore_index=True)
        for lg in new:
            print(f"  new station {lg['station_id']!r} (logger {lg['logger_id']}) added to {STATIONS.name}")
    stations.to_csv(STATIONS, index=False)
    return dict(zip(stations["logger_id"], stations["station_id"]))


def drop_repeats(readings):
    """Keep one reading per sample where exports overlap, taking it from the most recent export."""
    series = ["station_id", "variable", "depth_cm"]
    readings = readings.sort_values([*series, "timestamp_utc"], ignore_index=True)
    step = readings.groupby(series, dropna=False)["timestamp_utc"].diff()
    sample = (step.isna() | (step >= SAME_SAMPLE)).cumsum()
    return readings.loc[readings.groupby(sample)["export"].idxmax()]


def main():
    files = sorted(p for p in RAW_DIR.glob("*.xlsx") if not p.name.startswith("~$"))
    loggers, parts = {}, []
    for path in files:
        print(f"reading {path.name}")
        logger, readings = parse_file(path)
        loggers.setdefault(logger["logger_id"], logger)
        parts.append(readings.assign(logger_id=logger["logger_id"]))

    DATA_DIR.mkdir(exist_ok=True)
    station_of = update_stations(loggers)

    # Rank exports by how recent their data is (file dates change when files are copied).
    parts.sort(key=lambda part: part["timestamp_utc"].max())
    readings = pd.concat([part.assign(export=i) for i, part in enumerate(parts)], ignore_index=True)
    readings["station_id"] = readings.pop("logger_id").map(station_of)
    readings["depth_cm"] = readings["depth_cm"].astype("Int16")
    readings = drop_repeats(readings)[COLUMNS].reset_index(drop=True)
    readings.to_parquet(READINGS, index=False)

    print(f"\nwrote {len(readings):,} readings to {READINGS.relative_to(ROOT)}")
    summary = readings.groupby("station_id").agg(
        start=("timestamp_utc", "min"), end=("timestamp_utc", "max"),
        variables=("variable", "nunique"), readings=("value", "size"),
    )
    print(summary.to_string())
