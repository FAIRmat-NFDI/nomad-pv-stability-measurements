"""Helpers of the parser that do not depend on what a file holds: which files of an
upload are registered, reading the beginning and end of a file, and finding the
institution and the uploader of a file."""

import os
from pathlib import PurePosixPath
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
    from typing import BinaryIO

    from nomad.datamodel.datamodel import EntryArchive
    from structlog.stdlib import BoundLogger

#: How many bytes of the beginning of a file the `match_<kind>` functions see, for
#: an institution whose module sets no `HEAD_SIZE` of its own.
HEAD_SIZE = 4096

#: How many bytes of the end of a file the `match_<kind>` functions see, for an
#: institution whose module sets no `TAIL_SIZE` of its own.
TAIL_SIZE = 4096

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


def read_head(file: 'BinaryIO', size: int = HEAD_SIZE) -> str:
    """The first `size` bytes of `file`, opened in binary mode, as text.

    Decoded as UTF-8: before parsing, NOMAD rewrites text files that it recognizes as
    Latin-1 in UTF-8. Bytes that are not UTF-8, as in binary files, become `�`
    instead of an error, so such a file gives text that no `match_<kind>` function
    recognizes."""
    return file.read(size).decode('utf-8', errors='replace')


def read_tail(file: 'BinaryIO', size: int = TAIL_SIZE) -> str:
    """The last `size` bytes of `file`, opened in binary mode, as text, decoded like
    `read_head`; empty for `size` 0. If head and tail together are longer than the
    file, they overlap; for a file shorter than `size`, the tail is the whole file.
    The tail may begin within a line."""
    if size == 0:
        return ''
    file.seek(0, os.SEEK_END)
    file.seek(max(0, file.tell() - size))
    return file.read().decode('utf-8', errors='replace')


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
