import re
from datetime import datetime, timezone

import pytest
from nomad import utils
from nomad.datamodel import EntryArchive, EntryMetadata
from structlog.testing import capture_logs

from nomad_pv_stability_measurements.parsers import (
    stability_file_parser_entry_point,
)
from nomad_pv_stability_measurements.parsers.stability_file_parser import (
    StabilityFileParser,
)

UNITOV_JV = (
    '## Header ##\t\t\r\n'
    '# General info\t\t\r\n'
    'User\tLHMJ\t\r\n'
    'Device\t3C_C1_1\t\r\n'
    'Test\tStability (JV)\t\r\n'
    'Date\t2023-10-19\t\r\n'
    'Time\t18:34:18\t\r\n'
)


def parse(tmp_path, path: str, content: bytes) -> EntryArchive:
    """Parses `content` stored at `path` within an upload in `tmp_path`."""
    file_path = tmp_path / path
    file_path.parent.mkdir(parents=True, exist_ok=True)
    file_path.write_bytes(content)
    archive = EntryArchive(metadata=EntryMetadata(mainfile=path))
    StabilityFileParser().parse(str(file_path), archive, utils.get_logger(__name__))
    return archive


def test_UNITOV_file_is_registered_with_kind_sample_and_start(tmp_path):
    with capture_logs() as logs:
        data = parse(tmp_path, 'UNITOV/run_1/001_JV.txt', UNITOV_JV.encode()).data

    assert not [log for log in logs if log['log_level'] in ('warning', 'error')]

    assert data.file == 'UNITOV/run_1/001_JV.txt'
    assert data.institution == 'UNITOV'
    assert data.measurement_kind == 'jv'
    assert data.file_format == 'txt'
    assert data.sample.id == '3C_C1_1'
    # 18:34:18 local time in Rome, in summer time (UTC+2).
    assert data.time_stamp == datetime(2023, 10, 19, 16, 34, 18, tzinfo=timezone.utc)


def test_utf8_header_text_is_kept(tmp_path):
    # NOMAD stores text files in UTF-8 before parsing, also those uploaded in Latin-1.
    content = UNITOV_JV.replace('3C_C1_1', 'Zelle_µ1').encode('utf-8')
    data = parse(tmp_path, 'UNITOV/run_1/001_JV.txt', content).data

    assert data.sample.id == 'Zelle_µ1'


@pytest.mark.parametrize(
    'path, content, log_level',
    [
        # In no institution's folder, so no institution's code can read it.
        ('results/001_JV.txt', UNITOV_JV.encode(), 'error'),
        # An institution's file that none of its functions recognizes.
        ('UNITOV/plots/001_JV.png', b'\x89PNG\r\n\x1a\n\x00\xff', 'warning'),
    ],
)
def test_unrecognized_file_is_registered_as_unknown(tmp_path, path, content, log_level):
    with capture_logs() as logs:
        data = parse(tmp_path, path, content).data

    assert [log['log_level'] for log in logs] == [log_level]

    assert data.file == path
    assert data.measurement_kind == 'unknown'
    assert data.sample is None
    assert data.time_stamp is None


@pytest.mark.parametrize(
    'path, is_registered',
    [
        ('/app/.volumes/fs/staging/ab/abc/raw/UNITOV/001_JV.txt', True),
        ('/app/.volumes/fs/staging/ab/abc/raw/images/cell.png', True),
        ('/app/.volumes/fs/staging/ab/abc/raw/sample.archive.json', False),
        ('/app/.volumes/fs/staging/ab/abc/raw/stability_upload.archive.yaml', False),
        ('/app/.volumes/fs/staging/ab/abc/raw/UNITOV/.DS_Store', False),
    ],
)
def test_parser_takes_data_files_but_not_archive_or_hidden_files(path, is_registered):
    name_re = stability_file_parser_entry_point.mainfile_name_re
    assert (re.fullmatch(name_re, path) is not None) == is_registered
