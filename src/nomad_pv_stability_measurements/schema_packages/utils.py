"""Helpers of the schema package: annotations, splitting of lists, a silent logger,
the address of the app "Stability files", the file entries and the groups the project
entry sorts them into, and the standards that a project applies to its samples, as `AppliedStandard`s that
reference a catalogue of standards that every user can see (plugin
`nomad-pv-stability-standards`)."""

import re
from typing import TYPE_CHECKING
from urllib.parse import urlencode

from nomad.config import config
from nomad.datamodel.metainfo.annotations import ELNAnnotation, ELNComponentEnum
from nomad_pv_stability_standards.schema_packages.standard import AppliedStandard

if TYPE_CHECKING:
    from structlog.stdlib import BoundLogger

    from nomad_pv_stability_measurements.schema_packages.schema_package import (
        StabilityActivity,
        StabilityActivityGroup,
    )


#: The group under which the project entry lists the files whose sample is not
#: known: files of a type that is about a sample, which name none.
UNKNOWN_SAMPLE = 'Unknown'

#: The group of the files that belong to no sample and to no other general group:
#: descriptions of the project or of a protocol, and reference data, such as a
#: calibration or a reference spectrum measured elsewhere, that name no sample.
GENERAL_GROUP = 'General'

#: Stability file types that are never about a sample, such as sensor readings of
#: a climate chamber or of an outdoor site's weather station, or a description of
#: the project: the project entry lists them in the group named here, whatever
#: sample they name.
#: Measured and simulated files alike. The groups are ordered as first named here.
GENERAL_FILE_TYPES = {
    'setup_log': 'Setup logs',
    'environment_log': 'Setup logs',
    'weather_information': 'Weather information',
    'metadata': GENERAL_GROUP,
    'measurement_protocol': GENERAL_GROUP,
}


def unique_lab_id(prefix: str, identifier: str) -> str:
    """A lab ID unique in NOMAD: `identifier`, unique within its project, after
    `prefix`, the project's proposal number, or the upload's ID without one. E.g.
    `RPV-261-00001-EF:RPV-S1` for a sample, `RPV-261-00001-EF:UNITOV/run_1/001_JV.txt`
    for a file."""
    return f'{prefix}:{identifier}'


def tabular(column: str) -> dict:
    """The tabular annotation that reads a quantity from the column `column` of the
    first sheet of a spreadsheet."""
    return {'name': column}


def eln(component: ELNComponentEnum) -> ELNAnnotation:
    return ELNAnnotation(component=component)


def split_commas(values) -> list[str] | None:
    """`values` with every value split at commas and stripped; `None` if empty. A
    comma in parentheses does not split, as in `ISOS-L-2 (65 °C, MPP)`."""
    if values is None:
        return None
    items = [
        item.strip()
        for value in values
        for item in re.split(r',(?![^()]*\))', str(value))
    ]
    return [item for item in items if item] or None


class QuietLogger:
    """A logger that drops every message."""

    def __getattr__(self, name):
        return lambda *args, **kwargs: None


QUIET = QuietLogger()


def files_app_url(upload_id: str) -> str:
    """The address of the app "Stability files" in NOMAD's new GUI, filtered to the
    files of the upload `upload_id`."""
    from nomad_pv_stability_measurements.apps.stability_files import (
        stability_files_app,
    )

    query = urlencode({'upload_id': upload_id})
    path = stability_files_app.path
    # The new GUI is served by its own plugin, below the classic GUI's path unless
    # that plugin says otherwise.
    try:
        gui_v2 = config.get_plugin_entry_point('nomad_gui.apis:gui_api')
        base_v2 = config.services.base_url(True) + gui_v2.get_public_base_path()
    except Exception:
        base_v2 = config.gui_url('v2')
    return f'{base_v2}/apps/{path}?{query}'


#: A standard as a project writes it: its name and, in parentheses, the choices made
#: among its options, e.g. `ISOS-L-2 (65 °C, MPP)`.
WRITTEN_STANDARD = re.compile(r'^(?P<name>[^(]+?)\s*(?:\((?P<variant>.*)\))?\s*$')


def split_standard(written: str) -> tuple[str, str | None]:
    """`ISOS-L-2 (65 °C, MPP)` as `('ISOS-L-2', '65 °C, MPP')`; `ISOS-L-2` as
    `('ISOS-L-2', None)`."""
    match = WRITTEN_STANDARD.match(written.strip())
    if match is None:
        return written.strip(), None
    return match.group('name'), (match.group('variant') or '').strip() or None


