"""Registering every file of a stability upload as a `StabilityFileEntry`."""

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
    StabilityFileEntry,
    StabilitySampleIdentity,
    StabilityUploadSummary,
)

#: How many bytes of a file the `match_<kind>` functions see. Enough for the headers
#: of all known formats; UNITOV's `Algorithm` line lies up to 556 bytes in.
HEAD_SIZE = 4096

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


def read_head(file: 'BinaryIO') -> str:
    """The first `HEAD_SIZE` bytes of `file`, opened in binary mode, as text.

    Decoded as UTF-8: before parsing, NOMAD rewrites text files that it recognizes as
    Latin-1 in UTF-8. Bytes that are not UTF-8, as in binary files, become `�`
    instead of an error, so such a file gives text that no `match_<kind>` function
    recognizes."""
    return file.read(HEAD_SIZE).decode('utf-8', errors='replace')


def institution_of(path: str) -> 'ModuleType | None':
    """The first module in `INSTITUTIONS` whose institution folder the file at
    `path`, a path within the upload, is in, or `None`."""
    return next(
        (
            module
            for module in INSTITUTIONS
            if is_in_institution_folder(path, module.INSTITUTION)
        ),
        None,
    )


def register_file(path: str, content: str, logger: 'BoundLogger') -> tuple[dict, dict]:
    """What is known about the file at `path`, a path within the upload, whose
    beginning is `content`.

    Returns two values:

    - the values of the `StabilityFile` quantities, without those nobody knows;
    - the `data` dict that the institution's `match_<kind>` function returned.

    The institution is given by `institution_of`.

    The institution's `match_<kind>` functions are asked in the order of
    `MEASUREMENT_KINDS`, and the first that recognizes the file, by not returning
    `False`, decides. A function that fails is logged as a warning and treated as not
    recognizing the file.

    A file that is in no institution's folder is of kind `unknown` and logged as an
    error, because no institution's code can read it. A file of an institution that
    no function recognizes is of kind `unknown` and logged as a warning.
    """
    values = {'file': path, 'file_format': file_format_from_path(path)}

    institution = institution_of(path)
    if institution is None:
        logger.error(
            'file is in no institution folder',
            file=path,
            institutions=[module.INSTITUTION for module in INSTITUTIONS],
        )
        return values, {}

    values['institution'] = institution.INSTITUTION
    for kind in MEASUREMENT_KINDS:
        match = getattr(institution, f'match_{kind}', None)
        if match is None:
            continue
        try:
            result = match(path, content)
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

        time_stamp, sample_id, sample_reference, data = result
        values['measurement_kind'] = kind
        if time_stamp is not None:
            values['time_stamp'] = time_stamp
        if sample_id is not None or sample_reference is not None:
            values['sample'] = StabilitySampleIdentity(
                id=sample_id, reference=sample_reference
            )
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
    """Makes one `StabilityFileEntry` per file, filled by `register_file`, and
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

        with open(mainfile, 'rb') as file:
            content = read_head(file)
        # The institution-specific `data` is not stored in the file's entry.
        values, _data = register_file(path, content, logger)
        archive.data = StabilityFileEntry(**values)

        ensure_summary(archive, logger)
