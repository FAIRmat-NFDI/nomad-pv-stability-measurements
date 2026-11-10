from typing import (
    TYPE_CHECKING,
)

if TYPE_CHECKING:
    from nomad.datamodel.datamodel import (
        EntryArchive,
    )
    from structlog.stdlib import (
        BoundLogger,
    )

from datetime import datetime, timezone, tzinfo
from pathlib import PurePosixPath
from urllib.parse import urlencode

import numpy as np
from nomad.config import config
from nomad.datamodel.data import ArchiveSection, EntryData, Schema
from nomad.datamodel.metainfo.annotations import (
    BrowserAdaptors,
    BrowserAnnotation,
    ELNAnnotation,
    ELNComponentEnum,
    Filter,
    SectionDisplayAnnotation,
)
from nomad.datamodel.metainfo.basesections import BaseSection
from nomad.datamodel.metainfo.plot import PlotlyFigure, PlotSection
from nomad.metainfo import (
    URL,
    Datetime,
    MEnum,
    MetainfoReferenceError,
    Quantity,
    SchemaPackage,
    Section,
    SubSection,
)
from nomad.utils import generate_entry_id

from nomad_pv_stability_measurements.file_reading import INSTITUTIONS

configuration = config.get_plugin_entry_point(
    'nomad_pv_stability_measurements.schema_packages:schema_package_entry_point'
)

m_package = SchemaPackage()


class NewSchemaPackage(Schema):
    name = Quantity(
        type=str, a_eln=ELNAnnotation(component=ELNComponentEnum.StringEditQuantity)
    )
    message = Quantity(type=str)

    def normalize(self, archive: 'EntryArchive', logger: 'BoundLogger') -> None:
        super().normalize(archive, logger)

        logger.info('NewSchema.normalize', parameter=configuration.parameter)
        self.message = f'Hello {self.name}!'


#: What was measured in a file. New kinds may be added; existing ones are never
#: removed or renamed, so that stored entries stay valid.
MEASUREMENT_KINDS = [
    'jv',
    'dark_jv',
    'mpp_tracking',
    'stability_series',
    'jv_parameters',
    'eqe',
    'pl',
    'el',
    'impedance',
    'uv_vis',
    'image',
    'pl_image',
    'el_image',
    'environment_log',
    'metadata',
    'measurement_protocol',
    'XRD',
    'SEM',
    'other',
    'unknown',
]

#: How a file is stored, independent of what it contains. Same rule as for
#: `MEASUREMENT_KINDS`: values are only ever added.
FILE_FORMATS = [
    'csv',
    'tsv',
    'txt',
    'dat',
    'json',
    'yaml',
    'xml',
    'xlsx',
    'xls',
    'ods',
    'hdf5',
    'nexus',
    'mat',
    'png',
    'jpg',
    'tiff',
    'bmp',
    'pdf',
    'docx',
    'zip',
    'other',
    'unknown',
]


#: The sample under which a summary lists the files whose sample is not known.
UNKNOWN_SAMPLE = 'Unknown'


class StabilityFile(EntryData):
    """
    The entry made from one file of a stability upload, registered with what is
    known about it.

    Values are stored as the institution's reading code provides them; this section
    does not interpret file contents. Fields that nothing could determine stay empty.
    """

    file = Quantity(
        type=str,
        description='The path of the file, relative to the upload.',
        a_browser=BrowserAnnotation(adaptor=BrowserAdaptors.RawFileAdaptor),
    )

    institution = Quantity(
        type=str,
        description="""
        Short name of the institution whose folder of the upload the file is in, or,
        for a file in no institution's folder, the institution of the uploader's
        email domain. Its reading code determines the other values. Empty if neither
        names an institution.
        """,
    )

    measurement_kind = Quantity(
        type=MEnum(*MEASUREMENT_KINDS),
        default='unknown',
        description="""
        What was measured, as recognized by the institution's reading code. The same
        file format can hold different kinds of measurements.
        """,
    )

    file_format = Quantity(
        type=MEnum(*FILE_FORMATS),
        default='unknown',
        description='How the file is stored, as given by its file name extension.',
    )

    start_time = Quantity(
        type=Datetime,
        description="""
        When the measurement in this file started, as an absolute time. Give a
        datetime with its time zone, the one where the measurement ran, or in UTC.
        NOMAD stores it in UTC, and a time without a time zone is read as UTC.
        Converting a file's local times is the job of the institution's reading code.
        """,
    )

    end_time = Quantity(
        type=Datetime,
        description="""
        When the measurement in this file finished, as an absolute time, with the
        same time zone rule as `start_time`. Equal to `start_time` if the
        institution's reading code gives no end, as for a measurement that takes
        only seconds.
        """,
    )

    sample_id = Quantity(
        type=str,
        description="""
        The identifier of the measured sample as the institution writes it. Empty if
        the institution's reading code does not know it.
        """,
    )

    sample_reference = Quantity(
        type=str,
        description="""
        A URI identifying the sample: a NOMAD entry, an external database, or any
        other resolvable identifier.
        """,
    )

    duration = Quantity(
        type=np.float64,
        unit='hour',
        description="""
        How long the measurement ran, from `start_time` to `end_time`; zero for a
        measurement without an end time. Derived on normalization. Empty without a
        start time.
        """,
    )

    def normalize(self, archive: 'EntryArchive', logger: 'BoundLogger') -> None:
        super().normalize(archive, logger)
        self.duration = None
        if self.start_time is not None:
            end_time = self.end_time or self.start_time
            self.duration = (end_time - self.start_time).total_seconds() / 3600


