"""Helpers shared by the logger parsers."""
import re

import pandas as pd

# Columns of the long-format readings table, in order.
COLUMNS = ["timestamp_utc", "station_id", "variable", "depth_cm", "value", "unit", "sensor"]


def snake_case(name):
    """'Max Precip Rate' -> 'max_precip_rate'."""
    return re.sub(r"[^0-9a-z]+", "_", name.strip().lower()).strip("_")


def metadata_dict(sheet, key_col, value_col):
    """Turn a two-column key/value metadata sheet into a dict, keeping the first value of repeated keys."""
    meta = {}
    for key, value in zip(sheet[key_col], sheet[value_col]):
        if pd.notna(key) and pd.notna(value):
            meta.setdefault(str(key).strip(), value)
    return meta


def long_frame(timestamps, variable, depth_cm, values, unit, sensor):
    """Build one variable's slice of the readings table (station_id is filled in by the build step)."""
    return pd.DataFrame({
        "timestamp_utc": timestamps.to_numpy(),
        "variable": variable,
        "depth_cm": depth_cm,
        "value": pd.to_numeric(values, errors="coerce").to_numpy(),
        "unit": unit,
        "sensor": sensor,
    })
