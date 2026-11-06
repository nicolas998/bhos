"""Parser for USGS stream gauge data downloaded by `python -m ingest.fetch` from the USGS Water Data service.

Files are the instantaneous-values service's tab-delimited (RDB) output for one site, as downloaded:
'#' comment lines, a header row, a field-width row, then one row per time with its zone (EST/EDT)
and, per parameter, a "<ts_id>_<parameter code>" value column and a "_cd" qualifier column.
Most recent values are provisional and may be revised; later downloads replace them.
"""
import io
import re

import pandas as pd

from .common import long_frame

# Gauges downloaded by the fetch script: USGS site number -> station details.
SITES = {
    "02249500": {
        "station_id": "USGS-02249500",
        "name": "Crane Creek at Melbourne (USGS)",
        "latitude": 28.079167,
        "longitude": -80.629722,
    },
    "02250030": {
        "station_id": "USGS-02250030",
        "name": "Turkey Creek at Palm Bay (USGS)",
        "latitude": 28.01724054,
        "longitude": -80.59588719,
    },
    "02249007": {
        "station_id": "USGS-02249007",
        "name": "Eau Gallie River at Heather Glen Circle, Melbourne (USGS)",
        "latitude": 28.12695888,
        "longitude": -80.6467205,
    },
}
DESCRIPTION = "USGS stream gauge, stage and discharge every 15 minutes (recent data provisional)"

# USGS parameter code -> (variable, unit).
PARAMETERS = {
    "00065": ("stage", "ft"),
    "00060": ("discharge", "ft³/s"),
}
OFFSETS = {"EST": -5, "EDT": -4, "UTC": 0}

FILE_NAME = re.compile(r"^usgs_(\d{8,15})_\d{8}_\d{8}\.rdb$")


def matches(path):
    return bool(FILE_NAME.match(path.name))


def parse(path):
    site = FILE_NAME.match(path.name).group(1)
    lines = [line for line in path.read_text(encoding="utf-8").splitlines() if not line.startswith("#")]
    # lines[1] gives field widths ("5s", "20d", ...), not data.
    data = pd.read_csv(io.StringIO("\n".join(lines[:1] + lines[2:])), sep="\t", dtype=str)

    frames = []
    if len(data):
        offsets = data["tz_cd"].map(OFFSETS)
        timestamps = (pd.to_datetime(data["datetime"]) - pd.to_timedelta(offsets, unit="h")).dt.tz_localize("UTC")
        for code, (variable, unit) in PARAMETERS.items():
            # A site can carry more than one series of a parameter (e.g. a backup sensor); use the first.
            columns = [c for c in data.columns if c.endswith(f"_{code}")]
            if columns:
                # Values such as "Eqp" (equipment malfunction) or "Ice" are not numbers and are dropped.
                frames.append(long_frame(timestamps, variable, pd.NA, data[columns[0]], unit, "USGS"))
    readings = pd.concat(frames, ignore_index=True).dropna(subset=["value"]) if frames else pd.DataFrame(
        columns=["timestamp_utc", "variable", "depth_cm", "value", "unit", "sensor"]
    )

    details = SITES.get(site, {"station_id": f"USGS-{site}", "name": None, "latitude": None, "longitude": None})
    logger = {"logger_id": site, "logger_model": "USGS stream gauge", "description": DESCRIPTION, **details}
    return logger, readings
