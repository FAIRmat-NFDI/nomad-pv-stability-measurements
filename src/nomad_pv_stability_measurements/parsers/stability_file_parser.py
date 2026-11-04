"""Registering every file of a stability upload as a `StabilityFileEntry`."""

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

from nomad.parsing.parser import MatchingParser

from nomad_pv_stability_measurements.file_reading import INSTITUTIONS
from nomad_pv_stability_measurements.file_reading.file_reading_utils import (
    file_format_from_path,
    is_in_institution_folder,
)
from nomad_pv_stability_measurements.schema_packages.schema_package import (
    MEASUREMENT_KINDS,
    StabilityFileEntry,
)

#: How many characters of a file the `match_<kind>` functions see. Enough for the
#: headers of all known formats; UNITOV's `Algorithm` line lies up to 556 characters
#: in.
HEAD_SIZE = 4096


def read_head(file_path: str) -> str:
    """The first `HEAD_SIZE` characters of the file at `file_path` as text.

    Decoded as UTF-8: before parsing, NOMAD rewrites text files that it recognizes as
    Latin-1 in UTF-8. Bytes that are not UTF-8, as in binary files, become `�`
    instead of an error, so such a file gives text that no `match_<kind>` function
    recognizes."""
    with open(file_path, encoding='utf-8', errors='replace') as file:
        return file.read(HEAD_SIZE)


def register_file(
    path: str, content: str, logger: 'BoundLogger'
) -> tuple[dict, str | None, dict]:
    """What is known about the file at `path`, a path within the upload, whose
    beginning is `content`.

    Returns three values:

    - the values of the `StabilityFile` quantities, without those nobody knows;
    - the `INSTITUTION` whose folder the file is in, or `None`;
    - the `data` dict that the institution's `match_<kind>` function returned.

    The institution's `match_<kind>` functions are asked in the order of
    `MEASUREMENT_KINDS`, and the first that recognizes the file, by not returning
    `False`, decides. A function that fails is logged as a warning and treated as not
    recognizing the file.

    A file that is in no institution's folder is of kind `unknown` and logged as an
    error, because no institution's code can read it. A file of an institution that
    no function recognizes is of kind `unknown` and logged as a warning.
    """
    values = {'file': path, 'file_format': file_format_from_path(path)}

    institution = next(
        (
            module
            for module in INSTITUTIONS
            if is_in_institution_folder(path, module.INSTITUTION)
        ),
        None,
    )
    if institution is None:
        logger.error(
            'file is in no institution folder',
            file=path,
            institutions=[module.INSTITUTION for module in INSTITUTIONS],
        )
        return values, None, {}

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
        found = {
            'time_stamp': time_stamp,
            'sample_id': sample_id,
            'sample_reference': sample_reference,
        }
        values.update(
            {name: value for name, value in found.items() if value is not None}
        )
        return values, institution.INSTITUTION, data

    logger.warning(
        'file kind not recognized',
        file=path,
        institution=institution.INSTITUTION,
    )
    return values, institution.INSTITUTION, {}


class StabilityFileParser(MatchingParser):
    """Makes one `StabilityFileEntry` per file, filled by `register_file`."""

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

        # The institution and the institution-specific `data` are not stored in
        # the file's entry.
        values, _institution, _data = register_file(path, read_head(mainfile), logger)
        archive.data = StabilityFileEntry(**values)
