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


import numpy as np
from nomad.datamodel.context import ServerContext
from nomad.datamodel.data import ArchiveSection, EntryData
from nomad.datamodel.metainfo.annotations import (
    BrowserAdaptors,
    BrowserAnnotation,
    ELNComponentEnum,
)
from nomad.datamodel.metainfo.plot import PlotSection
from nomad.metainfo import (
    URL,
    Datetime,
    MEnum,
    Quantity,
    SchemaPackage,
    SubSection,
)
from nomad.parsing.tabular import TableData
from nomad.utils import generate_entry_id
from nomad_pv_stability_standards.schema_packages.standard import AppliedStandard

from nomad_pv_stability_measurements.schema_packages.plotting_utils import (
    file_timeline,
)
from nomad_pv_stability_measurements.schema_packages.sample_schema import (
    SolarCellSample,
)
from nomad_pv_stability_measurements.schema_packages.utils import (
    GENERAL_GROUP,
    QUIET,
    UNKNOWN_SAMPLE,
    applied_standards,
    eln,
    files_app_url,
    group_of,
    sample_series,
    split_commas,
    stability_file,
    tabular,
)

m_package = SchemaPackage()


#: What a file of a stability upload holds, e.g. a J-V curve or an environment
#: log. New types may be added; existing ones are never removed or renamed, so
#: that stored entries stay valid.
STABILITY_FILE_TYPES = [
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
    # Logs of the conditions at the test setup: a climate chamber, an oven, the
    # laboratory, or sensors next to the samples outdoors.
    'setup_log',
    # Weather data of an outdoor test site, e.g. from its meteorological station:
    # irradiance, air temperature, wind, rain.
    'weather_information',
    'metadata',
    'measurement_protocol',
    'XRD',
    'SEM',
    'other',
    'unknown',
    # Deprecated: the name of `setup_log` until 2026-11, kept so that stored entries
    # and spreadsheets stay valid.
    'environment_log',
]

#: How a file is stored, independent of what it contains. Same rule as for
#: `STABILITY_FILE_TYPES`: values are only ever added.
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

#: Where the data of a file comes from, with what each value means. Same rule as for
#: `STABILITY_FILE_TYPES`: values are only ever added.
PROVENANCES = {
    'measured': 'Measured on the sample.',
    'simulated': 'Computed by a model of the sample.',
    'derived': (
        'Computed from other data, such as figures of merit fitted to measured curves.'
    ),
    'imported': 'Taken from another source, such as a database.',
    'literature': 'Taken from a publication.',
    'note': 'Written by hand, such as lab notes or values typed in.',
    'reference': (
        'Measured on a reference device or standard rather than on the sample '
        'studied, such as a calibration.'
    ),
    'other': 'From a source that none of the other values describes.',
    'unknown': 'Not known.',
}


class SampleIdentity(ArchiveSection):
    """
    Which sample a file or a series is about: as the institution names it, as the
    sample entry of the upload, and as an identifier outside the upload.
    """

    sample_id = Quantity(
        type=str,
        description="""
        The identifier of the sample as the institution writes it, without spaces at
        its start and end. Empty if nothing gives it.
        """,
    )
    entry = Quantity(
        type=SolarCellSample,
        description="""
        The sample entry of the upload whose identifier is `sample_id`, made from the
        sheet `samples` of the project data spreadsheet. Empty without such a sample.
        """,
    )
    external_reference = Quantity(
        type=URL,
        description="""
        Where the sample is described outside the upload: an external database, a
        DOI, or a NOMAD entry of another upload.
        """,
    )


