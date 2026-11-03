"""Sensor data explorer: pick a gauge on the map, then stack plots of its variables.

Run from the project root with:  streamlit run app/streamlit_app.py
"""
import base64
import json
import math
from datetime import date, timedelta
from pathlib import Path

import pandas as pd
import pydeck as pdk
import streamlit as st

import charts
import loading

MAX_PLOTS = 5
MAP_HEIGHT = 460

# Reports zooming or panning on any plot, so all plots can be redrawn over the same range.
x_axis_sync = st.components.v2.component(
    "x_axis_sync", js=(Path(__file__).parent / "xaxis_sync.js").read_text(encoding="utf-8")
)
# Range of the period slider.
PERIOD_MIN, PERIOD_MAX = date(2025, 1, 1), date(2026, 12, 31)

# What a first visit shows: rainfall at Satellite Beach over the Nov 2, 2026 flood, accumulated, in feet.
DEFAULT_PLOT = ("z6-37246", "precipitation", None)
DEFAULT_PERIOD = (date(2026, 11, 1), date(2026, 11, 3))
DEFAULT_OPTIONS = {"cumulative": True, "unit": "ft"}  # widget key prefix -> value

# Map marker colour per logger model (categorical slots 1 and 2).
MODEL_COLORS = {"METER ZL6": [42, 120, 214], "HOBO MX2001": [235, 104, 52]}
OTHER_COLOR = [98, 80, 214]

# OpenStreetMap's standard tiles as a MapLibre style. Streamlit only accepts a style URL,
# so the style is passed inline as a data: URL.
OSM_STYLE = {
    "version": 8,
    "sources": {"osm": {
        "type": "raster", "tiles": ["https://tile.openstreetmap.org/{z}/{x}/{y}.png"],
        "tileSize": 256, "maxzoom": 19, "attribution": "© OpenStreetMap contributors",
    }},
    "layers": [{"id": "osm", "type": "raster", "source": "osm"}],
}
OSM_STYLE_URL = "data:application/json;base64," + base64.b64encode(json.dumps(OSM_STYLE).encode()).decode()

TOOLTIP = {
    "html": "<b>{tip_name}</b><br/>{tip_description}<br/><br/>"
            "<span style='opacity:.75'>{tip_model} · {tip_id}<br/>Data: {tip_period}<br/>Measures: {tip_measures}</span>",
    "style": {"font-size": "13px", "max-width": "320px"},
}

st.set_page_config(page_title="Brevard Hydrologic Observations System (BHOS)", layout="wide")
state = st.session_state
state.setdefault("zoom", None)  # (period, (start, end)) while the plots are zoomed in on part of the period


def select_from_map():
    picked = state.map.selection.get("objects", {}).get("stations", [])
    if picked:
        state.station = state.station_picker = picked[0]["station_id"]


def select_from_picker():
    state.station = state.station_picker


def add_plot(key):
    """Put the series on top; a series already shown moves up instead of repeating."""
    state.plots = [p for p in state.plots if p["key"] != key]
    state.plots.insert(0, {"id": state.next_id, "key": key})
    state.next_id += 1
    del state.plots[MAX_PLOTS:]


def open_default_view(catalog):
    """Set up a first visit: DEFAULT_PLOT over DEFAULT_PERIOD with DEFAULT_OPTIONS, if that data exists."""
    state.station = state.station_picker = None
    state.plots = []  # newest first: {"id": int, "key": (station_id, variable, depth_cm)}
    state.next_id = 0
    station_id, variable, _ = DEFAULT_PLOT
    if not ((catalog["station_id"] == station_id) & (catalog["variable"] == variable)).any():
        return
    state.station = state.station_picker = station_id
    add_plot(DEFAULT_PLOT)
    state.period = DEFAULT_PERIOD
    for prefix, value in DEFAULT_OPTIONS.items():
        state[f"{prefix}_{state.plots[0]['id']}"] = value


def remove_plot(plot_id):
    state.plots = [p for p in state.plots if p["id"] != plot_id]


