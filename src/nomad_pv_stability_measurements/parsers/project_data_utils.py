"""The project data spreadsheet `project_data.xlsx` of a stability upload, with the
proposal, the samples and values for the files.

The spreadsheet has four sheets:

- `project` (the first sheet): one row with the proposal as submitted in GATE
  (READY-PV);
- `files`: one row per path pattern with values for the files it matches;
- `references`: one URL per row, of a database or repository linked to the
  project;
- `samples`: one row per sample with the standards applied to it, and its layer
  stack at the end in blocks of three columns `LayerN: layer_type`,
  `LayerN: layer_material_name` and `LayerN: layer_thickness [nm]`.

NOMAD's tabular parser fills `ProjectData` from the sheet `project`. The sheet
`samples` is read here when `ProjectData` imports the spreadsheet, and each row
becomes sample entries of the upload; so is the sheet `references`, into
`ProjectData.external_references`. The sheet `files` is read here by every file
entry when it is parsed.
"""

import json
import math
import os
import re
from datetime import datetime
from fnmatch import fnmatchcase
from functools import lru_cache
from pathlib import PurePosixPath
from typing import TYPE_CHECKING, NamedTuple
from urllib.parse import urlsplit

from nomad.datamodel.metainfo.basesections import CompositeSystemReference
from nomad.parsing.tabular import read_table_data
from nomad.units import ureg
from openpyxl import Workbook
from openpyxl.comments import Comment
from openpyxl.styles import Alignment, Border, Font, PatternFill, Protection, Side
from openpyxl.utils import get_column_letter, quote_sheetname
from openpyxl.worksheet.datavalidation import DataValidation
from openpyxl.worksheet.protection import SheetProtection

from nomad_pv_stability_measurements.schema_packages.sample_schema import (
    Encapsulation,
    LayerProperties,
    ModuleConfiguration,
    SolarCellSample,
    Substrate,
)
from nomad_pv_stability_measurements.schema_packages.schema_package import (
    ProjectData,
    SampleIdentity,
    StabilityActivity,
)
from nomad_pv_stability_measurements.schema_packages.utils import (
    split_commas,
    unique_lab_id,
)

if TYPE_CHECKING:
    from structlog.stdlib import BoundLogger

#: The spreadsheet, at the upload root.
PROJECT_DATA_FILE = 'project_data.xlsx'

#: The ELN entry made from the spreadsheet, at the upload root.
PROJECT_DATA_ARCHIVE = 'project_data.archive.json'

#: The empty spreadsheet that the plugin ships; never read as project data.
TEMPLATE_FILE = 'project_data_template.xlsx'

#: The folder of the upload in which the sample entries are written.
SAMPLES_FOLDER = 'samples'

#: The longest path pattern accepted, in characters.
MAX_PATTERN_LENGTH = 500

#: How many layer blocks the template has; more can be pasted.
TEMPLATE_LAYER_BLOCKS = 8

#: The sections that the sheet `samples` fills, by the names used in
#: `SAMPLE_COLUMNS`.
SAMPLE_SECTIONS = {
    'sample': SolarCellSample,
    'substrate': Substrate,
    'module': ModuleConfiguration,
    'encapsulation': Encapsulation,
}

#: The columns of the sheet `samples` before the layer blocks: the section they
#: fill (a key of `SAMPLE_SECTIONS`) and its quantity.
SAMPLE_COLUMNS = {
    'sample_id': ('sample', 'sample_id'),
    'name': ('sample', 'name'),
    'architecture': ('sample', 'architecture'),
    'number_of_junctions': ('sample', 'number_of_junctions'),
    'is_module': ('module', 'is_module'),
    'pixel_connection': ('module', 'pixel_connection'),
    'module_active_area': ('module', 'module_active_area'),
    'substrate': ('substrate', 'substrate'),
    'active_area': ('substrate', 'active_area'),
    'dead_area': ('substrate', 'dead_area'),
    'aperture_area': ('substrate', 'aperture_area'),
    'number_of_pixels': ('substrate', 'number_of_pixels'),
    'encapsulation_method': ('encapsulation', 'encapsulation_method'),
    'sides_encapsulated': ('encapsulation', 'sides_encapsulated'),
}

#: The column of the sheet `samples` with the standards applied to the sample,
#: separated by commas, e.g. `ISOS-L-2 (65 °C, MPP), ISOS-D-1`. It gives the
#: sample's file series in `ProjectData` its applied standards, not the sample entry.
STANDARD_COLUMN = 'standard'

#: What the column `standard` holds, for the template.
STANDARD_COLUMN_DESCRIPTION = """
The stability standards applied to the sample, separated by commas, e.g. ISOS-L-2,
or with the choices made among its options in parentheses, e.g. ISOS-L-2 (65 °C,
MPP), ISOS-D-1. Each references the standard of its name in the catalogue of
standards.
"""

