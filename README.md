# PhysicalLab

Sensor data and the visualization site built on it.

## Data workflow

1. Download the logger export (`.xlsx`) and drop it in `Raw/` unchanged.
   Overlapping or full-history exports are fine; duplicates are removed.
2. Rebuild the dataset:

   ```
   python -m ingest
   ```

3. Commit `data/`. `Raw/` is git-ignored and stays on your machine, so keep a backup of it:
   it is the only source the dataset can be rebuilt from.

New loggers are added to `data/stations.csv` automatically. Edit that file to rename a
station (`station_id`) or add a `description`; the next ingest applies the change.

Supported exports: Onset HOBOconnect (HOBO MX2001) and METER ZL6 from ZENTRA Utility
or the ZENTRA mobile app.

### Public gauges

Public gauges near the BHOS loggers are downloaded by a script, run by hand whenever you update:

```
python -m ingest.fetch
```

It downloads what's new since the last run (from Sep 1, 2025 the first time) into
`Raw/external/`, files kept as downloaded, then rebuilds the dataset like `python -m ingest`.
Commit `data/` afterwards as usual. `python -m ingest.fetch --start 2025-09-01` downloads
everything again, e.g. to pick up USGS revisions of provisional data.

| Station | Source | Data |
|---|---|---|
| `KMLB` Melbourne International Airport | NWS ASOS, via the [Iowa Environmental Mesonet](https://mesonet.agron.iastate.edu/request/download.phtml) | hourly rainfall |
| `USGS-02249500` Crane Creek at Melbourne | [USGS Water Data](https://waterdata.usgs.gov/monitoring-location/02249500/) | stage and discharge, 15 min |
| `USGS-02250030` Turkey Creek at Palm Bay | [USGS Water Data](https://waterdata.usgs.gov/monitoring-location/02250030/) | stage and discharge, 15 min |
| `USGS-02249007` Eau Gallie River at Melbourne | [USGS Water Data](https://waterdata.usgs.gov/monitoring-location/02249007/) | stage and discharge, 15 min |

To add a gauge, list it in `STATIONS` in `ingest/asos.py` (airports) or `SITES` in
`ingest/usgs.py` (USGS sites). Recent USGS data is provisional and may be revised.

## Visualization app

```
streamlit run app/streamlit_app.py
```

Hover a gauge on the map for its details and click it to list its variables; each variable
clicked adds a plot (newest on top, at most 5) with its own CSV download. One period slider
sets the dates for all plots; data is plotted at 5-minute resolution for periods under a month,
15-minute up to 6 months, and hourly beyond (rain summed, water level as mean and maximum,
everything else averaged). Dragging across any plot zooms all of them to that range (with
resolution following the zoomed span); double-click a plot or "Reset zoom" to go back. Rainfall
plots can show the cumulative total on a second axis, and rainfall and water level can be shown
in feet.

## Dataset

`data/readings.parquet` — one row per reading:

| column | description |
|---|---|
| `timestamp_utc` | measurement time, UTC |
| `station_id` | station, as named in `stations.csv` |
| `variable` | e.g. `water_content`, `soil_temperature`, `water_level`, `precipitation`, `stage`, `discharge` |
| `depth_cm` | sensor depth for profile sensors, empty otherwise |
| `value` | measured value (missing samples are dropped) |
| `unit` | e.g. `m³/m³`, `°C`, `m`, `mm`, `ft`, `ft³/s` |
| `sensor` | sensor model, e.g. `TEROS 54`, `ECRN-100`, `MX2001`, or the source network (`ASOS`, `USGS`) |

`data/stations.csv` — one row per logger or public gauge, with model and coordinates.
