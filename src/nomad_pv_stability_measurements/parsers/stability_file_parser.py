"""Registering every file of a stability upload as a `StabilityFile`."""

from typing import (
    TYPE_CHECKING,
)

if TYPE_CHECKING:
    from types import ModuleType
    from typing import BinaryIO

    from nomad.datamodel.datamodel import (
        EntryArchive,
    )
    from structlog.stdlib import (
        BoundLogger,
    )

import json
import os
from pathlib import PurePosixPath

from nomad.datamodel.context import ServerContext
from nomad.parsing.parser import MatchingParser

from nomad_pv_stability_measurements.file_reading import INSTITUTIONS
from nomad_pv_stability_measurements.file_reading.file_reading_utils import (
    file_format_from_path,
    is_in_institution_folder,
)
from nomad_pv_stability_measurements.schema_packages.schema_package import (
    MEASUREMENT_KINDS,
    StabilityFile,
    StabilityUploadSummary,
)

#: How many bytes of the beginning of a file the `match_<kind>` functions see, for
#: an institution whose module sets no `HEAD_SIZE` of its own.
HEAD_SIZE = 4096

#: How many bytes of the end of a file the `match_<kind>` functions see, for an
#: institution whose module sets no `TAIL_SIZE` of its own.
TAIL_SIZE = 4096

#: The endings of NOMAD archive files, such as ELN entries and the upload summary.
#: These are processed by NOMAD itself and not registered.
ARCHIVE_FILE_ENDINGS = ('.archive.json', '.archive.yaml', '.archive.yml')

#: The names of an upload's summary file, at the upload's root. A user may supply
#: any of them; a summary created automatically gets the first.
SUMMARY_FILE_NAMES = (
    'stability_upload.archive.json',
    'stability_upload.archive.yaml',
    'stability_upload.archive.yml',
)


def is_registered(path: str) -> bool:
    """`True` if the file at `path`, a path within the upload, is registered: all
    files except NOMAD archive files, hidden files, files in hidden folders, and
    files whose name starts with `~`, which NOMAD never processes."""
    names = PurePosixPath(path).parts
    if any(name.startswith('.') for name in names) or names[-1].startswith('~'):
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
    folder_institution = next(
        (
            module
            for module in INSTITUTIONS
            if is_in_institution_folder(path, module.INSTITUTION)
        ),
        None,
    )
    if folder_institution is not None or not email or '@' not in email:
        return folder_institution

    domain = email.rsplit('@', 1)[1].lower()
    return next(
        (
            module
            for module in INSTITUTIONS
            for institution_domain in getattr(module, 'EMAIL_DOMAINS', ())
            if domain == institution_domain.lower()
            or domain.endswith('.' + institution_domain.lower())
        ),
        None,
    )


def uploader_email(archive: 'EntryArchive') -> str | None:
    """The email address of the upload's main author, as NOMAD's user management
    knows it, or `None`, as when parsing outside of NOMAD's processing."""
    try:
        return archive.metadata.main_author.email
    except Exception:
        return None