#: The columns of the sheet `files`: the path pattern, then quantities of
#: `StabilityActivity` that a row can give for the files it matches.
FILE_COLUMNS = (
    'files',
    'stability_file_type',
    'datetime',
    'datetime_end',
    'duration',
    'provenance',
    'sample_id',
    'sample_reference',
    'description',
)

#: Earlier headers of columns of the sheet `files`, read under their current name.
FILE_COLUMN_ALIASES = {'measurement_kind': 'stability_file_type'}

#: Columns of the sheet `files` that fill the file entry's `sample_identity`, by
#: the quantity of `SampleIdentity` they fill.
SAMPLE_IDENTITY_COLUMNS = {
    'sample_id': 'sample_id',
    'sample_reference': 'external_reference',
}

#: What the column `files` holds, for the template.
FILES_COLUMN_DESCRIPTION = """
The path pattern of the files, relative to the upload root, matched against the
whole path with case: `*` stands for any characters, also across folders, `?` for
one character, `[abc]` for one of the characters. No leading `/`, no `..` and no
backslash. Later rows override earlier ones, field by field; empty cells give
nothing.
"""

#: The three columns of a layer block, in their order.
LAYER_FIELDS = ('layer_type', 'layer_material_name', 'layer_thickness')

#: A header of the sheet `samples`: an optional layer label, a name and an optional
#: unit in brackets, e.g. `Layer2: layer_thickness [nm]` or `active_area [cm^2]`.
HEADER_RE = re.compile(
    r'^\s*(?:Layer\s*(?P<layer>\d+)\s*:\s*)?(?P<name>[A-Za-z_]+)\s*'
    r'(?:\[(?P<unit>[^\]]*)\])?\s*$'
)

#: Text that a cell of a yes/no column may hold, ignoring case.
TRUE_TEXTS = ('yes', 'true', '1', 'y', 'x')
FALSE_TEXTS = ('no', 'false', '0', 'n', '')


# Cells and paths.


def is_empty(value) -> bool:
    """Whether a cell holds nothing: `None`, NaN or blank text."""
    if value is None:
        return True
    if isinstance(value, float) and math.isnan(value):
        return True
    return isinstance(value, str) and not value.strip()


def clean_sample_id(sample_id) -> str | None:
    """`sample_id` without spaces at its start and end, `None` if nothing is left. A
    whole number read as a float, as spreadsheets give it, is written without `.0`."""
    if isinstance(sample_id, float) and sample_id.is_integer():
        sample_id = int(sample_id)
    return None if is_empty(sample_id) else str(sample_id).strip()


def pattern_error(pattern: str | None) -> str | None:
    """Why the path pattern `pattern` is not accepted, or `None` if it is.

    A pattern is matched only as text against paths within the upload, so it can
    never reach anything outside it; these rules reject patterns that could only be
    mistakes."""
    if not pattern or not pattern.strip():
        return 'empty pattern'
    if len(pattern) > MAX_PATTERN_LENGTH:
        return f'longer than {MAX_PATTERN_LENGTH} characters'
    if pattern.startswith('/'):
        return 'starts with /; patterns are relative to the upload'
    if '\\' in pattern:
        return 'contains a backslash; use / between folders'
    if '..' in PurePosixPath(pattern).parts:
        return 'contains ..'
    return None


def sample_entry_path(sample_id: str, part: str = '') -> str:
    """The path in the upload of the entry of the sample `sample_id`, or of one of
    its parts (`substrate`, `encapsulation`). Characters that are not safe in a
    file name become `_`."""
    name = re.sub(r'[^A-Za-z0-9._-]', '_', sample_id)
    suffix = f'_{part}' if part else ''
    return f'{SAMPLES_FOLDER}/{name}{suffix}.archive.json'


def sample_lab_id(prefix: str, sample_id: str, part: str = '') -> str:
    """The lab ID of the sample `sample_id`, or of one of its parts, by
    `unique_lab_id`. E.g. `RPV-261-00001-EF:RPV-S1` and
    `RPV-261-00001-EF:RPV-S1-substrate`."""
    suffix = f'-{part}' if part else ''
    return unique_lab_id(prefix, f'{sample_id}{suffix}')


def sample_entry_reference(sample_id: str, part: str = '') -> str:
    """A reference to the data of the entry of the sample `sample_id`, or of one of
    its parts, in the same upload."""
    return f'../upload/archive/mainfile/{sample_entry_path(sample_id, part)}#data'


# Reading the sheets.


def _sheets(path: str, file) -> dict:
    """The sheets of the spreadsheet `file`, named `path`, as NOMAD's tabular parser
    reads them: per sheet, per column header, per row index, the cell value."""
    return dict(read_table_data(path, file).iloc[:, 0].items())


def read_sheets(context, path: str) -> dict:
    """The sheets of the spreadsheet `path` of the upload, as `_sheets` reads them."""
    with context.raw_file(path, 'rb') as file:
        return _sheets(path, file)


