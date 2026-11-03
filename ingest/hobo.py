"""Parser for Onset HOBO exports from HOBOconnect (e.g. the MX2001 water level logger)."""
import re

import pandas as pd

from .common import long_frame, metadata_dict, snake_case

# Time zone named in the "Date-Time (...)" column header -> zone to localize with.
TIMEZONES = {
    "EST/EDT": "America/New_York",
    "EDT/EST": "America/New_York",
    "EST": "Etc/GMT+5",
    "EDT": "Etc/GMT+4",
    "UTC": "UTC",
    "GMT": "UTC",
}

# Abbreviation ending the times in the Details sheet -> UTC offset in hours.
OFFSETS = {"EST": -5, "EDT": -4, "UTC": 0, "GMT": 0}

# HOBOconnect writes -888.888 for samples it could not take.
MISSING_BELOW = -888


def matches(sheet_names):
    return {"Data", "Details"} <= set(sheet_names)


def parse(xl):
    details = metadata_dict(xl.parse("Details", header=None), 2, 3)
    data = xl.parse("Data")
    timestamps = _sample_times(details, data)

    frames = []
    for col in data.columns[2:]:
        name, unit = (part.strip() for part in col.split(",", 1))
        frames.append(long_frame(timestamps, snake_case(name), pd.NA, data[col], unit, details["Product"]))
    readings = pd.concat(frames, ignore_index=True)
    readings = readings[readings["value"] > MISSING_BELOW]

    logger = {
        "logger_id": str(details["Serial Number"]),
        "logger_model": f"HOBO {details['Product']}",
        "station_id": details.get("Name", str(details["Serial Number"])),
        "latitude": None,
        "longitude": None,
    }
    return logger, readings


def _sample_times(details, data):
    """UTC time of each sample.

    The Date-Time column can't be trusted on its own: depending on the HOBOconnect version it is
    either DST-aware local time or one fixed offset, and it can leave the last samples blank.
    For fixed-interval logging the times are rebuilt from the first sample time and interval in
    Details, checked against the last sample time; otherwise the column is used.
    """
    first = _details_time(details.get("First Sample Time"))
    last = _details_time(details.get("Last Sample Time"))
    interval = _interval(details.get("Interval 1"))
    if first is not None and last is not None and interval is not None and "Interval 2" not in details:
        times = first + interval * pd.RangeIndex(len(data))
        if times[-1] == last:
            return pd.Series(times)

    time_col = data.columns[1]
    local = pd.to_datetime(data[time_col])
    if local.isna().any():
        raise ValueError(f"{local.isna().sum()} samples have no time and the times can't be rebuilt from Details")
    zone = TIMEZONES[re.search(r"\((.+)\)", time_col).group(1)]
    # "infer" resolves the repeated hour when DST ends from the order of the samples.
    return local.dt.tz_localize(zone, ambiguous="infer").dt.tz_convert("UTC")


def _details_time(text):
    """'2026/02/11 13:24:09 EST' -> UTC timestamp."""
    match = re.fullmatch(r"(.+) ([A-Z]{3})", str(text).strip())
    if not match or match.group(2) not in OFFSETS:
        return None
    local = pd.Timestamp(match.group(1))
    return (local - pd.Timedelta(hours=OFFSETS[match.group(2)])).tz_localize("UTC")


def _interval(text):
    """'0 hour 10 minutes 0 seconds, 35592 Samples' -> Timedelta('10min')."""
    match = re.match(r"(\d+) hours? (\d+) minutes? (\d+) seconds?", str(text).strip())
    if not match:
        return None
    hours, minutes, seconds = map(int, match.groups())
    return pd.Timedelta(hours=hours, minutes=minutes, seconds=seconds)