def register_file(
    path: str,
    content: str,
    tail: str,
    logger: 'BoundLogger',
    email: str | None = None,
) -> tuple[dict, dict]:
    """What is known about the file at `path`, a path within the upload, whose
    beginning is `content` and whose end is `tail`, uploaded by the user with the
    address `email`.

    Returns two values:

    - the values of the `StabilityFile` quantities, without those nobody knows;
    - the `data` dict that the institution's `match_<kind>` function returned.

    The institution is given by `institution_of`: by the file's folder, or else by
    the domain of `email`, which is logged.

    The institution's `match_<kind>` functions are asked in the order of
    `MEASUREMENT_KINDS`, and the first that recognizes the file, by not returning
    `False`, decides. A function that fails is logged as a warning and treated as not
    recognizing the file. A measurement whose function gives no end time ends when it
    starts.

    A file that belongs to no institution, by folder or email, is of kind `unknown`
    and logged as an error, because no institution's code can read it. A file of an institution that
    no function recognizes is of kind `unknown` and logged as a warning.
    """
    values = {'file': path, 'file_format': file_format_from_path(path)}

    institution = institution_of(path, email)
    if institution is None:
        logger.error(
            "file is in no institution folder, and the uploader's email domain "
            'belongs to no institution',
            file=path,
            institutions=[module.INSTITUTION for module in INSTITUTIONS],
        )
        return values, {}
    if institution is not institution_of(path):
        logger.info(
            "file is in no institution folder; institution taken from the uploader's "
            'email domain',
            file=path,
            institution=institution.INSTITUTION,
        )

    values['institution'] = institution.INSTITUTION
    for kind in MEASUREMENT_KINDS:
        match = getattr(institution, f'match_{kind}', None)
        if match is None:
            continue
        try:
            result = match(path, content, tail)
        except Exception as error:
            logger.warning(
                'match function failed',
                institution=institution.INSTITUTION,
                function=match.__name__,
                exc_info=error,
            )
            continue
        if result is False:
            continue

        start_time, end_time, sample_id, sample_reference, data = result
        values['measurement_kind'] = kind
        if start_time is not None:
            values['start_time'] = start_time
        if end_time is None:
            end_time = start_time
        if end_time is not None:
            values['end_time'] = end_time
        if sample_id is not None:
            values['sample_id'] = sample_id
        if sample_reference is not None:
            values['sample_reference'] = sample_reference
        return values, data

    logger.warning(
        'file kind not recognized',
        file=path,
        institution=institution.INSTITUTION,
    )
    return values, {}


def ensure_summary(archive: 'EntryArchive', logger: 'BoundLogger') -> None:
    """Creates the upload's summary file, unless the upload has one, and has NOMAD
    process it.

    Only during NOMAD's processing of an upload, with a `ServerContext`. The files of
    an upload are processed in parallel, so several may create the summary at once;
    they write the same content, and NOMAD processes the summary again instead of
    failing. A failure is logged as a warning and does not fail the file's entry."""
    context = archive.m_context
    if not isinstance(context, ServerContext):
        return
    if any(context.raw_path_exists(name) for name in SUMMARY_FILE_NAMES):
        return

    path = SUMMARY_FILE_NAMES[0]
    try:
        with context.raw_file(path, 'w') as file:
            json.dump(
                {'data': StabilityUploadSummary().m_to_dict(with_root_def=True)}, file
            )
        context.process_updated_raw_file(path, allow_modify=True)
    except Exception as error:
        logger.warning('could not create the upload summary', file=path, exc_info=error)


class StabilityFileParser(MatchingParser):
    """Makes one `StabilityFile` per file, filled by `register_file`, and
    makes sure that the upload has a summary."""

    def parse(
        self,
        mainfile: str,
        archive: 'EntryArchive',
        logger: 'BoundLogger',
        child_archives: dict[str, 'EntryArchive'] = None,
    ) -> None:
        # `mainfile` is where the file lies on disk; the institution folder is
        # looked for in its path within the upload.
        path = mainfile
        if archive.metadata is not None and archive.metadata.mainfile:
            path = archive.metadata.mainfile

        # How much of the file the institution's functions see, as its module sets.
        email = uploader_email(archive)
        institution = institution_of(path, email)
        head_size = getattr(institution, 'HEAD_SIZE', HEAD_SIZE)
        tail_size = getattr(institution, 'TAIL_SIZE', TAIL_SIZE)
        with open(mainfile, 'rb') as file:
            content = read_head(file, head_size)
            tail = read_tail(file, tail_size)
        # The institution-specific `data` is not stored in the file's entry.
        values, _data = register_file(path, content, tail, logger, email)
        archive.data = StabilityFile(**values)

        ensure_summary(archive, logger)