def read_sheet_rows(data: dict, sheet: str) -> list[dict]:
    """The rows of the sheet `sheet`, as dictionaries from header to cell, from
    `data`, the sheets as `read_sheets` reads them."""
    columns = data.get(sheet)
    if not columns:
        return []
    indices = sorted({index for column in columns.values() for index in column})
    return [
        {header: column.get(index) for header, column in columns.items()}
        for index in indices
    ]


# The sheet `files`.


class FileRow(NamedTuple):
    """A row of the sheet `files`: its path pattern and the values it gives."""

    pattern: str
    values: dict


def file_column_quantity(name: str):
    """The quantity that the column `name` of the sheet `files` fills: one of
    `StabilityActivity`, or of its `SampleIdentity`."""
    if name in SAMPLE_IDENTITY_COLUMNS:
        return SampleIdentity.m_def.all_quantities[SAMPLE_IDENTITY_COLUMNS[name]]
    return StabilityActivity.m_def.all_quantities[name]


def file_rows(data: dict, logger: 'BoundLogger | None' = None) -> list[FileRow]:
    """The readable rows of the sheet `files` in `data`, the sheets as
    `read_sheets` reads them. Unknown columns, invalid patterns and values that a
    `StabilityActivity` does not accept are logged as errors naming row and column, if
    a `logger` is given, and left out: an unknown column or a cell, or a row with an
    invalid pattern."""

    def problem(row, column, message):
        if logger is not None:
            logger.error(
                'could not read a file row', row=row, column=column, reason=message
            )

    rows = read_sheet_rows(data, 'files')
    columns = []
    for header in rows[0] if rows else []:
        name = str(header).strip()
        name = FILE_COLUMN_ALIASES.get(name, name)
        if name in FILE_COLUMNS:
            columns.append((header, name))
        elif not name.startswith('Unnamed:'):
            problem(1, header, 'unknown column')

    readable = []
    for number, row in enumerate(rows, start=2):
        cells = {name: row.get(header) for header, name in columns}
        if all(is_empty(cell) for cell in cells.values()):
            continue
        pattern = None if is_empty(cells.get('files')) else str(cells['files'])
        error = pattern_error(pattern)
        if error is not None:
            problem(number, 'files', error)
            continue
        values = {}
        for name, cell in cells.items():
            if name == 'files' or is_empty(cell):
                continue
            if name == 'sample_id':
                values[name] = clean_sample_id(cell)
                continue
            # The file entry's own quantity checks and converts the value.
            quantity = file_column_quantity(name)
            check = quantity.m_parent.section_cls()
            # A number stays a number, as for a `duration`; all else is read as text.
            is_number = isinstance(cell, int | float) and not isinstance(cell, bool)
            try:
                check.m_set(quantity, cell if is_number else str(cell).strip())
            except Exception as exception:
                problem(number, name, str(exception))
                continue
            values[name] = check.m_get(quantity)
        readable.append(FileRow(pattern, values))
    return readable


def described_values(path: str, rows: list[FileRow]) -> dict:
    """The values that the rows of the sheet `files` whose pattern matches `path`
    give, field by field; a later row overrides an earlier one."""
    values = {}
    for row in rows:
        if fnmatchcase(path, row.pattern):
            values.update(row.values)
    return values


class Spreadsheet(NamedTuple):
    """What a file entry reads from the project data spreadsheet: the rows of the
    sheet `files`, the identifiers of the samples of the sheet `samples`, and the
    proposal number of the sheet `project`, `None` if it gives none."""

    file_rows: list[FileRow]
    sample_ids: frozenset[str]
    proposal_number: str | None = None


def load_spreadsheet(context) -> Spreadsheet | None:
    """The `Spreadsheet` of the upload whose context is `context`, `None` if it has
    no project data spreadsheet or it cannot be read.

    Every file of an upload reads it, so it is read once per version of the file
    and process, recognized by its size and modification time."""
    try:
        if not context.raw_path_exists(PROJECT_DATA_FILE):
            return None
        os_path = context.upload_files.raw_file_object(PROJECT_DATA_FILE).os_path
        stat = os.stat(os_path)
        return _read_spreadsheet(os_path, stat.st_size, stat.st_mtime_ns)
    except Exception:
        return None


@lru_cache(maxsize=4)
def _read_spreadsheet(os_path: str, _size: int, _mtime: int) -> Spreadsheet:
    with open(os_path, 'rb') as file:
        data = _sheets(PROJECT_DATA_FILE, file)
    sample_ids = {
        clean_sample_id(row.get('sample_id'))
        for row in read_sheet_rows(data, 'samples')
    }
    project = read_sheet_rows(data, 'project')
    cell = project[0].get('proposal_number') if project else None
    proposal_number = None if is_empty(cell) else str(cell).strip()
    return Spreadsheet(file_rows(data), frozenset(sample_ids - {None}), proposal_number)


# The sheet `samples`.