def toggle_plots(pills_key, keys):
    """Add plots for newly selected variable pills and remove those of deselected ones."""
    picked = set(state[pills_key] or [])
    for key in keys:
        plot_ids = [p["id"] for p in state.plots if p["key"] == key]
        if key in picked and not plot_ids:
            add_plot(key)
        elif key not in picked and plot_ids:
            remove_plot(plot_ids[0])


def station_map(stations):
    points = loading.tooltip_fields(stations).assign(
        longitude=stations["longitude"],
        latitude=stations["latitude"],
        color=[MODEL_COLORS.get(m, OTHER_COLOR) for m in stations["logger_model"]],
        line=[[20, 20, 20] if s == state.station else [255, 255, 255] for s in stations["station_id"]],
    ).dropna(subset=["longitude", "latitude"])
    layer = pdk.Layer(
        "ScatterplotLayer", id="stations", data=points,
        get_position=["longitude", "latitude"], get_fill_color="color", get_line_color="line",
        get_radius=30, radius_min_pixels=8, radius_max_pixels=16,
        stroked=True, line_width_min_pixels=2, pickable=True, auto_highlight=True,
    )
    deck = pdk.Deck(layers=[layer], initial_view_state=fit_view(points), map_style=OSM_STYLE_URL, tooltip=TOOLTIP)
    st.pydeck_chart(deck, on_select=select_from_map, selection_mode="single-object", key="map", height=MAP_HEIGHT)

    legend = " &nbsp; ".join(
        f"<span style='color:rgb{tuple(c)}'>●</span> {model}" for model, c in MODEL_COLORS.items()
        if model in set(stations["logger_model"])
    )
    st.caption(
        legend + " &nbsp;·&nbsp; Hover a gauge for details, click it to see its variables."
        " Gauges close together separate as you zoom in.",
        unsafe_allow_html=True,
    )


def fit_view(points, width=900, height=MAP_HEIGHT, padding=0.5, max_zoom=15):
    """View centred on the gauges' bounding box, zoomed so all of them fit in a map of about width x height px."""
    lon_min, lon_max = points["longitude"].min(), points["longitude"].max()
    lat_min, lat_max = points["latitude"].min(), points["latitude"].max()
    lat = (lat_min + lat_max) / 2
    # Web Mercator as deck.gl draws it: the world is 512 * 2**zoom px around, and near `lat`
    # a degree of latitude takes 1/cos(lat) times the pixels of a degree of longitude.
    zooms = [max_zoom]
    if lon_max > lon_min:
        zooms.append(math.log2(width * 360 / (512 * (lon_max - lon_min))))
    if lat_max > lat_min:
        zooms.append(math.log2(height * 360 * math.cos(math.radians(lat)) / (512 * (lat_max - lat_min))))
    return pdk.ViewState(longitude=(lon_min + lon_max) / 2, latitude=lat, zoom=min(zooms) - padding)


def station_panel(stations, catalog):
    names = dict(zip(stations["station_id"], stations["name"]))
    st.selectbox(
        "Gauge", list(names), format_func=names.get, placeholder="Click a gauge on the map",
        key="station_picker", on_change=select_from_picker,
    )
    if state.station not in names:
        st.caption("Select a gauge on the map (or in the list above) to see what it measures.")
        return

    station = stations.set_index("station_id").loc[state.station]
    st.caption(" · ".join(filter(None, [station["description"], station["logger_model"], state.station])))

    series = catalog[catalog["station_id"] == state.station].sort_values(["variable", "depth_cm"], na_position="first")
    # Companions appear on their main variable's plot rather than as options of their own.
    pairs = list(zip(series["variable"], series["depth_cm"]))
    paired = {(charts.COMPANIONS[v], d) for v, d in pairs if v in charts.COMPANIONS}
    keys = [(state.station, v, d) for v, d in pairs if (v, d) not in paired]

    # Selected pills are the station's plots on screen, so the pills follow plots added or removed elsewhere.
    pills_key = f"variables_{state.station}"
    shown = {p["key"] for p in state.plots}
    state[pills_key] = [k for k in keys if k in shown]
    st.pills(
        "Variables", keys, selection_mode="multi", format_func=lambda k: loading.label(k[1], k[2]),
        key=pills_key, on_change=toggle_plots, args=(pills_key, keys), wrap=True,
    )
    notes = dict.fromkeys(
        f"{loading.label(charts.COMPANIONS[v])} is shown on the {loading.label(v).lower()} plots."
        for v, d in pairs if (charts.COMPANIONS.get(v), d) in paired
    )
    st.caption(" ".join([f"Click to plot, again to remove (up to {MAX_PLOTS} plots; more replace the oldest).", *notes]))


