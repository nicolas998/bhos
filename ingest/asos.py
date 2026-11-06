"""Parser for NWS airport (ASOS) rainfall downloaded by `python -m ingest.fetch` from the Iowa Environmental Mesonet.

Files are IEM's comma-separated output as downloaded: station, valid (UTC), lon, lat, p01i. Only the
routine hourly reports are requested, so p01i is the rain of the hour ending at `valid`, in inches.
"""
import re

import pandas as pd

from .common import long_frame

# Gauges downloaded by the fetch script: IEM station code -> station details.
STATIONS = {
    "MLB": {
        "station_id": "KMLB",
        "name": "Melbourne International Airport (NWS)",
        "description": "NWS ASOS weather station, hourly rainfall from the Iowa Environmental Mesonet",
    },
}

FILE_NAME = re.compile(r"^asos_([A-Z0-9]+)_\d{8}_\d{8}\.csv$")
MM_PER_INCH = 25.4


def matches(path):
    return bool(FILE_NAME.match(path.name))


def parse(path):
    code = FILE_NAME.match(path.name).group(1)
    data = pd.read_csv(path, dtype={"p01i": str})
    # "T" is a trace of rain (under 0.01 in); "M" a missing report.
    inches = pd.to_numeric(data["p01i"].replace("T", "0"), errors="coerce")
    timestamps = pd.to_datetime(data["valid"]).dt.tz_localize("UTC")
    readings = long_frame(timestamps, "precipitation", pd.NA, inches * MM_PER_INCH, "mm", "ASOS").dropna(subset=["value"])

    logger = {
        "logger_id": code,
        "logger_model": "NWS ASOS",
        **STATIONS.get(code, {"station_id": f"K{code}", "name": None, "description": None}),
        "latitude": data["lat"].iloc[0] if len(data) else None,
        "longitude": data["lon"].iloc[0] if len(data) else None,
    }
    return logger, readings