def _kind(quantity) -> str:
    """`bool`, `int`, `float` or `str`: how a cell is read into `quantity`."""
    standard = quantity.type.standard_type()
    for kind in ('bool', 'int', 'float'):
        if standard.startswith(kind):
            return kind
    return 'str'


def _bool_value(value) -> bool:
    """`value` from a cell of a TRUE/FALSE column."""
    # A column with empty cells is read as numbers: TRUE as 1.0.
    if isinstance(value, bool | int | float) and value in (0, 1):
        return bool(value)
    text = str(value).strip().lower()
    if text not in TRUE_TEXTS + FALSE_TEXTS:
        raise ValueError(f'{value!r} is not TRUE or FALSE')
    return text in TRUE_TEXTS


def _quantity_value(quantity, value, unit: str | None):
    """`value` from a cell as a value of `quantity`, converted from `unit`, the unit
    in the column's header, to the quantity's unit."""
    kind = _kind(quantity)
    if kind == 'bool':
        return _bool_value(value)
    if kind == 'int':
        number = float(value)
        if not number.is_integer():
            raise ValueError(f'{value!r} is not a whole number')
        return int(number)
    if kind != 'float':
        return str(value).strip()
    given_unit = (unit or '').replace('^', '**').strip()
    if quantity.unit is None:
        if given_unit:
            raise ValueError(f'{given_unit!r}: this column has no unit')
        return float(value)
    return ureg.Quantity(float(value), given_unit or quantity.unit).to(quantity.unit)


def sample_columns(headers, logger: 'BoundLogger') -> tuple[dict, dict]:
    """The readable columns of the sheet `samples` with the headers `headers`: the
    fixed columns as header to (name, unit), and the complete layer blocks as block
    number to field to (header, unit), in block order. Headers that cannot be read,
    and incomplete or repeated layer blocks, are logged as errors in row 1 and their
    columns are ignored."""

    def problem(column, message):
        logger.error('could not read a sample', row=1, column=column, reason=message)

    columns: dict[str, tuple[str, str | None]] = {}
    blocks: dict[int, dict[str, tuple[str, str | None]]] = {}
    broken: set[int] = set()
    for header in headers:
        if str(header).startswith('Unnamed:'):
            continue
        match = HEADER_RE.match(str(header))
        name = match['name'] if match else None
        if match is not None and match['layer'] is not None:
            number = int(match['layer'])
            block = blocks.setdefault(number, {})
            if name not in LAYER_FIELDS:
                problem(header, f'a layer column is one of {", ".join(LAYER_FIELDS)}')
                broken.add(number)
            elif name in block:
                problem(header, f'Layer{number} has {name} twice')
                broken.add(number)
            else:
                block[name] = (header, match['unit'])
        elif name in SAMPLE_COLUMNS:
            columns[header] = (name, match['unit'])
        elif name != STANDARD_COLUMN:
            problem(header, 'unknown column')
    for number, block in list(blocks.items()):
        missing = [field for field in LAYER_FIELDS if field not in block]
        if missing and number not in broken:
            problem(f'Layer{number}', f'missing column {", ".join(missing)}')
        if missing or number in broken:
            del blocks[number]
    return columns, dict(sorted(blocks.items()))


def sample_sections(
    row: dict, number: int, columns: dict, blocks: dict, logger: 'BoundLogger'
):
    """The sections that the row `row` (the `number`th row of the sheet `samples`)
    describes, read from the `columns` and layer `blocks` of `sample_columns`:
    sample, substrate, and encapsulation if its columns are filled; `None` if a cell
    cannot be read, logged as an error naming row and column."""
    values: dict[str, dict] = {key: {} for key in SAMPLE_SECTIONS}
    ok = True

    def read(quantity, header, unit):
        nonlocal ok
        try:
            return _quantity_value(quantity, row[header], unit)
        except Exception as error:
            ok = False
            logger.error(
                'could not read a sample', row=number, column=header, reason=str(error)
            )
            return None

    for header, (name, unit) in columns.items():
        if is_empty(row.get(header)):
            continue
        section, quantity_name = SAMPLE_COLUMNS[name]
        if name == 'sample_id':
            values['sample']['sample_id'] = clean_sample_id(row[header])
            continue
        quantity = SAMPLE_SECTIONS[section].m_def.all_quantities[quantity_name]
        values[section][quantity_name] = read(quantity, header, unit)

    sample_id = values['sample'].pop('sample_id', None)
    if sample_id is None:
        logger.error(
            'could not read a sample',
            row=number,
            column='sample_id',
            reason='no sample_id',
        )
        return None

    layer_quantities = LayerProperties.m_def.all_quantities
    layers = []
    for block in blocks.values():
        cells = {
            field: (header, unit)
            for field, (header, unit) in block.items()
            if not is_empty(row.get(header))
        }
        if cells:
            layers.append(
                LayerProperties(
                    **{
                        field: read(layer_quantities[field], header, unit)
                        for field, (header, unit) in cells.items()
                    }
                )
            )
    if not ok:
        return None

    substrate = Substrate(
        name=f'{sample_id} substrate',
        substrate_properties=layers,
        **values['substrate'],
    )
    sample = SolarCellSample(
        name=values['sample'].pop('name', sample_id),
        sample_id=sample_id,
        substrate=sample_entry_reference(sample_id, 'substrate'),
        **values['sample'],
    )
    if values['module']:
        sample.module_configuration = ModuleConfiguration(**values['module'])
    encapsulation = None
    if values['encapsulation']:
        encapsulation = Encapsulation(
            name=f'{sample_id} encapsulation',
            samples=[
                CompositeSystemReference(reference=sample_entry_reference(sample_id))
            ],
            **values['encapsulation'],
        )
    return sample_id, sample, substrate, encapsulation