class StabilityFileReference(ArchiveSection):
    """
    One file of a stability upload in its summary: the file's path and a reference
    to the file's own entry, which holds what is known about it.

    The reference is resolved only when it is followed, so it may be written before
    the file's entry exists.
    """

    file = Quantity(
        type=str,
        description='The path of the file, relative to the upload.',
        a_browser=BrowserAnnotation(adaptor=BrowserAdaptors.RawFileAdaptor),
    )
    entry = Quantity(
        type=StabilityFile,
        description='The entry made from the file.',
    )


class StabilitySampleGroup(ArchiveSection):
    """The files of one sample of a stability upload, in the order they were measured.
    What is known about the sample is in the files' entries."""

    sample_id = Quantity(
        type=str,
        description=f"""
        The identifier of the sample as the institution writes it, or
        `{UNKNOWN_SAMPLE}` for the files whose sample is not known. A sample that the
        institution itself names `{UNKNOWN_SAMPLE}` shares that group.
        """,
    )
    files = SubSection(
        section_def=StabilityFileReference,
        repeats=True,
        description="""
        One record per file of the sample, ordered by start time. Files without a start
        time come last.
        """,
    )


class StabilityUploadSummary(PlotSection, BaseSection, EntryData):
    """
    All files of one stability upload, grouped by sample, with the institutions that
    measured them and the proposal under which they were measured.

    Its figure shows when each sample was measured: one row per sample, one dot per
    file at the file's start time, coloured by measurement kind.
    """

    # An upload has no lab ID, and the time NOMAD fills in is only that of the
    # first processing, so both are not shown.
    m_def = Section(
        a_display=SectionDisplayAnnotation(
            visible=Filter(exclude=['lab_id', 'datetime'])
        )
    )

    institutions = Quantity(
        type=str,
        shape=['*'],
        description="""
        Short names of the institutions that measured the files of this upload, one
        per institution folder, and that of the uploader's email domain if files lie
        in no institution's folder. Derived from the files; values entered here are
        replaced.
        """,
    )
    proposal = Quantity(
        type=str,
        description='A URI of the proposal under which these measurements were made.',
        a_eln=ELNAnnotation(component=ELNComponentEnum.URLEditQuantity),
    )
    files_app = Quantity(
        type=URL,
        description="""
        Opens the app "Stability files" in NOMAD's new GUI with the files of this
        upload: their plots, filters and table. Derived from the upload.
        """,
    )
    files_app_classic = Quantity(
        type=URL,
        description="""
        Opens the app "Stability files" in NOMAD's classic GUI with the files of this
        upload. Derived from the upload.
        """,
    )

    file_groups = SubSection(
        section_def=StabilitySampleGroup,
        repeats=True,
        description=f"""
        Every file of the upload, grouped by sample, ordered by sample identifier.
        Each file is in exactly one group; the files whose sample is not known are in
        a last group `{UNKNOWN_SAMPLE}`. Derived from the files' entries; records
        entered here are replaced.
        """,
    )

    def normalize(self, archive: 'EntryArchive', logger: 'BoundLogger') -> None:
        """Groups every registered file of the upload by the sample its entry names,
        with a reference to the entry, and derives `institutions` from the files'
        institution folders or else the uploader's email domain.

        `institutions` follows from the upload's file paths and its uploader alone.
        The groups read the files' entries, which NOMAD processes before the summary;
        a file without sample, or whose entry cannot be read, is in the group
        `UNKNOWN_SAMPLE`."""
        super().normalize(archive, logger)

        # Imported here, because the parser module imports this module.
        from nomad_pv_stability_measurements.parsers.stability_file_parser import (
            institution_of,
            is_registered,
            uploader_email,
        )

        upload_files = getattr(archive.m_context, 'upload_files', None)
        upload_id = archive.metadata.upload_id if archive.metadata else None
        if upload_id is not None:
            self.files_app, self.files_app_classic = _files_app_urls(upload_id)
        if upload_files is None or upload_id is None:
            return

        paths = sorted(
            info.path
            for info in upload_files.raw_listdir(recursive=True, files_only=True)
            if is_registered(info.path)
        )
        email = uploader_email(archive)
        institutions = {institution_of(path, email) for path in paths}
        self.institutions = sorted(
            institution.INSTITUTION for institution in institutions if institution
        )

        # An entry's id follows from its upload and its file, so the reference can be
        # written whether or not the entry exists yet.
        references = {
            path: f'../uploads/{upload_id}/archive/'
            f'{generate_entry_id(upload_id, path)}#data'
            for path in paths
        }
        # A reference is followed through the archive it is part of, so the records
        # are attached to the summary before their entries are read.
        self.file_groups = [
            StabilitySampleGroup(
                files=[
                    StabilityFileReference(file=path, entry=reference)
                    for path, reference in references.items()
                ]
            )
        ]
        entries = {}
        for record in self.file_groups[0].files:
            try:
                entries[record.file] = record.entry.m_resolved()
            except MetainfoReferenceError:
                logger.warning('Could not read the entry of a file.', file=record.file)
                entries[record.file] = None

        by_sample: dict[str, StabilitySampleGroup] = {}
        for path in paths:
            entry = entries[path]
            sample_id = (entry.sample_id if entry else None) or UNKNOWN_SAMPLE
            group = by_sample.setdefault(
                sample_id, StabilitySampleGroup(sample_id=sample_id)
            )
            group.files.append(
                StabilityFileReference(file=path, entry=references[path])
            )

        def measured_first(record):
            entry = entries[record.file]
            start_time = entry.start_time if entry else None
            # Put missing times last and use the file path to break ties.
            return (start_time is None, start_time, record.file)

        # Order groups by sample identifier, with the unknown-sample group last.
        ordered_ids = sorted(
            by_sample, key=lambda sample_id: (sample_id == UNKNOWN_SAMPLE, sample_id)
        )
        self.file_groups = []
        for sample_id in ordered_ids:
            group = by_sample[sample_id]
            group.files = sorted(group.files, key=measured_first)
            self.file_groups.append(group)

        self.figures = _measurement_timeline(self.file_groups, entries)


