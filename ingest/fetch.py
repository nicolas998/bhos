"""Download public gauge data into Raw/external/, then rebuild the dataset.

    python -m ingest.fetch                     # what's new since the last download, for every gauge
    python -m ingest.fetch --start 2025-09-01  # everything from that date (e.g. to pick up USGS revisions)

Gauges are listed in ingest/asos.py (NWS airport rain) and ingest/usgs.py (USGS stream gauges);
add one there to download it too. Each run saves one file per gauge, named after the dates it
covers. Files are kept as downloaded, so Raw/ stays the only source the dataset is built from.
"""
import argparse
import re
import time
import urllib.error
import urllib.parse
import urllib.request
from datetime import date, datetime, timedelta

from . import asos, build, usgs

EXTERNAL_DIR = build.EXTERNAL_DIR
# First date fetched for a gauge with no downloads yet: the start of the BHOS records.
FIRST_DATE = date(2025, 9, 1)
# Each download re-reads a few days before the last one ended, to pick up late or revised values.
OVERLAP = timedelta(days=3)
USER_AGENT = "BHOS-fetch/1.0"

DATES = re.compile(r"_(\d{8})_(\d{8})\.\w+$")


def main():
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--start", type=date.fromisoformat, help="first date to download (YYYY-MM-DD)")
    parser.add_argument("--no-build", action="store_true", help="download only, don't rebuild the dataset")
    args = parser.parse_args()

    EXTERNAL_DIR.mkdir(parents=True, exist_ok=True)
    end = date.today()
    for site in usgs.SITES:
        download(f"usgs_{site}", args.start, end, ".rdb", lambda start: usgs_url(site, start, end))
    for code in asos.STATIONS:
        download(f"asos_{code}", args.start, end, ".csv", lambda start: asos_url(code, start, end))

    if not args.no_build:
        print()
        build.main()


def download(prefix, start, end, suffix, url_for):
    start = start or next_start(prefix)
    path = EXTERNAL_DIR / f"{prefix}_{start:%Y%m%d}_{end:%Y%m%d}{suffix}"
    print(f"downloading {prefix} {start} to {end}")
    text = get(url_for(start))
    if not has_data(text, suffix):
        print("  no data returned, nothing saved")
        return
    path.write_text(text, encoding="utf-8")
    print(f"  saved {path.relative_to(build.ROOT)}")


def next_start(prefix):
    """Day to start from: a little before the end of the latest download of this gauge."""
    ends = [
        datetime.strptime(m.group(2), "%Y%m%d").date()
        for p in EXTERNAL_DIR.glob(f"{prefix}_*") if (m := DATES.search(p.name))
    ]
    return max(ends) - OVERLAP if ends else FIRST_DATE


def has_data(text, suffix):
    rows = [line for line in text.splitlines() if line.strip() and not line.startswith("#")]
    header_rows = 2 if suffix == ".rdb" else 1  # RDB has a field-width row under the header
    return len(rows) > header_rows


def usgs_url(site, start, end):
    query = {"format": "rdb", "sites": site, "parameterCd": ",".join(usgs.PARAMETERS),
             "startDT": start.isoformat(), "endDT": end.isoformat(), "siteStatus": "all"}
    return "https://waterservices.usgs.gov/nwis/iv/?" + urllib.parse.urlencode(query)


def asos_url(code, start, end):
    stop = end + timedelta(days=1)  # IEM's end date is exclusive
    query = {
        "station": code, "data": "p01i", "tz": "UTC", "format": "onlycomma", "latlon": "yes",
        "missing": "M", "trace": "T", "report_type": "3",  # routine hourly reports only
        "year1": start.year, "month1": start.month, "day1": start.day,
        "year2": stop.year, "month2": stop.month, "day2": stop.day,
    }
    return "https://mesonet.agron.iastate.edu/cgi-bin/request/asos.py?" + urllib.parse.urlencode(query)


def get(url, attempts=4):
    """Response body of `url`, waiting and retrying when the server asks to slow down."""
    for attempt in range(attempts):
        try:
            request = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
            with urllib.request.urlopen(request, timeout=300) as response:
                text = response.read().decode("utf-8")
        except urllib.error.HTTPError as error:
            if error.code not in (429, 503) or attempt == attempts - 1:
                raise
            text = "Too many requests"
        if not text.startswith("Too many requests"):  # IEM's rate-limit reply
            return text
        wait = 30 * (attempt + 1)
        print(f"  server busy, retrying in {wait} s")
        time.sleep(wait)
    raise RuntimeError(f"server kept refusing: {url}")


if __name__ == "__main__":
    main()
