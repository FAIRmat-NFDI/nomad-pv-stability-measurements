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

from nomad.config import config
from nomad.datamodel.data import ArchiveSection, EntryData, Schema
from nomad.datamodel.metainfo.annotations import (
    BrowserAdaptors,
    BrowserAnnotation,
    ELNAnnotation,
    ELNComponentEnum,
)
from nomad.datamodel.metainfo.basesections import BaseSection
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
        Short name of the institution whose folder of the upload the file is in. Its
        reading code determines the other values. Empty if the file is in no
        institution's folder.
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


class StabilityUploadSummary(BaseSection, EntryData):
    """
    All files of one stability upload, with the institutions that measured them and
    the proposal under which they were measured.
    """

    institutions = Quantity(
        type=str,
        shape=['*'],
        description="""
        Short names of the institutions that measured the files of this upload, one
        per institution folder. Derived from the files; values entered here are
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
        derives `institutions` from the files' institution folders, and groups the
        files by the sample their entries name.

        `files` and `institutions` follow from the upload's file paths alone. The
        groups read the files' entries, which NOMAD processes before the summary; a
        file whose entry cannot be read is in the group without sample."""
        super().normalize(archive, logger)

        # Imported here, because the parser module imports this module.
        from nomad_pv_stability_measurements.parsers.stability_file_parser import (
            institution_of,
            is_registered,
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
        institutions = {institution_of(path) for path in paths}
        self.institutions = sorted(
            institution.INSTITUTION for institution in institutions if institution
        )

        # Build each sample group while reading its files' entries.
        by_sample: dict[str | None, StabilitySample] = {}
        measurement_times = {}
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


m_package.__init_metainfo__()