class StabilityFile(EntryData):
    """
    The entry made from one file of a stability upload, registered with what is
    known about it.

    The values come from the sheet `files` of the upload's project data
    spreadsheet where a row matches the file, and otherwise from the institution's
    reading code; this section does not interpret file contents. Fields that
    nothing could determine stay empty.
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
        email domain. Its reading code determines the values that the project data
        does not give. Empty if neither names an institution.
        """,
    )

    stability_file_type = Quantity(
        type=MEnum(*STABILITY_FILE_TYPES),
        default='unknown',
        # The name until 2026-11, so that stored entries keep their value.
        aliases=['measurement_kind'],
        description="""
        What the file holds, e.g. a J-V curve, MPP tracking or an environment log.
        The same file format can hold different types of files.
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
        The start of the period of the stability test that the file's data cover, as
        an absolute time: for measured data when the recording started, for a
        simulation of the test the start of the period it simulates. Empty where the
        data have no time in the calendar, such as a simulation over model time; then
        `duration` may give their length. Give a datetime with its time zone, the one
        where the data were taken, or in UTC. NOMAD stores it in UTC, and a time
        without a time zone is read as UTC. Converting a file's local times is the job
        of the institution's reading code.
        """,
    )

    end_time = Quantity(
        type=Datetime,
        description="""
        The end of the period that the file's data cover, as an absolute time, with
        the same rules as `start_time`. Equal to `start_time` if nothing gives an end,
        as for data taken within seconds, such as a J-V scan.
        """,
    )

    provenance = Quantity(
        type=MEnum(*PROVENANCES, m_descriptions=PROVENANCES),
        default='measured',
        description="""
        Where the data of the file comes from; each value is described with the
        enumeration.
        """,
    )

    sample_identity = SubSection(
        section_def=SampleIdentity,
        description='The sample the file is about. Empty if nothing names one.',
    )

    duration = Quantity(
        type=np.float64,
        unit='hour',
        description="""
        How long a period the file's data cover. With a `start_time`, derived on
        normalization from `start_time` to `end_time`, zero without an end time.
        Without a `start_time`, as given, e.g. in the sheet `files`: for a simulation
        over 1000 h of model time, 1000; empty if nothing gives it.
        """,
    )

    def normalize(self, archive: 'EntryArchive', logger: 'BoundLogger') -> None:
        super().normalize(archive, logger)
        if self.start_time is not None:
            end_time = self.end_time or self.start_time
            self.duration = (end_time - self.start_time).total_seconds() / 3600


