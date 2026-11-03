"""Load the dataset built by `python -m ingest` and describe what it holds."""
import html
from pathlib import Path

import pandas as pd
import streamlit as st

ROOT = Path(__file__).resolve().parents[1]
READINGS = ROOT / "data" / "readings.parquet"
STATIONS = ROOT / "data" / "stations.csv"

# All gauges are in Florida; times are shown in local time.
TIMEZONE = "America/New_York"

# Display names where the snake_case variable name doesn't read well.
LABELS = {
    "max_precip_rate": "Max precipitation rate",
    "precipitation": "Rainfall",
    "temperature": "Water temperature",  # measured by the submerged water level loggers
}


def label(variable, depth_cm=None):
    """'water_content', 15 -> 'Water content at 15 cm'."""
    name = LABELS.get(variable, variable.replace("_", " ").capitalize())
    return f"{name} at {depth_cm} cm" if depth_cm is not None else name


def _version():
    """Changes whenever ingest rewrites the data, so cached results are refreshed."""
    return READINGS.stat().st_mtime, STATIONS.stat().st_mtime


@st.cache_data
def _readings(version):
    return pd.read_parquet(READINGS)


@st.cache_data
def _catalog(version):
    readings = _readings(version)
    catalog = (
        readings.groupby(["station_id", "variable", "depth_cm", "unit"], dropna=False)
        .agg(start=("timestamp_utc", "min"), end=("timestamp_utc", "max"))
        .reset_index()
    )
    # Plain int / None so depths can be used as cache and session-state keys.
    catalog["depth_cm"] = pd.Series([None if pd.isna(d) else int(d) for d in catalog["depth_cm"]], dtype=object)
    return catalog


@st.cache_data
def _stations(version):
    stations = pd.read_csv(STATIONS, dtype={"logger_id": str})
    stations["description"] = stations["description"].fillna("").str.strip()
    stations["name"] = stations["name"].fillna("").str.strip().where(lambda n: n != "", stations["station_id"])
    catalog = _catalog(version)
    spans = catalog.groupby("station_id").agg(start=("start", "min"), end=("end", "max"))
    measures = catalog.groupby("station_id")["variable"].agg(
        lambda v: ", ".join(label(x).lower() for x in sorted(set(v)))
    )
    return stations.join(spans, on="station_id").join(measures.rename("measures"), on="station_id")


@st.cache_data
def _series(station_id, variable, depth_cm, version):
    readings = _readings(version)
    mask = (readings["station_id"] == station_id) & (readings["variable"] == variable)
    mask &= readings["depth_cm"].isna() if depth_cm is None else (readings["depth_cm"] == depth_cm).fillna(False)
    series = readings.loc[mask, ["timestamp_utc", "value", "unit"]].sort_values("timestamp_utc").reset_index(drop=True)
    series.insert(0, "timestamp_local", series["timestamp_utc"].dt.tz_convert(TIMEZONE))
    return series


def catalog():
    """One row per (station, variable, depth) with its unit and the span of its data."""
    return _catalog(_version())


def stations():
    """stations.csv (name falls back to station_id) plus each station's data span and the variables it measures."""
    return _stations(_version())


def series(station_id, variable, depth_cm):
    """Readings of one variable, oldest first, with local and UTC timestamps."""
    return _series(station_id, variable, depth_cm, _version())


def tooltip_fields(stations):
    """HTML-safe text for the map tooltip."""
    period = [
        f"{s.tz_convert(TIMEZONE):%b %d, %Y} – {e.tz_convert(TIMEZONE):%b %d, %Y}" if pd.notna(s) else "no data yet"
        for s, e in zip(stations["start"], stations["end"])
    ]
    return pd.DataFrame({
        "station_id": stations["station_id"],
        "tip_name": stations["name"].map(html.escape),
        "tip_id": stations["station_id"].map(html.escape),
        "tip_description": stations["description"].map(html.escape),
        "tip_model": stations["logger_model"].map(html.escape),
        "tip_period": period,
        "tip_measures": stations["measures"].fillna("").map(html.escape),
    })