#: The sheet of the URLs linked to the project, and its only column.
REFERENCES_SHEET = 'references'
REFERENCE_COLUMN = 'url'

#: What the column `url` of the sheet `references` holds, for the template.
REFERENCE_COLUMN_DESCRIPTION = """
A URL of a database or repository linked to the project, e.g. a data set on Zenodo
or a DOI link: https://doi.org/10.5281/zenodo.1234567. One per row.
"""


def project_references(data: dict, logger: 'BoundLogger') -> list[str]:
    """The URLs of the sheet `references` in `data`, in their order. A cell that is
    not a URL with a scheme and a host, such as https://zenodo.org/records/1, is
    logged as an error naming row and column and left out."""
    urls = []
    for number, row in enumerate(read_sheet_rows(data, REFERENCES_SHEET), start=2):
        cell = row.get(REFERENCE_COLUMN)
        if is_empty(cell):
            continue
        url = str(cell).strip()
        parts = urlsplit(url)
        if parts.scheme in ('http', 'https') and parts.netloc:
            urls.append(url)
        else:
            logger.error(
                'could not read a reference',
                row=number,
                column=REFERENCE_COLUMN,
                reason=f'{url!r} is not a URL beginning with http:// or https://',
            )
    return urls


def sample_standards(data: dict) -> dict[str, list[str]]:
    """The standards written in the column `standard` of the sheet `samples` in
    `data`, by sample identifier, for the samples that have any. A comma in
    parentheses does not separate, as in `ISOS-L-2 (65 °C, MPP)`."""
    standards = {}
    for row in read_sheet_rows(data, 'samples'):
        sample_id = clean_sample_id(row.get('sample_id'))
        cell = row.get(STANDARD_COLUMN)
        written = None if is_empty(cell) else split_commas([cell])
        if sample_id is not None and written:
            standards[sample_id] = written
    return standards


def write_sample_entries(
    context, data: dict, lab_id_prefix: str, logger: 'BoundLogger'
) -> list[SampleIdentity]:
    """Writes the entries of the samples of the sheet `samples` in `data` into the
    upload's folder `samples`, with lab IDs made with `lab_id_prefix`, and has NOMAD
    process them; returns the identity of each sample written, with a reference to
    its entry. Entries of earlier imports are overwritten; rows that cannot be read,
    and repeated sample identifiers, are logged as errors and left out."""
    identities = []
    seen_paths: dict[str, str] = {}
    if not context.raw_path_exists(SAMPLES_FOLDER):
        context.upload_files.raw_create_directory(SAMPLES_FOLDER)
    rows = read_sheet_rows(data, 'samples')
    columns, blocks = sample_columns(rows[0] if rows else [], logger)
    for number, row in enumerate(rows, start=2):
        if all(is_empty(cell) for cell in row.values()):
            continue
        sections = sample_sections(row, number, columns, blocks, logger)
        if sections is None:
            continue
        sample_id, sample, substrate, encapsulation = sections
        path = sample_entry_path(sample_id)
        if path in seen_paths:
            logger.error(
                'could not read a sample',
                row=number,
                column='sample_id',
                reason=f'{sample_id!r} is given twice, or names the same file as '
                f'{seen_paths[path]!r}',
            )
            continue
        seen_paths[path] = sample_id

        parts = {'substrate': substrate, '': sample, 'encapsulation': encapsulation}
        for part, section in parts.items():
            if section is None:
                continue
            section.lab_id = sample_lab_id(lab_id_prefix, sample_id, part)
            if part == 'encapsulation':
                section.samples[0].lab_id = sample.lab_id
            entry_path = sample_entry_path(sample_id, part)
            with context.raw_file(entry_path, 'w') as file:
                json.dump(
                    {'data': section.m_to_dict(with_root_def=True)}, file, indent=2
                )
            context.process_updated_raw_file(entry_path, allow_modify=True)
        identities.append(
            SampleIdentity(sample_id=sample_id, entry=sample_entry_reference(sample_id))
        )
    return identities


# The template.


