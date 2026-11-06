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

from pathlib import PurePosixPath

from nomad.config import config
from nomad.datamodel.data import ArchiveSection, EntryData, Schema
from nomad.datamodel.metainfo.annotations import (
    BrowserAdaptors,
    BrowserAnnotation,
    ELNAnnotation,
    ELNComponentEnum,
)
from nomad.datamodel.metainfo.basesections import BaseSection
from nomad.datamodel.metainfo.plot import PlotlyFigure, PlotSection
from nomad.metainfo import (
    Datetime,
    MEnum,
    MetainfoReferenceError,
    Quantity,
    SchemaPackage,
    SubSection,
)
from nomad.utils import generate_entry_id

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


class StabilitySampleIdentity(ArchiveSection):
    """Sample identity reported by the institution's reading code."""

    id = Quantity(
        type=str,
        description='The identifier of the sample as the institution writes it.',
    )

    reference = Quantity(
        type=str,
        description="""
        A URI identifying the sample: a NOMAD entry, an external database, or any
        other resolvable identifier.
        """,
    )


class StabilityFile(ArchiveSection):
    """
    One file of a stability upload, registered with what is known about it.

    Values are stored as the institution's reading code provides them; this section
    does not interpret file contents. Fields that nothing could determine stay empty.
    """

    file = Quantity(
        type=str,
        description='The path of the file, relative to the upload.',
        a_eln=ELNAnnotation(component=ELNComponentEnum.FileEditQuantity),
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

    time_stamp = Quantity(
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
        same time zone rule as `time_stamp`. Equal to `time_stamp` if the
        institution's reading code gives no end, as for a measurement that takes
        only seconds.
        """,
    )

    sample = SubSection(section_def=StabilitySampleIdentity)


class StabilityFileEntry(StabilityFile, EntryData):
    """The entry made from one file of a stability upload."""


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
        type=StabilityFileEntry,
        description='The entry made from the file.',
    )


class StabilitySample(ArchiveSection):
    """The files of one sample of a stability upload, in the order they were measured."""

    sample = SubSection(section_def=StabilitySampleIdentity)
    files = SubSection(
        section_def=StabilityFileReference,
        repeats=True,
        description="""
        One record per file of the sample, ordered by time stamp. Files without a time
        stamp come last.
        """,
    )


class StabilityUploadSummary(PlotSection, BaseSection, EntryData):
    """
    All files of one stability upload, with the institutions that measured them and
    the proposal under which they were measured.

    Its figure shows when each sample was measured: one row per sample, one dot per
    file at the file's time stamp, coloured by measurement kind.
    """

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

    files = SubSection(
        section_def=StabilityFileReference,
        repeats=True,
        description="""
        One record per file of the upload, referencing the file's entry. Derived from
        the files; records entered here are replaced.
        """,
    )
    samples = SubSection(
        section_def=StabilitySample,
        repeats=True,
        description="""
        The files of the upload grouped by sample, ordered by sample identifier. The
        files whose sample is not known are in a last group without identifier.
        Derived from the files' entries; records entered here are replaced.
        """,
    )

    def normalize(self, archive: 'EntryArchive', logger: 'BoundLogger') -> None:
        """Lists every registered file of the upload with a reference to its entry,
        derives `institutions` from the files' institution folders or else the
        uploader's email domain, and groups the files by the sample their entries
        name.

        `files` and `institutions` follow from the upload's file paths and its
        uploader alone. The
        groups read the files' entries, which NOMAD processes before the summary; a
        file whose entry cannot be read is in the group without sample."""
        super().normalize(archive, logger)

        # Imported here, because the parser module imports this module.
        from nomad_pv_stability_measurements.parsers.stability_file_parser import (
            institution_of,
            is_registered,
            uploader_email,
        )

        upload_files = getattr(archive.m_context, 'upload_files', None)
        upload_id = archive.metadata.upload_id if archive.metadata else None
        if upload_files is None or upload_id is None:
            return

        paths = sorted(
            info.path
            for info in upload_files.raw_listdir(recursive=True, files_only=True)
            if is_registered(info.path)
        )
        # An entry's id follows from its upload and its file, so the reference can be
        # written whether or not the entry exists yet.
        references = {
            path: f'../uploads/{upload_id}/archive/'
            f'{generate_entry_id(upload_id, path)}#data'
            for path in paths
        }
        self.files = [
            StabilityFileReference(file=path, entry=reference)
            for path, reference in references.items()
        ]
        email = uploader_email(archive)
        institutions = {institution_of(path, email) for path in paths}
        self.institutions = sorted(
            institution.INSTITUTION for institution in institutions if institution
        )

        # Build each sample group while reading its files' entries.
        by_sample: dict[str | None, StabilitySample] = {}
        measurement_times = {}
        entries = {}
        for record in self.files:
            try:
                entry = record.entry
                sample_id = entry.sample.id if entry.sample else None
            except MetainfoReferenceError:
                logger.warning('Could not read the entry of a file.', file=record.file)
                entry, sample_id = None, None

            # Create a group when its first file is encountered.
            if sample_id not in by_sample:
                by_sample[sample_id] = StabilitySample(
                    sample=StabilitySampleIdentity(id=sample_id)
                )
            group = by_sample[sample_id]

            # Keep the first non-empty reference, even if earlier files had none.
            if not group.sample.reference:
                if entry and entry.sample and entry.sample.reference:
                    group.sample.reference = entry.sample.reference

            # Give the group its own file record pointing to the same entry.
            group.files.append(
                StabilityFileReference(file=record.file, entry=references[record.file])
            )
            # Remember the measurement time so sorting does not need to read the entry.
            measurement_times[record.file] = entry.time_stamp if entry else None
            entries[record.file] = entry

        def measured_first(record):
            time_stamp = measurement_times[record.file]
            # Put missing times last and use the file path to break ties.
            return (time_stamp is None, time_stamp, record.file)

        # Order groups by sample identifier, with the unknown-sample group last.
        ordered_ids = sorted(
            by_sample, key=lambda sample_id: (sample_id is None, sample_id or '')
        )
        self.samples = []
        for sample_id in ordered_ids:
            group = by_sample[sample_id]
            # Sort each group's files by measurement time before adding it to the summary.
            group.files = sorted(group.files, key=measured_first)
            self.samples.append(group)

        self.figures = _measurement_timeline(self.samples, entries)


#: Size of a file's dots in the measurement timeline, in pixels. A file's line from
#: start to end is as thick as its dots.
TIMELINE_MARKER_SIZE = 8

#: How opaque dots and lines are, so that overlapping files stay visible.
TIMELINE_OPACITY = 0.5

#: The part of a sample's row over which the kinds are spread, in rows.
TIMELINE_ROW_SPREAD = 0.6

#: How much paler the dot at the end of a measurement is than the one at its start:
#: the share of white mixed into the kind's colour.
TIMELINE_END_PALENESS = 0.6

#: The legend entry that explains the paler dots.
TIMELINE_END_LEGEND = 'paler dot: end of a measurement'


def _measurement_timeline(
    samples: list[StabilitySample], entries: dict
) -> list[PlotlyFigure]:
    """A figure with one row per sample and one line per file from the start to the
    end of its measurement, with a dot at both ends, coloured by measurement kind,
    with the file name shown on hover. The dot at the end is paler than the one at
    the start, as a grey entry of the legend explains. A file that ends when it
    starts is one dot, in the colour of a start.

    Within a sample's row, each kind of the upload has its own slight vertical
    offset, so that files of different kinds over the same time stay apart. Dots and
    lines are translucent, so that overlapping files stay visible.

    Files without sample or time stamp are not plotted. Without any plottable file,
    no figure. Rows keep the order of `samples`, top to bottom. Each kind has its
    own colour, the same in every upload. An entry made before end times existed
    ends when it starts."""
    import plotly.graph_objects as go
    from plotly.colors import hex_to_rgb, qualitative

    rows = [group for group in samples if group.sample.id is not None]
    sample_ids = [group.sample.id for group in rows]
    files_by_kind: dict[str, list] = {}
    for row, group in enumerate(rows):
        for record in group.files:
            entry = entries[record.file]
            if entry is None or entry.time_stamp is None:
                continue
            files_by_kind.setdefault(entry.measurement_kind or 'unknown', []).append(
                (row, group.sample.id, record.file, entry)
            )
    if not files_by_kind:
        return []

    kinds = sorted(files_by_kind, key=MEASUREMENT_KINDS.index)
    spacing = TIMELINE_ROW_SPREAD / max(len(kinds) - 1, 1)
    # Dark24 has more colours than there are measurement kinds.
    colors = qualitative.Dark24
    figure = go.Figure()
    for index, kind in enumerate(kinds):
        offset = (index - (len(kinds) - 1) / 2) * spacing
        red, green, blue = hex_to_rgb(colors[MEASUREMENT_KINDS.index(kind)])
        color = _rgba(red, green, blue)
        pale = _rgba(*(_paler(value) for value in (red, green, blue)))
        x, y, hover, dot_colors = [], [], [], []
        for row, sample_id, path, entry in files_by_kind[kind]:
            start = entry.time_stamp
            end = entry.end_time or start
            text = (
                PurePosixPath(path).name,
                sample_id,
                f'{start:%Y-%m-%d %H:%M:%S}',
                f'{end:%Y-%m-%d %H:%M:%S}',
            )
            # One point for a file that ends when it starts, else its two ends;
            # `None` separates the files.
            times = [start] if end == start else [start, end]
            x += [*times, None]
            y += [row + offset] * len(times) + [None]
            hover += [text] * len(times) + [None]
            dot_colors += [color, pale][: len(times)] + [color]

        figure.add_trace(
            go.Scatter(
                x=x,
                y=y,
                customdata=hover,
                name=kind,
                mode='lines+markers',
                connectgaps=False,
                line=dict(color=color, width=TIMELINE_MARKER_SIZE),
                marker=dict(color=dot_colors, size=TIMELINE_MARKER_SIZE),
                hovertemplate='%{customdata[0]}<br>%{customdata[1]}<br>'
                '%{customdata[2]} – %{customdata[3]}',
            )
        )

    # A legend entry without data, in grey, for what the paler dots mean.
    grey = _paler(0)
    figure.add_trace(
        go.Scatter(
            x=[None],
            y=[None],
            name=TIMELINE_END_LEGEND,
            mode='markers',
            marker=dict(color=_rgba(grey, grey, grey), size=TIMELINE_MARKER_SIZE),
            hoverinfo='skip',
        )
    )

    # Enough room per row that the kinds' offsets stay apart.
    row_height = max(20, 6 * len(kinds))
    figure.update_layout(
        template='plotly_white',
        showlegend=True,
        legend_title_text='Measurement kind',
        # NOMAD's new GUI replaces a figure's template by its own, which turns
        # hovering off; set here, hovering stays on.
        hovermode='closest',
        # NOMAD's GUI fixes the margins once the figure is first drawn. Tick labels
        # of one line at every zoom level, which Plotly's default date ticks are
        # not, and a few of them, so they never turn, keep the space below the axis
        # the same when zooming, and the title clear of the labels.
        xaxis=dict(
            title=dict(text='Time (UTC)', standoff=15),
            tickformatstops=[
                dict(dtickrange=[None, 60_000], value='%b %d %H:%M:%S'),
                dict(dtickrange=[60_000, 86_400_000], value='%b %d %H:%M'),
                dict(dtickrange=[86_400_000, None], value='%b %d, %Y'),
            ],
            nticks=6,
            tickangle=0,
            automargin=True,
        ),
        margin=dict(b=80),
        yaxis=dict(
            title='Sample',
            tickmode='array',
            tickvals=list(range(len(sample_ids))),
            ticktext=sample_ids,
            range=[len(sample_ids) - 0.5, -0.5],
            zeroline=False,
            showgrid=False,
        ),
        height=max(400, 150 + row_height * len(sample_ids)),
    )
    return [
        PlotlyFigure(
            label='Measurement timeline', open=True, figure=figure.to_plotly_json()
        )
    ]


def _paler(value: int) -> int:
    """A colour channel's `value` mixed with white by `TIMELINE_END_PALENESS`."""
    return round(value + (255 - value) * TIMELINE_END_PALENESS)


def _rgba(red: int, green: int, blue: int) -> str:
    """A Plotly colour with the timeline's translucency."""
    return f'rgba({red}, {green}, {blue}, {TIMELINE_OPACITY})'


m_package.__init_metainfo__()
