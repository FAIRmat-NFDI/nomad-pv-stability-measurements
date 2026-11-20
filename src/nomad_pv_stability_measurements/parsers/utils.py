"""Helpers of the parser that do not depend on what a file holds: which files of an
upload are registered, where a file lies on disk, and finding the institution and the uploader of a file."""

import shutil
import tempfile
from collections.abc import Iterator
from contextlib import contextmanager
from pathlib import Path, PurePosixPath
from typing import TYPE_CHECKING

from nomad_pv_stability_measurements.file_reading import INSTITUTIONS
from nomad_pv_stability_measurements.file_reading.file_reading_utils import (
    is_in_institution_folder,
)
from nomad_pv_stability_measurements.parsers.project_data_utils import (
    PROJECT_DATA_FILE,
    TEMPLATE_FILE,
)

if TYPE_CHECKING:
    from types import ModuleType

    from nomad.datamodel.datamodel import EntryArchive
    from structlog.stdlib import BoundLogger

#: The endings of NOMAD archive files, such as ELN entries and the project entry.
#: These are processed by NOMAD itself and not registered.
ARCHIVE_FILE_ENDINGS = ('.archive.json', '.archive.yaml', '.archive.yml')


def is_registered(path: str) -> bool:
    """`True` if the file at `path`, a path within the upload, is registered: all
    files except NOMAD archive files, hidden files, files in hidden folders, files
    whose name starts with `~`, which NOMAD never processes, and the project data
    spreadsheet and its template, which the project entry reads."""
    names = PurePosixPath(path).parts
    if any(name.startswith('.') for name in names) or names[-1].startswith('~'):
        return False
    if names[-1] in (PROJECT_DATA_FILE, TEMPLATE_FILE):
        return False
    return not path.endswith(ARCHIVE_FILE_ENDINGS)


@contextmanager
def raw_file_on_disk(upload_files, path: str) -> Iterator[str]:
    """Where the file at `path`, a path within the upload, lies on disk, for the
    `match_<kind>` functions, which read files by their path.

    A staging upload keeps its files on disk. A published upload keeps them in a zip
    file, so the file is copied to a temporary file, which is removed afterwards and
    whose name ends with the file's path within the upload."""
    raw_file_object = getattr(upload_files, 'raw_file_object', None)
    if raw_file_object is not None:
        yield raw_file_object(path).os_path
        return
    with tempfile.TemporaryDirectory() as folder:
        os_path = Path(folder, path)
        os_path.parent.mkdir(parents=True, exist_ok=True)
        with upload_files.raw_file(path, 'rb') as source, open(os_path, 'wb') as copy:
            shutil.copyfileobj(source, copy)
        yield str(os_path)


def institution_of(path: str, email: str | None = None) -> 'ModuleType | None':
    """The institution of the file at `path`, a path within the upload: the first
    module in `INSTITUTIONS` whose institution folder the file is in.

    For a file in no institution's folder, the first module whose `EMAIL_DOMAINS`
    hold the domain of `email`, the uploader's email address; a subdomain counts, so
    `chem.uni.edu` belongs to `uni.edu`. `None` if neither decides."""
    for module in INSTITUTIONS:
        if is_in_institution_folder(path, module.INSTITUTION):
            return module
    if not email or '@' not in email:
        return None
    domain = email.rsplit('@', 1)[1].lower()
    for module in INSTITUTIONS:
        domains = [each.lower() for each in getattr(module, 'EMAIL_DOMAINS', ())]
        if any(domain == each or domain.endswith('.' + each) for each in domains):
            return module
    return None


def uploader_email(archive: 'EntryArchive') -> str | None:
    """The email address of the upload's main author, as NOMAD's user management
    knows it, or `None`, as when parsing outside of NOMAD's processing."""
    try:
        return archive.metadata.main_author.email
    except Exception:
        return None


class DescribedFileLogger:
    """The logger for reading a file that the upload's project data describes:
    warnings and errors become information, because the project data gives the
    file's values."""

    def __init__(self, logger: 'BoundLogger'):
        self._logger = logger

    def warning(self, *args, **kwargs):
        self._logger.info(*args, **kwargs)

    error = warning

    def __getattr__(self, name):
        return getattr(self._logger, name)