#: The colours of the template's column groups: of the header, written in white
#: bold, and the light tint of the column below it. Columns of one group are filled
#: alike, so that the parts of a sample or a layer block are seen at a glance.
TEMPLATE_GROUP_COLORS = {
    'identity': ('1F4E79', 'DDEBF7'),
    'proposal': ('375623', 'E2EFDA'),
    'documents': ('7F6000', 'FFF2CC'),
    'values': ('375623', 'E2EFDA'),
    'sample': ('5B2C6F', 'EADCF0'),
    'module': ('833C0B', 'FBE4D5'),
    'substrate': ('0B5345', 'D1F2EB'),
    'encapsulation': ('7B241C', 'F5D5D2'),
    'layer': ('404040', 'F2F2F2'),
    'layer_alternate': ('707070', 'E4E4E4'),
}

#: How many rows the lists of the template, the sheets `files` and `samples`, offer;
#: rows can be added.
TEMPLATE_LIST_ROWS = 40

#: The sheet of the template that says how to fill it in, on which it opens. Not the
#: first sheet: that is `project`, which NOMAD's tabular parser reads.
TEMPLATE_GUIDE_SHEET = 'How to fill in'

#: The lines of `TEMPLATE_GUIDE_SHEET`, each with what is shown beside it: `form`, a
#: field to fill; `list`, a row of a list; `header`, a heading; else nothing.
TEMPLATE_GUIDE = (
    ('title', 'Project data of a PV stability upload'),
    (
        'text',
        'Fill in this workbook and put it, named project_data.xlsx, at the root of '
        'the upload. NOMAD reads it when the upload is processed: the proposal, the '
        'samples with their layer stacks and standards, and values for the files '
        'that their own reading code does not find.',
    ),
    ('heading', 'What to fill in'),
    (
        'form',
        'A field: one value. In the sheet project, the boxed cells under the '
        'headings hold the proposal as submitted in GATE.',
    ),
    (
        'list',
        'A row of a list: one item per row, from the top, without gaps. In the sheet '
        'files, one path pattern and the values for the files it matches; in the '
        'sheet samples, one sample; in the sheet references, one URL of a database '
        'or repository linked to the project. Insert rows within a list if you need '
        'more.',
    ),
    (
        'header',
        'A heading: fixed, do not change it. Point at a heading to read what belongs '
        'below it. Many columns offer a dropdown of allowed or suggested values. Units '
        'are those in the headings, e.g. active_area [cm^2].',
    ),
    ('heading', 'Good to know'),
    (
        'text',
        'Only the outlined cells can be edited. The sheets are protected without a '
        'password: to change more, e.g. to paste another layer block (Layer9: …) at '
        'the end of the sheet samples, unprotect the sheet (Review, Unprotect sheet).',
    ),
    (
        'text',
        'Dates and times are written as text, e.g. 2026-09-13 or '
        '2026-09-13T08:00:00+02:00. Several values in one cell are separated by '
        'commas, e.g. the standards ISOS-L-2 (65 °C, MPP), ISOS-D-1.',
    ),
    (
        'text',
        'The colours of the headings group the columns: what identifies the proposal, '
        'a file pattern or a sample (blue), the sample, module, substrate and '
        'encapsulation, and the layer blocks in alternating grey.',
    ),
)

#: The colours of the sheets' tabs.
TEMPLATE_TAB_COLORS = {
    'project': '375623',
    'files': '1F4E79',
    'samples': '5B2C6F',
    REFERENCES_SHEET: '7F6000',
}


class TemplateColumn(NamedTuple):
    """A column of the template: its header, the comment on the header, the values
    of its dropdown, whether other values are refused, whether its cells are text,
    and its group in `TEMPLATE_GROUP_COLORS`."""

    header: str
    comment: str | None
    values: list | None = None
    strict: bool = False
    text: bool = False
    group: str = 'values'


def _unit_label(quantity) -> str:
    """The unit of `quantity` as written in a header, e.g. ` [cm^2]`; empty without
    a unit."""
    if quantity.unit is None:
        return ''
    return f' [{format(quantity.unit, "~")}]'.replace(' ** ', '^').replace('**', '^')


def _value_column(header: str, quantity, text: bool = False) -> TemplateColumn:
    """The column `header` of `quantity`: a TRUE/FALSE dropdown for a yes/no
    quantity, the allowed values of an enumeration, or the suggestions of its ELN
    annotation."""
    if _kind(quantity) == 'bool':
        return TemplateColumn(header, quantity.description, ['TRUE', 'FALSE'], True)
    if quantity.type.standard_type() == 'enum':
        return TemplateColumn(
            header, quantity.description, list(quantity.type), True, text
        )
    eln = quantity.m_get_annotations('eln')
    props = eln.get('props') if isinstance(eln, dict) else getattr(eln, 'props', None)
    suggestions = (props or {}).get('suggestions')
    return TemplateColumn(header, quantity.description, suggestions, False, text)