#: Sizes in the measurement timeline, in pixels: of the circle at a file's start,
#: of the smaller triangle at its end, which hides behind the circle when zoomed
#: out, and of the line between them, thinner still so the triangle stands out.
TIMELINE_START_SIZE = 10
TIMELINE_END_SIZE = 7
TIMELINE_LINE_WIDTH = 3

#: How opaque a file's line is, so that overlapping files stay visible. The
#: markers at its start and end are opaque.
TIMELINE_LINE_OPACITY = 0.35

#: The colours of the measurement kinds in the timeline. NOMAD's GUI shows a figure
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
}
TIMELINE_OTHER_COLOR = '#8c8c8c'

#: The outline of the markers: a mid grey, which stands out on a light and on a
#: dark background, and around a marker over another one.
TIMELINE_OUTLINE_COLOR = '#808080'
TIMELINE_OUTLINE_WIDTH = 0.5

#: Space above the timeline for the legend, in pixels.
TIMELINE_LEGEND_HEIGHT = 50

#: The part of a sample's row over which the kinds are spread, in rows.
TIMELINE_ROW_SPREAD = 0.6

#: The Plotly marker symbols at the start and the end of a measurement.
TIMELINE_START_SYMBOL = 'circle'
TIMELINE_END_SYMBOL = 'triangle-up'

#: The legend entries that explain the start and end markers.
TIMELINE_START_LEGEND = 'start_time'
TIMELINE_END_LEGEND = 'end_time'

#: The hover text of a file's markers.
TIMELINE_HOVER = (
    '<b>%{customdata[0]}</b><br>'
    'sample_id: %{customdata[1]}<br>'
    'start_time: %{customdata[2]}<br>'
    'end_time: %{customdata[3]}<br>'
    # `<extra></extra>` leaves out the box with the trace's name.
    'type: %{customdata[4]}<extra></extra>'
)


