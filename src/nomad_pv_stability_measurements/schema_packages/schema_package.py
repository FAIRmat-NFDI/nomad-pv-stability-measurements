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
from nomad.metainfo import Datetime, MEnum, Quantity, SchemaPackage, SubSection
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

    sample_id = Quantity(
        type=str,
        description='The identifier of the sample as the institution writes it.',
    )

    sample_reference = Quantity(
        type=str,
        description="""
        A URI identifying the sample: a NOMAD entry, an external database, or any
        other resolvable identifier.
        """,
    )


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

    def normalize(self, archive: 'EntryArchive', logger: 'BoundLogger') -> None:
        """Lists every registered file of the upload with a reference to its entry,
        and derives `institutions` from the files' institution folders.

        Only the upload's file paths are used, not the files' entries, so the result
        does not depend on which entries are processed already."""
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
        self.files = [
            StabilityFileReference(
                file=path,
                entry=f'../uploads/{upload_id}/archive/'
                f'{generate_entry_id(upload_id, path)}#data',
            )
            for path in paths
        ]
        institutions = {institution_of(path) for path in paths}
        self.institutions = sorted(
            institution.INSTITUTION for institution in institutions if institution
        )


m_package.__init_metainfo__()
