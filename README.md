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
| `variable` | e.g. `water_content`, `soil_temperature`, `water_level`, `precipitation` |
| `depth_cm` | sensor depth for profile sensors, empty otherwise |
| `value` | measured value (missing samples are dropped) |
| `unit` | e.g. `m³/m³`, `°C`, `m`, `mm` |
| `sensor` | sensor model, e.g. `TEROS 54`, `ECRN-100`, `MX2001` |

`data/stations.csv` — one row per logger, with model and coordinates.