class StabilityFileReference(ArchiveSection):
    """
    One file of a stability upload in its project entry: the file's path and a
    reference to the file's own entry, which holds what is known about it.

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


class StabilityFileGroup(ArchiveSection):
    """A group of files of a stability upload, ordered by when their data start:
    either the series of one sample, its stability test, with the sample and the
    standards applied to it; or the files that belong to no sample, of a general type
    (`GENERAL_FILE_TYPES`, e.g. `Setup logs`, and `GENERAL_GROUP`) or of an unknown
    sample (`UNKNOWN_SAMPLE`), without sample and standards. What is known about each
    file is in its entry."""

    name = Quantity(
        type=str,
        description=f"""
        The name of the group: the sample's identifier, the name of a general type of
        files (e.g. `Setup logs` or `{GENERAL_GROUP}`), or `{UNKNOWN_SAMPLE}`.
        """,
    )
    sample_identity = SubSection(
        section_def=SampleIdentity,
        description=f"""
        The sample of a sample's series; empty for the other groups. A sample that
        the institution itself names `{UNKNOWN_SAMPLE}` shares the group of the files
        without sample.
        """,
    )
    applied_standards = SubSection(
        section_def=AppliedStandard,
        repeats=True,
        description="""
        The standards applied to the sample, one after the other or at once, each with
        the choices made among its options, referencing the standard in a catalogue
        every user can see. Set from the column `standard` of the sheet `samples` on
        import, in its order; edits stay until the next import. Only for a sample's
        series.
        """,
    )
    files = SubSection(
        section_def=StabilityFileReference,
        repeats=True,
        description="""
        One record per file of the group, ordered by start time. Files without a
        start time come last.
        """,
    )


class ProjectData(PlotSection, EntryData, TableData):
    """
    One stability upload as a project: the proposal as submitted in GATE
    (READY-PV) and the samples, which can be edited, and an overview of the upload's
    files, which is derived on every normalization: the institutions, the file
    groups (the files of each sample, with the standard applied to it, and of each
    general type, such as the environment), a link to the app "Stability files", and
    a timeline of the periods that the files' data cover.

    The plugin creates it for every upload. The editable part is filled from the
    spreadsheet `data_file` while "fill archive from data file" is ticked: the first
    sheet `project` gives the proposal, and the sheet `samples` writes the sample
    entries of the upload. After that the values here hold, and edits stay until the
    spreadsheet is imported again. The sheet `files` is read by the file entries
    themselves; an import only checks it and reports its errors here.

    The timeline has one row per group and one line per file from its start to
    its end, coloured by stability file type.
    """

    data_file = Quantity(
        type=str,
        description='The spreadsheet with the project data, in the upload.',
        # Only the quantities of the first sheet; the other sheets are read by
        # the plugin.
        a_tabular_parser={
            'mapping_options': [
                {'mapping_mode': 'column', 'file_mode': 'current_entry', 'sections': []}
            ]
        },
        a_browser=BrowserAnnotation(adaptor=BrowserAdaptors.RawFileAdaptor),
        a_eln=eln(ELNComponentEnum.FileEditQuantity),
    )

    files_app = Quantity(
        type=URL,
        description="""
        Opens the app "Stability files" in NOMAD's new GUI with the files of this
        upload: their plots, filters and table. Derived from the upload.
        """,
    )

    proposal_number = Quantity(
        type=str,
        description='The number of the proposal in GATE (READY-PV).',
        a_tabular=tabular('proposal_number'),
        a_eln=eln(ELNComponentEnum.StringEditQuantity),
    )
    proposal = Quantity(
        type=str,
        description='A URI of the proposal under which the data of this upload were '
        'taken.',
        a_tabular=tabular('proposal'),
        a_eln=eln(ELNComponentEnum.URLEditQuantity),
    )
    title = Quantity(
        type=str,
        description='GATE, general proposal data: title (max. 500 characters).',
        a_tabular=tabular('title'),
        a_eln=eln(ELNComponentEnum.StringEditQuantity),
    )
    abstract = Quantity(
        type=str,
        description='GATE, general proposal data: abstract (max. 1000 characters).',
        a_tabular=tabular('abstract'),
        a_eln=eln(ELNComponentEnum.RichTextEditQuantity),
    )
    main_research_area = Quantity(
        type=str,
        description='GATE, general proposal data: main research area.',
        a_tabular=tabular('main_research_area'),
        a_eln=eln(ELNComponentEnum.StringEditQuantity),
    )
    scientific_category = Quantity(
        type=str,
        description='GATE, general proposal data: scientific category.',
        a_tabular=tabular('scientific_category'),
        a_eln=eln(ELNComponentEnum.StringEditQuantity),
    )
    funding_requested = Quantity(
        type=bool,
        description='GATE, general proposal data: whether funding was requested.',
        a_tabular=tabular('funding_requested'),
        a_eln=eln(ELNComponentEnum.BoolEditQuantity),
    )
    proposer = Quantity(
        type=str,
        description='GATE: the proposer, who submitted the proposal.',
        a_tabular=tabular('proposer'),
        a_eln=eln(ELNComponentEnum.StringEditQuantity),
    )
    co_proposers = Quantity(
        type=str,
        shape=['*'],
        description='GATE: the co-proposers; in the spreadsheet separated by commas.',
        a_tabular=tabular('co_proposers'),
        a_eln=eln(ELNComponentEnum.StringEditQuantity),
    )
    installation = Quantity(
        type=str,
        description="""
        GATE, technical requirements: the installation (instrument) of the
        proposal; one per proposal.
        """,
        a_tabular=tabular('installation'),
        a_eln=eln(ELNComponentEnum.StringEditQuantity),
    )
    instrument_scientist = Quantity(
        type=str,
        description='GATE, technical requirements: the contacted instrument scientist.',
        a_tabular=tabular('instrument_scientist'),
        a_eln=eln(ELNComponentEnum.StringEditQuantity),
    )
    experiment_start = Quantity(
        type=Datetime,
        description="""
        The start of the allocated experiment time, as ISO text, e.g. 2026-09-13;
        without a time zone read as UTC.
        """,
        a_tabular=tabular('experiment_start'),
        a_eln=eln(ELNComponentEnum.DateTimeEditQuantity),
    )
    experiment_end = Quantity(
        type=Datetime,
        description='The end of the allocated experiment time, as `experiment_start`.',
        a_tabular=tabular('experiment_end'),
        a_eln=eln(ELNComponentEnum.DateTimeEditQuantity),
    )
    proposal_file = Quantity(
        type=str,
        description="""
        The proposal as PDF from GATE ("Preview proposal"), path in the upload.
        """,
        a_tabular=tabular('proposal_file'),
        a_browser=BrowserAnnotation(adaptor=BrowserAdaptors.RawFileAdaptor),
        a_eln=eln(ELNComponentEnum.FileEditQuantity),
    )
    scientific_case_file = Quantity(
        type=str,
        description="""
        GATE, general proposal data: the scientific case and results expected (one
        page PDF), path in the upload.
        """,
        a_tabular=tabular('scientific_case_file'),
        a_browser=BrowserAnnotation(adaptor=BrowserAdaptors.RawFileAdaptor),
        a_eln=eln(ELNComponentEnum.FileEditQuantity),
    )
    experimental_plan_file = Quantity(
        type=str,
        description="""
        GATE, technical requirements: the experimental plan (one page PDF), path in
        the upload.
        """,
        a_tabular=tabular('experimental_plan_file'),
        a_browser=BrowserAnnotation(adaptor=BrowserAdaptors.RawFileAdaptor),
        a_eln=eln(ELNComponentEnum.FileEditQuantity),
    )
    report_file = Quantity(
        type=str,
        description="""
        GATE, after the experiment time: the first result PDF of the experimental
        report, path in the upload.
        """,
        a_tabular=tabular('report_file'),
        a_browser=BrowserAnnotation(adaptor=BrowserAdaptors.RawFileAdaptor),
        a_eln=eln(ELNComponentEnum.FileEditQuantity),
    )
    samples = Quantity(
        type=SolarCellSample,
        shape=['*'],
        description="""
        The sample entries of the project, written from the sheet `samples` on
        every import.
        """,
        a_eln=eln(ELNComponentEnum.ReferenceEditQuantity),
    )

    institutions = Quantity(
        type=str,
        shape=['*'],
        description="""
        Short names of the institutions that the files of this upload come from, one
        per institution folder, and that of the uploader's email domain if files lie
        in no institution's folder. Derived from the files; values entered here are
        replaced.
        """,
    )

    sample_series = SubSection(
        section_def=StabilityFileGroup,
        repeats=True,
        description="""
        One series per sample, with the standards applied to it, ordered by sample
        identifier. The files are derived on every normalization; the applied
        standards are set on import and otherwise kept, also for a sample without
        files.
        """,
    )
    general_groups = SubSection(
        section_def=StabilityFileGroup,
        repeats=True,
        description=f"""
        The files that belong to no sample: one group per general type of files
        (`GENERAL_FILE_TYPES`), such as the setup logs, and `{GENERAL_GROUP}`; last
        `{UNKNOWN_SAMPLE}`, the files whose sample is not known. Derived on every
        normalization. Each file of the upload is in exactly one series or group.
        """,
    )

    def normalize(self, archive: 'EntryArchive', logger: 'BoundLogger') -> None:
        """Reads the spreadsheet if "fill archive from data file" is ticked: the
        first sheet into the quantities here, the sheet `samples` into sample
        entries, and the sheet `files` only to report its errors. Comma separated
        lists are split. On import, the column `standard` of the sheet `samples` gives
        each sample's applied standards. Sample entries are only written during
        NOMAD's processing. Without `data_file`, the upload's `project_data.xlsx` is
        taken and imported.

        Then derives the overview: every registered file of the upload in a series,
        of its sample or of its general kind (`GENERAL_FILE_TYPES`), with a reference
        to the file's entry, `institutions` from the files' institution folders or
        else the uploader's email domain, and the timeline. A file of no general kind
        without sample, or that cannot be read, is in the series `UNKNOWN_SAMPLE`."""
        # Imported here, because the module imports this one.
        from nomad_pv_stability_measurements.parsers.project_data_utils import (
            PROJECT_DATA_FILE,
            file_rows,
            read_sheets,
            sample_standards,
            write_sample_entries,
        )

        context = archive.m_context
        server = isinstance(context, ServerContext)
        if (
            self.data_file is None
            and server
            and context.raw_path_exists(PROJECT_DATA_FILE)
        ):
            self.data_file = PROJECT_DATA_FILE
            self.fill_archive_from_datafile = True
        importing = bool(self.fill_archive_from_datafile and self.data_file)
        if importing:
            # NOMAD's tabular parser fills only empty quantities of the first sheet;
            # an import replaces them all.
            for quantity in self.m_def.all_quantities.values():
                annotation = quantity.m_get_annotations('tabular')
                if annotation is not None and '/' not in annotation.name:
                    self.m_set(quantity, None)
        super().normalize(archive, logger)

        self.co_proposers = split_commas(self.co_proposers)

        standards = None
        if importing and server:
            data = read_sheets(context, self.data_file)
            file_rows(data, logger)
            self.samples = write_sample_entries(context, data, logger)
            standards = sample_standards(data)

        self._derive_overview(archive, logger, standards)

    def _derive_overview(
        self,
        archive: 'EntryArchive',
        logger: 'BoundLogger',
        standards: dict[str, list[str]] | None = None,
    ) -> None:
        """Derives the institutions, the file groups, the link to the app and the
        timeline from the upload's files.

        The samples' applied standards are kept by sample identifier; on import,
        `standards` (the written standards by sample identifier) replaces them,
        keeping an applied standard that is written the same, with its edits.

        Each file's values are found exactly as for its own entry, by
        `file_values`, so the overview does not depend on whether the files'
        entries are processed yet. Problems of single files are reported by their
        entries, not here."""
        # Imported here, because these modules import this one.
        from nomad_pv_stability_measurements.parsers.project_data_utils import (
            load_spreadsheet,
        )
        from nomad_pv_stability_measurements.parsers.stability_file_parser import (
            file_values,
        )
        from nomad_pv_stability_measurements.parsers.utils import (
            institution_of,
            is_registered,
            uploader_email,
        )

        upload_files = getattr(archive.m_context, 'upload_files', None)
        upload_id = archive.metadata.upload_id if archive.metadata else None
        if upload_id is not None:
            self.files_app = files_app_url(upload_id)
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
        spreadsheet = load_spreadsheet(archive.m_context)
        entries = {}
        for path in paths:
            try:
                with upload_files.raw_file(path, 'rb') as file:
                    values = file_values(path, file, QUIET, email, spreadsheet)
                entries[path] = stability_file(values)
            except Exception as error:
                logger.warning('could not read a file', file=path, exc_info=error)
                entries[path] = None

        applied = applied_standards(self.sample_series, standards, logger)
        sample_ids = spreadsheet.sample_ids if spreadsheet else frozenset()
        groups: dict[tuple, StabilityFileGroup] = {
            (0, sample_id): sample_series(sample_id, sample_ids)
            for sample_id in applied
        }
        for path in paths:
            key, name = group_of(entries[path])
            if key not in groups:
                groups[key] = (
                    sample_series(name, sample_ids)
                    if key[0] == 0
                    else StabilityFileGroup(name=name)
                )
            group = groups[key]
            group.files.append(
                StabilityFileReference(file=path, entry=references[path])
            )

        def earliest_first(record):
            entry = entries[record.file]
            start_time = entry.start_time if entry else None
            # Put missing times last and use the file path to break ties.
            return (start_time is None, start_time, record.file)

        for group in groups.values():
            group.files = sorted(group.files, key=earliest_first)
        # The key's first element tells a sample's series (0) from the others.
        self.sample_series = [groups[key] for key in sorted(groups) if key[0] == 0]
        self.general_groups = [groups[key] for key in sorted(groups) if key[0] != 0]
        for series in self.sample_series:
            series.applied_standards = applied.get(series.sample_identity.sample_id, [])
            for standard in series.applied_standards:
                # Added after NOMAD normalized the sub-sections, so normalized here.
                standard.normalize(archive, logger)

        self.figures = file_timeline(
            [*self.sample_series, *self.general_groups], entries
        )


m_package.__init_metainfo__()
