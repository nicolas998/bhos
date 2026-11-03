"""Parser for METER ZL6 exports, from both ZENTRA Utility (desktop) and the ZENTRA mobile app.

Both put each logger configuration on its own sheet with three header rows
(port, sensor, "<unit> <measurement>" label) above the records:
  - ZENTRA Utility: "Processed Data Config N"; one fixed time zone in the Metadata sheet.
  - Mobile app:     "Config N"; a per-record "UTC Offset" column on the matching "Raw Config N" sheet.
"""
import re

import pandas as pd

from .common import long_frame, metadata_dict, snake_case

DATA_SHEET = re.compile(r"^(Processed Data )?Config \d+$")

# The mobile app uses long sensor names; shorten them to match ZENTRA Utility.
SENSOR_NAMES = {
    "TEROS 54 Profile Moisture/Temp": "TEROS 54",
    "ECRN-100 Precipitation": "ECRN-100",
}


def matches(sheet_names):
    return any(DATA_SHEET.match(s) for s in sheet_names)


def parse(xl):
    meta = metadata_dict(xl.parse("Metadata", header=None), 1, 2)
    logger_id = None
    frames = []
    for sheet in filter(DATA_SHEET.match, xl.sheet_names):
        table = xl.parse(sheet, header=None)
        logger_id = logger_id or str(table.iloc[0, 0]).strip()
        frames.extend(_parse_sheet(xl, sheet, table, meta))
    readings = pd.concat(frames, ignore_index=True).dropna(subset=["value"])

    logger = {
        "logger_id": logger_id,
        "logger_model": "METER ZL6",
        "station_id": str(meta.get("Device Name", logger_id)),
        "latitude": meta.get("Latitude"),
        "longitude": meta.get("Longitude"),
    }
    return logger, readings


def _parse_sheet(xl, sheet, table, meta):
    sensors = table.iloc[1].ffill()
    labels = table.iloc[2]
    records = table.iloc[3:]
    records = records[pd.to_datetime(records[0], errors="coerce").notna()]

    local = pd.to_datetime(records[0])
    offsets = _utc_offsets(xl, sheet, meta, records.index).map(_offset_minutes)
    timestamps = (local - pd.to_timedelta(offsets, unit="min")).dt.tz_localize("UTC")

    for col in table.columns[1:]:
        variable, depth_cm, unit = _parse_label(labels[col])
        sensor = SENSOR_NAMES.get(sensors[col], sensors[col])
        yield long_frame(timestamps, variable, depth_cm, records[col], unit, sensor)


def _utc_offsets(xl, sheet, meta, index):
    raw_sheet = "Raw " + sheet
    if raw_sheet in xl.sheet_names:
        raw = xl.parse(raw_sheet, header=None)
        headers = raw.iloc[2].tolist()
        if "UTC Offset" in headers:
            return raw.loc[index, headers.index("UTC Offset")]
    return pd.Series(meta["Time Zone"], index=index)


def _offset_minutes(text):
    """'UTC-05' or 'UTC-04:00' -> -300 / -240."""
    # "Not Set" appears before the logger first syncs its clock, which runs on UTC until then.
    match = re.fullmatch(r"UTC([+-])(\d{1,2})(?::?(\d{2}))?", str(text).strip())
    if not match:
        return 0
    sign, hours, minutes = match.groups()
    return (1 if sign == "+" else -1) * (int(hours) * 60 + int(minutes or 0))


def _parse_label(label):
    """'15 cm m³/m³ Water Content' or 'm³/m³ 15 cm Water Content 1' -> ('water_content', 15, 'm³/m³')."""
    label = str(label).strip()
    depth = re.search(r"(\d+) cm", label)
    rest = re.sub(r"\s*\d+ cm\s*", " ", label).strip()
    rest = re.sub(r"\s+\d+$", "", rest)  # the mobile app numbers repeated measurements
    unit, name = rest.split(None, 1)
    return snake_case(name), int(depth.group(1)) if depth else pd.NA, unit
