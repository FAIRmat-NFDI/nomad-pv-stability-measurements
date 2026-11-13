"""Registering every file of a stability upload as a `StabilityFile`."""

import json
from typing import TYPE_CHECKING

from nomad.datamodel.context import ServerContext
from nomad.parsing.parser import MatchingParser

from nomad_pv_stability_measurements.file_reading import INSTITUTIONS
from nomad_pv_stability_measurements.file_reading.file_reading_utils import (
    file_format_from_path,
)
from nomad_pv_stability_measurements.parsers.project_data_utils import (
    PROJECT_DATA_ARCHIVE,
    Spreadsheet,
    clean_sample_id,
    described_values,
    load_spreadsheet,
    sample_entry_reference,
)
from nomad_pv_stability_measurements.parsers.utils import (
    HEAD_SIZE,
    TAIL_SIZE,
    DescribedFileLogger,
    institution_of,
    read_head,
    read_tail,
    uploader_email,
)
from nomad_pv_stability_measurements.schema_packages.schema_package import (
    STABILITY_FILE_TYPES,
    ProjectData,
)
from nomad_pv_stability_measurements.schema_packages.utils import stability_file

if TYPE_CHECKING:
    from typing import BinaryIO

    from nomad.datamodel.datamodel import EntryArchive
    from structlog.stdlib import BoundLogger


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
    `STABILITY_FILE_TYPES`, and the first that recognizes the file, by not returning
    `False`, decides. A function that fails is logged as a warning and treated as not
    recognizing the file. A file whose function gives no end time ends when it
    starts.

    A file that belongs to no institution, by folder or email, is of kind `unknown`
    and logged as an error, because no institution's code can read it. A file of an
    institution that no function recognizes is of kind `unknown` and logged as a
    warning.
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
    for kind in STABILITY_FILE_TYPES:
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

        start_time, end_time, provenance, sample_id, sample_reference, data = result
        found = {
            'stability_file_type': kind,
            'start_time': start_time,
            'end_time': start_time if end_time is None else end_time,
            'provenance': provenance,
            'sample_id': clean_sample_id(sample_id),
            'sample_reference': sample_reference,
        }
        values.update({key: value for key, value in found.items() if value is not None})
        return values, data

    logger.warning(
        'file kind not recognized',
        file=path,
        institution=institution.INSTITUTION,
    )
    return values, {}


def with_project_data(values: dict, described: dict, sample_ids: frozenset) -> dict:
    """`values`, the values of a file found by matching, with `described`, those that
    the rows of the sheet `files` give for it, which win field by field, and with a
    reference to the sample entry of the file's `sample_id` if the sheet `samples`
    (`sample_ids`) has it.

    If the descriptions give a start but no end, and matching gave no end of its
    own, the file's data end when they start, as for matching."""
    end_was_start = values.get('end_time') == values.get('start_time')
    values = {**values, **described}
    if 'end_time' not in described and end_was_start:
        values.pop('end_time', None)
        if values.get('start_time') is not None:
            values['end_time'] = values['start_time']
    if values.get('sample_id') is None:
        values.pop('sample_id', None)
    elif values['sample_id'] in sample_ids:
        values['sample'] = sample_entry_reference(values['sample_id'])
    return values


def file_values(
    path: str,
    file: 'BinaryIO',
    logger: 'BoundLogger',
    email: str | None = None,
    spreadsheet: 'Spreadsheet | None' = None,
) -> dict:
    """The values of the `StabilityFile` of the file at `path`, a path within the
    upload, whose content `file` gives, uploaded by the user with the address
    `email`: found by `register_file` and completed by the project data
    `spreadsheet` with `with_project_data`.

    The institution's module sets how much of the beginning and end of the file its
    functions see. Problems of a file that the spreadsheet describes are logged as
    information, because the spreadsheet gives its values."""
    institution = institution_of(path, email)
    content = read_head(file, getattr(institution, 'HEAD_SIZE', HEAD_SIZE))
    tail = read_tail(file, getattr(institution, 'TAIL_SIZE', TAIL_SIZE))
    described = {}
    if spreadsheet is not None:
        described = described_values(path, spreadsheet.file_rows)
    if described:
        logger = DescribedFileLogger(logger)
    # The institution-specific `data` is not stored.
    values, _data = register_file(path, content, tail, logger, email)
    if spreadsheet is None:
        return values
    return with_project_data(values, described, spreadsheet.sample_ids)


def ensure_project_data(archive: 'EntryArchive', logger: 'BoundLogger') -> None:
    """Creates the upload's project entry `ProjectData`, unless the upload has one,
    and has NOMAD process it.

    Only during NOMAD's processing of an upload, with a `ServerContext`. The files of
    an upload are processed in parallel, so several may create it at once; they
    write the same content, and NOMAD processes it again instead of failing. An
    existing entry, which may hold edits, is never overwritten. A failure is logged
    as a warning and does not fail the file's entry."""
    context = archive.m_context
    if not isinstance(context, ServerContext):
        return
    path = PROJECT_DATA_ARCHIVE
    if context.raw_path_exists(path):
        return

    try:
        with context.raw_file(path, 'w') as file:
            json.dump({'data': ProjectData().m_to_dict(with_root_def=True)}, file)
        context.process_updated_raw_file(path, allow_modify=True)
    except Exception as error:
        logger.warning('could not create the project data', file=path, exc_info=error)


class StabilityFileParser(MatchingParser):
    """Makes one `StabilityFile` per file, filled by `register_file`, and
    makes sure that the upload has a project entry."""

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

        email = uploader_email(archive)
        spreadsheet = load_spreadsheet(archive.m_context)
        with open(mainfile, 'rb') as file:
            values = file_values(path, file, logger, email, spreadsheet)
        archive.data = stability_file(values)

        ensure_project_data(archive, logger)