def _measurement_timeline(
    file_groups: list[StabilitySampleGroup], entries: dict
) -> list[PlotlyFigure]:
    """A figure with one row per sample and one line per file from the start to the
    end of its measurement, coloured by measurement kind. Hovering over a file's
    markers shows the file name, its sample, start and end time, and kind. A circle
    marks the start and a smaller triangle the end, both in the kind's full colour
    with a grey outline; the thinner line between them is translucent, so that
    overlapping files stay visible. Circles are drawn over all triangles, and these
    over all lines. A file that ends when it starts is one circle. The legend shows
    each kind as a line, which shows and hides the kind's files, and the two markers
    in grey.

    Every trace, legend entries included, holds data and no gaps: NOMAD's new GUI
    does not show traces without data, nor their legend entries.

    Within a sample's row, each kind of the upload has its own slight vertical
    offset, so that files of different kinds over the same time stay apart.

    Files without start time are not plotted, and a sample without such files, the
    group `UNKNOWN_SAMPLE` included, has no row. Without any plottable file, no
    figure. Rows keep the order of `file_groups`, top to bottom. Each kind has the
    colour of `TIMELINE_KIND_COLORS`, the same in every upload. An entry made before
    end times existed ends when it starts. Times are in the zone given by
    `_timeline_time_zone`."""
    import plotly.graph_objects as go
    from plotly.colors import hex_to_rgb

    def plottable(record):
        entry = entries[record.file]
        return entry is not None and entry.start_time is not None

    rows = [group for group in file_groups if any(map(plottable, group.files))]
    sample_ids = [group.sample_id for group in rows]
    files_by_kind: dict[str, list] = {}
    for row, group in enumerate(rows):
        for record in filter(plottable, group.files):
            entry = entries[record.file]
            files_by_kind.setdefault(entry.measurement_kind or 'unknown', []).append(
                (row, group.sample_id, record.file, entry)
            )
    if not files_by_kind:
        return []

    zone = _timeline_time_zone(
        entry for files in files_by_kind.values() for *_, entry in files
    )

    def local(time: datetime) -> datetime:
        # Plotly ignores time zones, so the times are given as written in `zone`.
        if time.tzinfo is None:
            time = time.replace(tzinfo=timezone.utc)
        return time.astimezone(zone).replace(tzinfo=None)

    kinds = sorted(files_by_kind, key=MEASUREMENT_KINDS.index)
    spacing = TIMELINE_ROW_SPREAD / max(len(kinds) - 1, 1)
    outline = dict(color=TIMELINE_OUTLINE_COLOR, width=TIMELINE_OUTLINE_WIDTH)
    lines, ends, starts = [], [], []
    for index, kind in enumerate(kinds):
        offset = (index - (len(kinds) - 1) / 2) * spacing
        red, green, blue = hex_to_rgb(
            TIMELINE_KIND_COLORS.get(kind, TIMELINE_OTHER_COLOR)
        )
        color = _rgba(red, green, blue)
        line_color = _rgba(red, green, blue, TIMELINE_LINE_OPACITY)
        # The start and the end of each file, with its hover text.
        start_points, end_points = [], []
        for row, sample_id, path, entry in files_by_kind[kind]:
            start = local(entry.start_time)
            end = local(entry.end_time or entry.start_time)
            text = (
                PurePosixPath(path).name,
                sample_id,
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
            y=[len(sample_ids) + 10],
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
            title='Sample',
            tickmode='array',
            tickvals=list(range(len(sample_ids))),
            ticktext=sample_ids,
            range=[len(sample_ids) - 0.5, -0.5],
            # NOMAD's GUI template would fit the range to the data instead.
            autorange=False,
            zeroline=False,
            showgrid=False,
            # The rows stay put when scrolling, which zooms in time only.
            fixedrange=True,
        ),
        height=max(400, 150 + TIMELINE_LEGEND_HEIGHT + row_height * len(sample_ids)),
    )
    return [
        PlotlyFigure(
            label='Measurement timeline', open=True, figure=figure.to_plotly_json()
        )
    ]


def _files_app_urls(upload_id: str) -> tuple[str, str]:
    """The addresses of the app "Stability files", filtered to the files of the
    upload `upload_id`, in NOMAD's new and in its classic GUI."""
    from nomad_pv_stability_measurements.apps.stability_files import (
        stability_files_app,
    )

    query = urlencode({'upload_id': upload_id})
    path = stability_files_app.path
    # The new GUI is served by its own plugin, below the classic GUI's path unless
    # that plugin says otherwise.
    try:
        gui_v2 = config.get_plugin_entry_point('nomad_gui.apis:gui_api')
        base_v2 = config.services.base_url(True) + gui_v2.get_public_base_path()
    except Exception:
        base_v2 = config.gui_url('v2')
    return (
        f'{base_v2}/apps/{path}?{query}',
        f'{config.gui_url(f"search/{path}")}?{query}',
    )


def _timeline_time_zone(entries) -> tzinfo:
    """The time zone of the measurement timeline for the files of `entries`: the
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


def _rgba(red: int, green: int, blue: int, opacity: float = 1) -> str:
    """A Plotly colour with the given `opacity`."""
    return f'rgba({red}, {green}, {blue}, {opacity})'


m_package.__init_metainfo__()