def find_standard(name: str) -> str | None:
    """A reference to the standard named `name` in a catalogue that every user can
    see: published, or visible to all before it is published. Where several hold it,
    the one published first, so the choice stays the same; unpublished catalogues come
    after all published ones. `None` where no such standard has the name."""
    from nomad.search import MetadataPagination, search

    # `visible` without a user: published without embargo, or visible to all.
    result = search(
        owner='visible',
        query={'entry_type': 'StabilityStandard', 'entry_name': name},
        pagination=MetadataPagination(
            page_size=1, order_by='publish_time', order='asc'
        ),
    )
    if not result.data:
        return None
    hit = result.data[0]
    return f'../uploads/{hit["upload_id"]}/archive/{hit["entry_id"]}#data'


def new_applied_standard(written: str, logger: 'BoundLogger') -> AppliedStandard:
    """The applied standard written `written`, e.g. `ISOS-L-2 (65 °C, MPP)`,
    referencing the standard of its name that every user can see; where none is
    found, it keeps the name alone, with a warning."""
    name, variant = split_standard(written)
    try:
        reference = find_standard(name)
    except Exception as error:
        logger.warning('could not look up the standard', standard=name, exc_info=error)
        reference = None
    else:
        if reference is None:
            logger.warning('no visible standard of this name', standard=name)
    return AppliedStandard(name=name, variant=variant, standard=reference)


def applied_standards(
    series: list, standards: dict[str, list[str]] | None, logger: 'BoundLogger'
) -> dict[str, list[AppliedStandard]]:
    """The applied standards of each sample: those of the current sample `series`,
    or, on import, one per written standard in
    `standards`, in its order, keeping a current one that is written the same so
    that its edits stay."""
    # Moved, not copied: a copy would lose the archive its reference points into.
    current = {}
    for each in series:
        if each.applied_standards:
            current[each.sample_identity.sample_id] = list(each.applied_standards)
            each.applied_standards = []
    if standards is None:
        return current
    applied = {}
    for sample_id, written_standards in standards.items():
        kept = current.get(sample_id, [])
        applied[sample_id] = []
        for written in written_standards:
            same = [
                each
                for each in kept
                if (each.name, each.variant) == split_standard(written)
            ]
            if same:
                kept.remove(same[0])
                applied[sample_id].append(same[0])
            else:
                applied[sample_id].append(new_applied_standard(written, logger))
    return applied


# The file entries and their groups.


def stability_activity(values: dict, data: dict | None = None) -> 'StabilityActivity':
    """The entry of a file with `values` as the file parser finds them: the
    quantities of the activity; `file` and `file_format`, which make its `file`; and
    `sample_id`, `sample` (the reference to the sample entry) and `sample_reference`,
    which make its `sample_identity`.

    `data` is what the institution's `match_<kind>` function read from the file
    beyond these values. It is not stored yet; it is passed here so that the entry
    can become a section of its own kind that holds it, chosen here alone, without
    changes to the parser or to the institutions' reading code."""
    from nomad_pv_stability_measurements.schema_packages.schema_package import (
        SampleIdentity,
        StabilityActivity,
        StabilityFile,
    )

    values = dict(values)
    path = values.pop('file', None)
    if path is not None:
        values['file'] = StabilityFile(
            path=path, file_format=values.pop('file_format', 'unknown')
        )
    identity = {
        'sample_id': values.pop('sample_id', None),
        'entry': values.pop('sample', None),
        'external_reference': values.pop('sample_reference', None),
    }
    identity = {key: value for key, value in identity.items() if value is not None}
    if identity:
        values['sample_identity'] = SampleIdentity(**identity)
    return StabilityActivity(**values)


def sample_series(sample_id: str, sample_ids: frozenset) -> 'StabilityActivityGroup':
    """The series of the sample `sample_id`, referencing its sample entry if the
    sheet `samples` (`sample_ids`) has it."""
    from nomad_pv_stability_measurements.parsers.project_data_utils import (
        sample_entry_reference,
    )
    from nomad_pv_stability_measurements.schema_packages.schema_package import (
        SampleIdentity,
        StabilityActivityGroup,
    )

    identity = SampleIdentity(sample_id=sample_id)
    if sample_id in sample_ids:
        identity.entry = sample_entry_reference(sample_id)
    return StabilityActivityGroup(name=sample_id, sample_identity=identity)


def group_of(entry: 'StabilityActivity | None') -> tuple[tuple, str]:
    """The group of a file's entry, as a key that orders the groups (samples, then
    the general groups, then the unknown sample) and the group's name."""
    general = list(dict.fromkeys(GENERAL_FILE_TYPES.values()))
    file_type = entry.stability_file_type if entry else None
    if file_type in GENERAL_FILE_TYPES:
        name = GENERAL_FILE_TYPES[file_type]
        return (1, general.index(name)), name
    identity = entry.sample_identity if entry else None
    sample_id = identity.sample_id if identity else None
    if sample_id and sample_id != UNKNOWN_SAMPLE:
        return (0, sample_id), sample_id
    if entry is not None and entry.provenance == 'reference':
        return (1, general.index(GENERAL_GROUP)), GENERAL_GROUP
    return (2, UNKNOWN_SAMPLE), UNKNOWN_SAMPLE
