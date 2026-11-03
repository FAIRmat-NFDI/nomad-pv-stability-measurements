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


class StabilityUploadSummary(BaseSection, EntryData):
    """
    All files of one stability upload, with the institution that measured them and
    the proposal under which they were measured.
    """

    institution = Quantity(
        type=str,
        description="""
        Short name of the institution that measured the files of this upload. Derived
        from the files; a value entered here is replaced.
        """,
    )
    proposal = Quantity(
        type=str,
        description='A URI of the proposal under which these measurements were made.',
        a_eln=ELNAnnotation(component=ELNComponentEnum.URLEditQuantity),
    )

    files = SubSection(
        section_def=StabilityFile,
        repeats=True,
        description="""
        One record per file of the upload. Derived from the files; records entered
        here are replaced.
        """,
    )


m_package.__init_metainfo__()