def template_columns(layer_blocks: int = TEMPLATE_LAYER_BLOCKS) -> dict:
    """The columns of the sheets `project`, `files`, `samples` and `references` of
    the template,
    from the schema: the quantities with a tabular annotation, and the sample
    columns with their units followed by `layer_blocks` layer blocks."""
    project = []
    for quantity in ProjectData.m_def.all_quantities.values():
        tabular = quantity.m_get_annotations('tabular')
        if tabular is not None and '/' not in tabular.name:
            if tabular.name in ('proposal_number', 'proposal'):
                group = 'identity'
            elif tabular.name.endswith('_file'):
                group = 'documents'
            else:
                group = 'proposal'
            column = _value_column(tabular.name, quantity, text=True)
            project.append(column._replace(group=group))

    files = [
        TemplateColumn('files', FILES_COLUMN_DESCRIPTION, text=True, group='identity')
    ]
    for name in FILE_COLUMNS[1:]:
        column = _value_column(name, file_column_quantity(name), text=True)
        group = 'sample' if name in SAMPLE_IDENTITY_COLUMNS else 'values'
        files.append(column._replace(group=group))

    samples = [
        TemplateColumn(
            'sample_id',
            'The identifier of the sample, as the stations write it in their files. '
            'Unique in this sheet.',
            text=True,
            group='identity',
        ),
        TemplateColumn(
            STANDARD_COLUMN, STANDARD_COLUMN_DESCRIPTION, text=True, group='identity'
        ),
    ]
    for name, (section, quantity_name) in SAMPLE_COLUMNS.items():
        if name != 'sample_id':
            quantity = SAMPLE_SECTIONS[section].m_def.all_quantities[quantity_name]
            column = _value_column(f'{name}{_unit_label(quantity)}', quantity)
            samples.append(column._replace(group=section))
    layer_quantities = LayerProperties.m_def.all_quantities
    for block in range(1, layer_blocks + 1):
        group = 'layer' if block % 2 else 'layer_alternate'
        for field in LAYER_FIELDS:
            quantity = layer_quantities[field]
            header = f'Layer{block}: {field}{_unit_label(quantity)}'
            samples.append(_value_column(header, quantity)._replace(group=group))
    references = [
        TemplateColumn(
            REFERENCE_COLUMN, REFERENCE_COLUMN_DESCRIPTION, text=True, group='documents'
        )
    ]
    return {
        'project': project,
        'files': files,
        'samples': samples,
        REFERENCES_SHEET: references,
    }


#: The borders of the template: bold around what is filled in, thin between list
#: cells, white between headings so that neighbouring groups stay apart.
_BOLD = Side(style='medium', color='000000')
_THIN = Side(style='thin', color='A6A6A6')
_DIVIDER = Side(style='thin', color='FFFFFF')


def _form_field(cell) -> None:
    """Makes `cell` a field to fill: white, boxed by a bold border, editable; long
    text wraps within it."""
    cell.fill = PatternFill('solid', fgColor='FFFFFF')
    cell.border = Border(left=_BOLD, right=_BOLD, top=_BOLD, bottom=_BOLD)
    cell.alignment = Alignment(wrap_text=True, vertical='top')
    cell.protection = Protection(locked=False)


def _list_cell(cell, tint: str, first: bool, last: bool, bottom: bool) -> None:
    """Makes `cell` a cell of a list: rows alternate between `tint` and white, the
    list is outlined in bold (the `first` and `last` column, the `bottom` row),
    editable."""
    cell.fill = PatternFill('solid', fgColor=tint if cell.row % 2 else 'FFFFFF')
    cell.border = Border(
        left=_BOLD if first else _THIN,
        right=_BOLD if last else _THIN,
        top=_THIN,
        bottom=_BOLD if bottom else _THIN,
    )
    cell.protection = Protection(locked=False)


def _heading(cell, color: str) -> None:
    """Makes `cell` a heading: white bold text on `color`, locked."""
    cell.font = Font(bold=True, color='FFFFFF')
    cell.fill = PatternFill('solid', fgColor=color)
    cell.border = Border(left=_DIVIDER, right=_DIVIDER)
    cell.alignment = Alignment(wrap_text=True, vertical='center', horizontal='center')


def _dropdown(sheet, letter: str, column: TemplateColumn, lists) -> None:
    """Adds the dropdown of `column`, in the column `letter` of `sheet`, with its
    values in a new column of the hidden sheet `lists`."""
    list_letter = get_column_letter(lists.max_column + 1)
    if lists.max_column == 1 and lists['A1'].value is None:
        list_letter = 'A'
    lists[f'{list_letter}1'] = f'{sheet.title}: {column.header}'
    for row, value in enumerate(column.values, start=2):
        lists[f'{list_letter}{row}'] = value
    validation = DataValidation(
        type='list',
        formula1=f'{quote_sheetname("lists")}!${list_letter}$2:'
        f'${list_letter}${len(column.values) + 1}',
        allow_blank=True,
        showErrorMessage=column.strict,
    )
    sheet.add_data_validation(validation)
    validation.add(f'{letter}2:{letter}1000')