def in_view(series, view):
    """Readings of `series` within `view`, a (start, end) pair of local timestamps."""
    local = series["timestamp_local"]
    return series[(local >= view[0]) & (local < view[1])]


def csv_bytes(window, station_id, variable, depth_cm, cumulative, companion=None, companion_window=None):
    out = pd.DataFrame({
        "timestamp_local": window["timestamp_local"].dt.tz_localize(None),
        "timestamp_utc": window["timestamp_utc"].dt.tz_localize(None),
        "station_id": station_id,
        "variable": variable,
        "depth_cm": depth_cm,
        "value": window["value"],
        "unit": window["unit"],
    })
    if cumulative:
        out["cumulative"] = window["value"].cumsum()
    if companion_window is not None:
        extra = pd.DataFrame({
            "timestamp_utc": companion_window["timestamp_utc"].dt.tz_localize(None),
            companion: companion_window["value"],
            f"{companion}_unit": companion_window["unit"],
        })
        out = out.merge(extra, on="timestamp_utc", how="left")
    return out.to_csv(index=False).encode("utf-8")


def period_picker(catalog):
    """The one period (start, end dates) shared by every plot."""
    first = max(catalog["start"].min().tz_convert(loading.TIMEZONE).date(), PERIOD_MIN)
    last = min(catalog["end"].max().tz_convert(loading.TIMEZONE).date(), PERIOD_MAX)
    state.setdefault("period", (first, last))  # unless the default view set one
    start, end = st.slider(
        "Period for all plots", min_value=PERIOD_MIN, max_value=PERIOD_MAX,
        step=timedelta(days=1), format="MMM D, YYYY", key="period",
    )
    return start, end


def local_time(value):
    """A local wall-clock time (as Plotly reports it) as a timestamp in TIMEZONE."""
    return pd.Timestamp(value).tz_localize(loading.TIMEZONE, ambiguous=False, nonexistent="shift_forward")


def reset_zoom():
    state.zoom = None


def plot_view(period):
    """The (start, end) local timestamps every plot shows: the range zoomed to on any plot, else the period."""
    start, end = period
    whole = (pd.Timestamp(start, tz=loading.TIMEZONE), pd.Timestamp(end + timedelta(days=1), tz=loading.TIMEZONE))
    zoomed = getattr(x_axis_sync(key="x_axis_sync", on_range_change=lambda: None), "range", None)
    if zoomed == "reset":
        state.zoom = None
    elif zoomed:
        state.zoom = (period, (local_time(zoomed[0]), local_time(zoomed[1])))
    if state.zoom and state.zoom[0] != period:  # moving the slider starts again from the whole period
        state.zoom = None
    view = state.zoom[1] if state.zoom else whole

    span = view[1] - view[0]
    resolution = charts.FREQ_NAMES[charts.resolution(span)]
    if state.zoom:
        text, button = st.columns([6, 1], vertical_alignment="center")
        text.caption(
            f"Zoomed in to {view[0]:%b %d, %Y %H:%M} – {view[1]:%b %d, %Y %H:%M}, plotted as {resolution} values."
            " Double-click a plot to see the whole period again."
        )
        button.button("Reset zoom", on_click=reset_zoom, icon=":material/zoom_out:", width="stretch")
    else:
        st.caption(
            f"{start:%b %d, %Y} – {end:%b %d, %Y} ({span.days} days), plotted as {resolution} values."
            " Drag across a plot to zoom in on all of them; drag the axis ends or use the pan tool to move along."
        )
    st.caption(
        "Plots use 5-minute values for spans under a month, 15-minute up to 6 months, and hourly beyond"
        " (readings already that far apart are plotted as they are); CSV downloads include every reading in view."
    )
    return view


