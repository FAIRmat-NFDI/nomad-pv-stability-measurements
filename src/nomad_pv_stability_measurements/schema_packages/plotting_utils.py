"""Helpers that draw the project entry's timeline: one row per file group and one
line per file, from the start to the end of the period its data cover."""

from datetime import datetime, timezone, tzinfo
from pathlib import PurePosixPath
from typing import TYPE_CHECKING

from nomad.datamodel.metainfo.plot import PlotlyFigure

from nomad_pv_stability_measurements.file_reading import INSTITUTIONS

if TYPE_CHECKING:
    from nomad_pv_stability_measurements.schema_packages.schema_package import (
        StabilityFileGroup,
    )

#: Sizes in the timeline of the files, in pixels: of the circle at a file's start,
#: of the smaller triangle at its end, which hides behind the circle when zoomed
#: out, and of the line between them, thinner still so the triangle stands out.
TIMELINE_START_SIZE = 10
TIMELINE_END_SIZE = 7
TIMELINE_LINE_WIDTH = 3

#: How opaque a file's line is, so that overlapping files stay visible. The
#: markers at its start and end are opaque.
TIMELINE_LINE_OPACITY = 0.35

#: The colours of the stability file types in the timeline. NOMAD's GUI shows a figure
#: on a light or a dark background, so each colour keeps a contrast of at least 3:1
#: to white and to near-black, and the colours stay apart for colour-blind readers.
#: Other kinds are grey; the hover text names them.
TIMELINE_KIND_COLORS = {
    'jv': '#3987e5',
    'dark_jv': '#d95926',
    'mpp_tracking': '#199e70',
    'stability_series': '#c98500',
    'jv_parameters': '#d55181',
    'eqe': '#008300',
    'pl': '#9085e9',
    'el': '#e66767',
    'setup_log': '#8a6d3b',
    'environment_log': '#8a6d3b',
    'weather_information': '#1f9eb3',
}
TIMELINE_OTHER_COLOR = '#8c8c8c'

#: The outline of the markers: a mid grey, which stands out on a light and on a
#: dark background, and around a marker over another one.
TIMELINE_OUTLINE_COLOR = '#808080'
TIMELINE_OUTLINE_WIDTH = 0.5

#: Space above the timeline for the legend, in pixels.
TIMELINE_LEGEND_HEIGHT = 50

#: The part of a group's row over which the kinds are spread, in rows.
TIMELINE_ROW_SPREAD = 0.6

#: The Plotly marker symbols at the start and the end of a file's data.
TIMELINE_START_SYMBOL = 'circle'
TIMELINE_END_SYMBOL = 'triangle-up'

#: The legend entries that explain the start and end markers.
TIMELINE_START_LEGEND = 'start_time'
TIMELINE_END_LEGEND = 'end_time'

#: The hover text of a file's markers.
TIMELINE_HOVER = (
    '<b>%{customdata[0]}</b><br>'
    'series: %{customdata[1]}<br>'
    'start_time: %{customdata[2]}<br>'
    'end_time: %{customdata[3]}<br>'
    # `<extra></extra>` leaves out the box with the trace's name.
    'type: %{customdata[4]}<extra></extra>'
)


