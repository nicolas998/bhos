"""Plotly figures for one variable of one station."""
import pandas as pd
from plotly.subplots import make_subplots

SERIES_COLOR = "#2a78d6"
SECOND_COLOR = "#eb6834"
COMPANION_COLOR = "#1baf7a"

# Variables recorded as amounts per interval: drawn as bars and offered a cumulative total.
ACCUMULATING = {"precipitation"}

# Variable drawn on a second axis of another's plot (same station and depth) instead of in a plot of its own.
COMPANIONS = {
    "water_content": "soil_temperature",
    "water_level": "temperature",
}

# Statistics used when a long period is aggregated; the first is the main series.
# Variables not listed are averaged.
AGGREGATIONS = {
    "precipitation": ["sum"],
    "water_level": ["mean", "max"],
    "stage": ["mean", "max"],
    "discharge": ["mean", "max"],
}
STAT_NAMES = {"sum": "total", "mean": "mean", "max": "maximum"}

# Display units offered per variable: unit -> factor from the stored unit, which is listed first.
UNITS = {
    "precipitation": {"mm": 1, "in": 1 / 25.4, "ft": 1 / 304.8},
    "water_level": {"m": 1, "ft": 1 / 0.3048},
    "stage": {"ft": 1, "m": 0.3048},
    "discharge": {"ft³/s": 1, "m³/s": 0.3048 ** 3},
}
FREQ_NAMES = {"5min": "5-minute", "15min": "15-minute", "1h": "hourly"}


def resolution(span):
    """Bin size for plotting a time span (Timedelta): 5 min under a month, 15 min up to 6 months, then hourly."""
    days = span / pd.Timedelta(days=1)
    if days < 30:
        return "5min"
    if days <= 182:
        return "15min"
    return "1h"


def plot_freq(window, span):
    """resolution(span), or None when those bins are no coarser than the readings, which are then plotted as is."""
    freq = resolution(span)
    step = window["timestamp_local"].diff().median()
    return freq if pd.isna(step) or pd.Timedelta(freq) > step else None


def unit_options(variable, stored_unit):
    """Units `variable` can be shown in, or [] when it has no alternatives (or isn't stored as expected)."""
    options = list(UNITS.get(variable, {}))
    return options if options and options[0] == stored_unit else []


def convert(window, variable, unit):
    """Express `window` (value, unit) in `unit`, one of unit_options(variable, ...)."""
    return window.assign(value=window["value"] * UNITS[variable][unit], unit=unit)


def aggregate(window, variable, freq):
    """Bin `window` (timestamp_local, value) to `freq`: the main statistic in `value`, any other in its own column."""
    stats = AGGREGATIONS.get(variable, ["mean"])
    bins = window.set_index("timestamp_local")["value"].resample(freq)
    # min_count leaves bins without readings empty rather than reporting zero rain; they are
    # dropped, and with_gaps breaks the line wherever the gap is real.
    columns = {stat: bins.sum(min_count=1) if stat == "sum" else bins.agg(stat) for stat in stats}
    return pd.DataFrame(columns).rename(columns={stats[0]: "value"}).dropna(how="all").reset_index()


def series_names(variable, name, freq):
    """Legend name of each value column that `aggregate` produces (just `value` when not aggregated)."""
    if freq is None:
        return {"value": name}
    stats = AGGREGATIONS.get(variable, ["mean"])
    return {
        "value" if i == 0 else stat: f"{name}, {FREQ_NAMES[freq]} {STAT_NAMES[stat]}"
        for i, stat in enumerate(stats)
    }


def with_gaps(df):
    """Insert an empty row inside each gap so lines break where data is missing instead of bridging it."""
    step = df["timestamp_local"].diff()
    gaps = step > 3 * step.median()
    if not gaps.any():
        return df
    breaks = pd.DataFrame({"timestamp_local": df.loc[gaps, "timestamp_local"] - step[gaps] / 2})
    return pd.concat([df, breaks]).sort_values("timestamp_local")


def figure(data, variable, name, unit, cumulative=False, freq=None, companion=None, x_range=None):
    """Plot `data` (timestamp_local, value[, other statistics][, cumulative][, companion]) for the series
    called `name`; `companion` is (variable, name, unit) of the series in the companion column, and
    `x_range` the (start, end) local times the x axis spans."""
    df = with_gaps(data)
    x = df["timestamp_local"].dt.tz_localize(None)  # plot local wall-clock time
    value_format = f"%{{y:.4g}} {unit}"
    names = series_names(variable, name, freq)

    fig = make_subplots(specs=[[{"secondary_y": cumulative or companion is not None}]])
    for column, color in zip(names, [SERIES_COLOR, SECOND_COLOR]):
        trace = dict(x=x, y=df[column], name=names[column], hovertemplate=value_format)
        if variable in ACCUMULATING:
            fig.add_bar(**trace, marker=dict(color=color, line_width=0))
        else:
            fig.add_scatter(**trace, mode="lines", line=dict(color=color, width=2), connectgaps=False)
    fig.update_yaxes(title_text=f"{name} ({unit})", secondary_y=False)

    if cumulative:
        fig.add_scatter(
            x=x, y=df["cumulative"], name="Cumulative", mode="lines", connectgaps=False,
            line=dict(color=SECOND_COLOR, width=2), hovertemplate=value_format, secondary_y=True,
        )
        fig.update_yaxes(title_text=f"Cumulative ({unit})", rangemode="tozero", showgrid=False, secondary_y=True)

    if companion is not None:
        companion_variable, companion_name, companion_unit = companion
        fig.add_scatter(
            x=x, y=df["companion"], name=series_names(companion_variable, companion_name, freq)["value"],
            mode="lines", connectgaps=False, line=dict(color=COMPANION_COLOR, width=2),
            hovertemplate=f"%{{y:.4g}} {companion_unit}", secondary_y=True,
        )
        fig.update_yaxes(title_text=f"{companion_name} ({companion_unit})", showgrid=False, secondary_y=True)

    # Round tick values on the second axis, rather than ticks synced to the first axis's gridlines.
    fig.update_yaxes(tickmode="auto", secondary_y=True)
    # Zoom and pan along time only; the y axes fit whatever is in view.
    fig.update_yaxes(fixedrange=True)
    legend = len(fig.data) > 1
    fig.update_xaxes(hoverformat="%b %d, %Y %H:%M")
    if x_range is not None:
        fig.update_xaxes(range=[pd.Timestamp(x_range[0]), pd.Timestamp(x_range[1])])
    fig.update_layout(
        height=320,
        margin=dict(l=10, r=10, t=30 if legend else 10, b=10),
        hovermode="x unified",
        showlegend=legend,
        legend=dict(orientation="h", x=0, y=1.02, yanchor="bottom"),
        bargap=0,
    )
    return fig