def plot_card(plot, stations, view):
    plot_id, (station_id, variable, depth_cm) = plot["id"], plot["key"]
    series = loading.series(station_id, variable, depth_cm)
    name = loading.label(variable, depth_cm)
    station_name = stations.set_index("station_id")["name"].get(station_id, station_id)
    unit = series["unit"].iloc[0] if len(series) else ""
    companion = charts.COMPANIONS.get(variable)
    companion_series = loading.series(station_id, companion, depth_cm) if companion else None
    has_companion = companion_series is not None and not companion_series.empty

    with st.container(border=True):
        title, close = st.columns([20, 1], vertical_alignment="center")
        title.markdown(f"**{name}** · {station_name}")
        close.button("✕", key=f"close_{plot_id}", on_click=remove_plot, args=(plot_id,), help="Remove this plot")

        controls, chart = st.columns([1, 5])
        with controls:
            first, last = series["timestamp_local"].iloc[[0, -1]].dt.date
            st.caption(f"Data available {first:%b %d, %Y} – {last:%b %d, %Y}")
            cumulative = variable in charts.ACCUMULATING and st.toggle("Show cumulative", key=f"cumulative_{plot_id}")
            units = charts.unit_options(variable, unit)
            if units:
                unit = st.radio("Units", units, horizontal=True, key=f"unit_{plot_id}")
            show_companion = has_companion and st.toggle(
                f"Show {loading.label(companion).lower()}", value=True, key=f"companion_{plot_id}"
            )

        start, end = view
        window = in_view(series, view)
        if units:
            window = charts.convert(window, variable, unit)
        companion_window = in_view(companion_series, view) if has_companion else None
        if window.empty:
            last_day = end - pd.Timedelta(days=1) if end == end.normalize() else end
            chart.warning(f"No data for this period ({start:%b %d, %Y} – {last_day:%b %d, %Y}).", icon="⚠️")
        else:
            freq = charts.plot_freq(window, end - start)
            plotted = charts.aggregate(window, variable, freq) if freq else window
            if cumulative:
                plotted = plotted.assign(cumulative=plotted["value"].cumsum())
            companion_spec = None
            if show_companion and not companion_window.empty:
                extra = charts.aggregate(companion_window, companion, freq) if freq else companion_window
                plotted = plotted.merge(
                    extra[["timestamp_local", "value"]].rename(columns={"value": "companion"}),
                    on="timestamp_local", how="left",
                )
                companion_spec = (companion, loading.label(companion), companion_window["unit"].iloc[0])
            # Every plot spans the same view, so their x axes line up; zooming one changes the view for all.
            figure = charts.figure(
                plotted, variable, name, unit, cumulative, freq, companion_spec,
                x_range=(start.tz_localize(None), end.tz_localize(None)),
            )
            # Double-click autoscales, which xaxis_sync.js reports as a reset to the whole period.
            chart.plotly_chart(figure, key=f"chart_{plot_id}", config={"doubleClick": "autosize"})

        depth = f"_{depth_cm}cm" if depth_cm is not None else ""
        controls.download_button(
            "Download CSV", csv_bytes(window, station_id, variable, depth_cm, cumulative, companion, companion_window),
            file_name=f"{station_id}_{variable}{depth}_{start:%Y-%m-%d}_{end:%Y-%m-%d}.csv", mime="text/csv",
            on_click="ignore", disabled=window.empty, icon=":material/download:", key=f"download_{plot_id}",
        )


stations = loading.stations()
catalog = loading.catalog()
if "plots" not in state:
    open_default_view(catalog)

st.title("Brevard Hydrologic Observations System (BHOS)")
map_column, panel_column = st.columns([3, 1], gap="medium")
with map_column:
    station_map(stations)
with panel_column:
    station_panel(stations, catalog)

st.divider()
view = plot_view(period_picker(catalog))
if not state.plots:
    st.info("Plots of the variables you pick will stack here, newest on top.")
for plot in state.plots:
    plot_card(plot, stations, view)