def file_timeline(
    file_groups: list['StabilityFileGroup'], entries: dict
) -> list[PlotlyFigure]:
    """A figure with one row per group and one line per file from the start to the
    end of the period its data cover, coloured by stability file type. Hovering over
    a file's
    markers shows the file name, its sample, start and end time, and kind. A circle
    marks the start and a smaller triangle the end, both in the kind's full colour
    with a grey outline; the thinner line between them is translucent, so that
    overlapping files stay visible. Circles are drawn over all triangles, and these
    over all lines. A file that ends when it starts is one circle. The legend shows
    each kind as a line, which shows and hides the kind's files, and the two markers
    in grey.

    Every trace, legend entries included, holds data and no gaps: NOMAD's new GUI
    does not show traces without data, nor their legend entries.

    Within a group's row, each kind of the upload has its own slight vertical
    offset, so that files of different kinds over the same time stay apart.

    Files without start time are not plotted, and a group without such files, the
    group `UNKNOWN_SAMPLE` included, has no row. Without any plottable file, no
    figure. Rows keep the order of `file_groups`, top to bottom. Each kind has the
    colour of `TIMELINE_KIND_COLORS`, the same in every upload. An entry made before
    end times existed ends when it starts. Times are in the zone given by
    `timeline_time_zone`."""
    import plotly.graph_objects as go
    from plotly.colors import hex_to_rgb

    # Imported here, because the schema package imports this module.
    from nomad_pv_stability_measurements.schema_packages.schema_package import (
        STABILITY_FILE_TYPES,
    )

    def plottable(record):
        entry = entries[record.file]
        return entry is not None and entry.start_time is not None

    rows = [group for group in file_groups if any(map(plottable, group.files))]
    row_names = [group.name for group in rows]
    files_by_kind: dict[str, list] = {}
    for row, group in enumerate(rows):
        for record in filter(plottable, group.files):
            entry = entries[record.file]
            files_by_kind.setdefault(entry.stability_file_type or 'unknown', []).append(
                (row, group.name, record.file, entry)
            )
    if not files_by_kind:
        return []

    zone = timeline_time_zone(
        entry for files in files_by_kind.values() for *_, entry in files
    )

    def local(time: datetime) -> datetime:
        # Plotly ignores time zones, so the times are given as written in `zone`.
        if time.tzinfo is None:
            time = time.replace(tzinfo=timezone.utc)
        return time.astimezone(zone).replace(tzinfo=None)

    kinds = sorted(files_by_kind, key=STABILITY_FILE_TYPES.index)
    spacing = TIMELINE_ROW_SPREAD / max(len(kinds) - 1, 1)
    outline = dict(color=TIMELINE_OUTLINE_COLOR, width=TIMELINE_OUTLINE_WIDTH)
    lines, ends, starts = [], [], []
    for index, kind in enumerate(kinds):
        offset = (index - (len(kinds) - 1) / 2) * spacing
        red, green, blue = hex_to_rgb(
            TIMELINE_KIND_COLORS.get(kind, TIMELINE_OTHER_COLOR)
        )
        color = rgba(red, green, blue)
        line_color = rgba(red, green, blue, TIMELINE_LINE_OPACITY)
        # The start and the end of each file, with its hover text.
        start_points, end_points = [], []
        for row, series_name, path, entry in files_by_kind[kind]:
            start = local(entry.start_time)
            end = local(entry.end_time or entry.start_time)
            text = (
                PurePosixPath(path).name,
                series_name,
                f'{start:%Y-%m-%d %H:%M:%S}',
                f'{end:%Y-%m-%d %H:%M:%S}',
                kind,
            )
            start_points.append((start, row + offset, text))
            if end != start:
                end_points.append((end, row + offset, text))
                # The kind's first line also is its legend entry.
                lines.append(
                    go.Scatter(
                        x=[start, end],
                        y=[row + offset] * 2,
                        name=kind,
                        legendgroup=kind,
                        showlegend=False,
                        mode='lines',
                        line=dict(color=line_color, width=TIMELINE_LINE_WIDTH),
                        hoverinfo='skip',
                    )
                )

        def markers(points, symbol, size, kind=kind, color=color):
            x, y, hover = zip(*points)
            return go.Scatter(
                x=x,
                y=y,
                customdata=hover,
                name=kind,
                legendgroup=kind,
                showlegend=False,
                mode='markers',
                marker=dict(
                    color=color, symbol=symbol, size=size, opacity=1, line=outline
                ),
                hovertemplate=TIMELINE_HOVER,
            )

        starts.append(markers(start_points, TIMELINE_START_SYMBOL, TIMELINE_START_SIZE))
        if end_points:
            ends.append(markers(end_points, TIMELINE_END_SYMBOL, TIMELINE_END_SIZE))

        # The kind's legend entry: a line of its colour, with data, but a single
        # point, which a line does not draw.
        lines.append(
            go.Scatter(
                x=[start_points[0][0]],
                y=[start_points[0][1]],
                name=kind,
                legendgroup=kind,
                mode='lines',
                line=dict(color=color, width=TIMELINE_LINE_WIDTH),
                hoverinfo='skip',
            )
        )

    # The legend entries of the markers, in grey, each with one point below the
    # rows, out of the fixed range of the y-axis, and so never drawn.
    first_start = min(trace.x[0] for trace in starts)
    legend_markers = [
        go.Scatter(
            x=[first_start],
            y=[len(row_names) + 10],
            name=name,
            mode='markers',
            marker=dict(
                color=TIMELINE_OTHER_COLOR, symbol=symbol, size=size, line=outline
            ),
            hoverinfo='skip',
        )
        for name, symbol, size in (
            (TIMELINE_START_LEGEND, TIMELINE_START_SYMBOL, TIMELINE_START_SIZE),
            (TIMELINE_END_LEGEND, TIMELINE_END_SYMBOL, TIMELINE_END_SIZE),
        )
    ]
    figure = go.Figure(data=[*lines, *ends, *starts, *legend_markers])

    # Enough room per row that the kinds' offsets stay apart.
    row_height = max(20, 6 * len(kinds))
    figure.update_layout(
        template='plotly_white',
        showlegend=True,
        # NOMAD's GUI fixes the margins at the left and right of the plot, which
        # cuts off a legend at the right; above the plot, in the space kept by the
        # top margin, it stays visible.
        legend=dict(
            orientation='h',
            x=0,
            xanchor='left',
            y=1.02,
            yanchor='bottom',
            # In the order of the traces: the kinds, then the markers.
            traceorder='normal',
        ),
        # NOMAD's new GUI replaces a figure's template by its own, which turns
        # hovering off; set here, hovering stays on.
        hovermode='closest',
        # NOMAD's GUI fixes the margins once the figure is first drawn. Tick labels
        # of one line at every zoom level, which Plotly's default date ticks are
        # not, and a few of them, so they never turn, keep the space below the axis
        # the same when zooming, and the title clear of the labels.
        xaxis=dict(
            title=dict(text=f'Time ({zone})', standoff=15),
            tickformatstops=[
                dict(dtickrange=[None, 60_000], value='%b %d %H:%M:%S'),
                dict(dtickrange=[60_000, 86_400_000], value='%b %d %H:%M'),
                dict(dtickrange=[86_400_000, None], value='%b %d, %Y'),
            ],
            nticks=6,
            tickangle=0,
            automargin=True,
            # NOMAD's GUI template fixes the x-axis range; set here, scrolling zooms
            # in time.
            fixedrange=False,
        ),
        margin=dict(t=TIMELINE_LEGEND_HEIGHT, b=80),
        yaxis=dict(
            title='Groups',
            tickmode='array',
            tickvals=list(range(len(row_names))),
            ticktext=row_names,
            range=[len(row_names) - 0.5, -0.5],
            # NOMAD's GUI template would fit the range to the data instead.
            autorange=False,
            zeroline=False,
            showgrid=False,
            # The rows stay put when scrolling, which zooms in time only.
            fixedrange=True,
        ),
        height=max(400, 150 + TIMELINE_LEGEND_HEIGHT + row_height * len(row_names)),
    )
    return [PlotlyFigure(label='Timeline', open=True, figure=figure.to_plotly_json())]


def timeline_time_zone(entries) -> tzinfo:
    """The time zone of the timeline for the files of `entries`: the
    `LOCAL_TIME_ZONE` of their institutions if all of them have the same, else UTC,
    as for institutions in different zones or without one."""
    modules = {module.INSTITUTION: module for module in INSTITUTIONS}
    zones = {
        getattr(modules.get(entry.institution), 'LOCAL_TIME_ZONE', None)
        for entry in entries
    }
    if len(zones) == 1 and None not in zones:
        return zones.pop()
    return timezone.utc


def rgba(red: int, green: int, blue: int, opacity: float = 1) -> str:
    """A Plotly colour with the given `opacity`."""
    return f'rgba({red}, {green}, {blue}, {opacity})'