def _write_sheet(sheet, columns: list[TemplateColumn], lists) -> None:
    """Writes the headings of `columns` into `sheet` and below them the cells to
    fill: one row of fields for the sheet `project`, a list of `TEMPLATE_LIST_ROWS`
    rows for the others. Protects the sheet, so that only those cells can be
    edited, and rows can be added to a list."""
    is_form = sheet.title == 'project'
    last_row = 2 if is_form else 1 + TEMPLATE_LIST_ROWS
    sheet.sheet_properties.tabColor = TEMPLATE_TAB_COLORS[sheet.title]
    sheet.row_dimensions[1].height = 48
    if is_form:
        # Room for a title or an abstract of a few lines.
        sheet.row_dimensions[2].height = 60
    for index, column in enumerate(columns, start=1):
        letter = get_column_letter(index)
        header_color, tint = TEMPLATE_GROUP_COLORS[column.group]
        cell = sheet.cell(row=1, column=index, value=column.header)
        _heading(cell, header_color)
        if column.comment:
            cell.comment = Comment(' '.join(column.comment.split()), 'NOMAD')
        # Free text, such as a title or a path pattern, gets room to be read.
        least = 24 if column.text and not column.values else 14
        sheet.column_dimensions[letter].width = max(
            least, min(40, len(column.header) + 4)
        )
        for row in range(2, last_row + 1):
            cell = sheet.cell(row=row, column=index)
            if is_form:
                _form_field(cell)
            else:
                first, last = index == 1, index == len(columns)
                _list_cell(cell, tint, first, last, row == last_row)
            if column.text:
                # Text, so that dates and identifiers are kept as written.
                cell.number_format = '@'
        if column.values:
            _dropdown(sheet, letter, column, lists)
    sheet.freeze_panes = 'A2'
    # Without a password: the protection guides, it does not secure.
    sheet.protection = SheetProtection(
        sheet=True,
        insertRows=is_form,
        deleteRows=is_form,
        formatColumns=False,
        formatRows=False,
    )


def _write_guide(guide) -> None:
    """Writes `TEMPLATE_GUIDE` into the sheet `guide`, each line beside an example
    of what it describes."""
    guide.sheet_properties.tabColor = '000000'
    guide.column_dimensions['A'].width = 18
    guide.column_dimensions['B'].width = 100
    for row, (kind, text) in enumerate(TEMPLATE_GUIDE, start=1):
        cell = guide.cell(row=row, column=2, value=text)
        cell.alignment = Alignment(wrap_text=True, vertical='center')
        example = guide.cell(row=row, column=1)
        if kind == 'title':
            cell.font = Font(bold=True, size=16)
        elif kind == 'heading':
            cell.font = Font(bold=True, size=12)
        elif kind == 'form':
            _form_field(example)
        elif kind == 'list':
            _list_cell(example, TEMPLATE_GROUP_COLORS['sample'][1], True, True, False)
        elif kind == 'header':
            example.value = 'heading'
            _heading(example, TEMPLATE_GROUP_COLORS['identity'][0])
        example.protection = Protection(locked=True)
        # A line of about 100 characters in the wide column, 15 points high.
        lines = -(-len(text) // 100)
        guide.row_dimensions[row].height = 36 if kind == 'title' else 15 * lines + 12
    guide.protection = SheetProtection(sheet=True)


def write_project_data_template(path: str, layer_blocks: int = TEMPLATE_LAYER_BLOCKS):
    """Writes the empty spreadsheet `path` as a form: the sheets `project`, `files`
    and `samples` of `template_columns`, and the sheet `TEMPLATE_GUIDE_SHEET`, on
    which it opens.

    Only the cells to fill can be edited; the sheets are protected without a
    password. In `project`, they are single fields under the headings, each boxed by
    a bold border; in `files` and `samples`, lists of `TEMPLATE_LIST_ROWS` rows in
    alternating colours inside a bold outline, to which rows can be added. Headings
    are coloured by their group (`TEMPLATE_GROUP_COLORS`) and carry the quantities'
    descriptions as comments; dropdowns offer the allowed values, refusing others, or
    the suggestions, accepting others, from a hidden sheet `lists`."""
    workbook = Workbook()
    workbook.remove(workbook.active)
    sheets = template_columns(layer_blocks)
    for name in sheets:
        workbook.create_sheet(name)
    guide = workbook.create_sheet(TEMPLATE_GUIDE_SHEET)
    lists = workbook.create_sheet('lists')
    lists.sheet_state = 'hidden'
    for name, columns in sheets.items():
        _write_sheet(workbook[name], columns, lists)
    _write_guide(guide)
    workbook.active = workbook.worksheets.index(guide)
    workbook.properties.creator = 'nomad-pv-stability-measurements'
    workbook.properties.created = datetime(2026, 1, 1)
    workbook.save(path)
