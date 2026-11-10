import re
from datetime import datetime, timezone

import pytest
from nomad import utils
from nomad.datamodel import EntryArchive, EntryMetadata, User
from structlog.testing import capture_logs

from nomad_pv_stability_measurements.file_reading import file_reading_UNITOV
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


def parse(
    tmp_path, path: str, content: bytes, email: str | None = None
) -> EntryArchive:
    """Parses `content` stored at `path` within an upload in `tmp_path`, uploaded by
    a user with the address `email`, if given."""
    file_path = tmp_path / path
    file_path.parent.mkdir(parents=True, exist_ok=True)
    file_path.write_bytes(content)
    main_author = User(email=email) if email else None
    archive = EntryArchive(
        metadata=EntryMetadata(mainfile=path, main_author=main_author)
    )
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
    assert data.sample_id == '3C_C1_1'
    # 18:34:18 local time in Rome, in summer time (UTC+2).
    assert data.start_time == datetime(2023, 10, 19, 16, 34, 18, tzinfo=timezone.utc)


@pytest.mark.parametrize(
    'test, algorithm, kind',
    [
        ('Stability (Tracking)', 'MPPT', 'mpp_tracking'),
        ('Stability (Tracking)', 'Fixed Voltage', 'stability_series'),
        ('Stability (Parameters)', None, 'jv_parameters'),
    ],
)
def test_UNITOV_series_are_told_apart(tmp_path, test, algorithm, kind):
    content = UNITOV_JV.replace('Stability (JV)', test)
    if algorithm:
        content += f'Algorithm\t{algorithm}\t\r\n'
    content += 'Time (Hours)\tVoc (V) FW\r\n0.5\t1.05\r\n'

    data = parse(tmp_path, 'UNITOV/run_1/000_series.txt', content.encode()).data

    assert data.measurement_kind == kind
    # Each series ends at its last row, half an hour after its start.
    assert data.end_time == datetime(2023, 10, 19, 17, 4, 18, tzinfo=timezone.utc)


#: A UNITOV MPP tracking file of two hours, started at 18:34:18 in Rome. Long enough
#: that its last row lies far beyond the beginning of the file.
UNITOV_LONG_TRACKING = (
    UNITOV_JV.replace('Stability (JV)', 'Stability (Tracking)')
    + 'Algorithm\tMPPT\t\r\n'
    + 'Time (Hours)\tVoltage (V)\tCurrent Density (mA/cm2)\tPower (mW/cm2)\r\n'
    + ''.join(f'{hour / 1000}\t0.41\t5.29\t2.17\r\n' for hour in range(1, 2001))
)


def test_UNITOV_file_ends_at_its_last_row_or_else_when_it_starts(tmp_path):
    assert len(UNITOV_LONG_TRACKING) > (
        file_reading_UNITOV.HEAD_SIZE + file_reading_UNITOV.TAIL_SIZE
    )

    tracking_path = 'UNITOV/run_1/000_Tracking.txt'
    tracked = parse(tmp_path, tracking_path, UNITOV_LONG_TRACKING.encode()).data
    swept = parse(tmp_path, 'UNITOV/run_1/001_JV.txt', UNITOV_JV.encode()).data

    assert tracked.measurement_kind == 'mpp_tracking'
    # Two hours after the start at 18:34:18 in Rome.
    assert tracked.end_time == datetime(2023, 10, 19, 18, 34, 18, tzinfo=timezone.utc)
    assert swept.end_time == swept.start_time


def test_institution_without_tail_gets_no_end_from_the_last_row(tmp_path, monkeypatch):
    monkeypatch.setattr(file_reading_UNITOV, 'TAIL_SIZE', 0)
    tracking_path = 'UNITOV/run_1/000_Tracking.txt'
    tracked = parse(tmp_path, tracking_path, UNITOV_LONG_TRACKING.encode()).data

    assert tracked.measurement_kind == 'mpp_tracking'
    assert tracked.end_time == tracked.start_time


def test_utf8_header_text_is_kept(tmp_path):
    # NOMAD stores text files in UTF-8 before parsing, also those uploaded in Latin-1.
    content = UNITOV_JV.replace('3C_C1_1', 'Zelle_µ1').encode('utf-8')
    data = parse(tmp_path, 'UNITOV/run_1/001_JV.txt', content).data

    assert data.sample_id == 'Zelle_µ1'


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
    assert data.sample_id is None
    assert data.start_time is None


@pytest.mark.parametrize(
    'path, email, institution, kind',
    [
        # In no institution's folder: the uploader's email domain decides.
        ('results/001_JV.txt', 'researcher@uniroma2.it', 'UNITOV', 'jv'),
        ('results/001_JV.txt', 'researcher@Chem.Uniroma2.it', 'UNITOV', 'jv'),
        # The folder decides over the email domain.
        ('UNITOV/001_JV.txt', 'researcher@helmholtz-berlin.de', 'UNITOV', 'jv'),
        # Domains of no institution, also those that only end like one.
        ('results/001_JV.txt', 'researcher@gmail.com', None, 'unknown'),
        ('results/001_JV.txt', 'researcher@notuniroma2.it', None, 'unknown'),
    ],
)
def test_file_in_no_institution_folder_belongs_to_the_uploaders_institution(
    tmp_path, path, email, institution, kind
):
    data = parse(tmp_path, path, UNITOV_JV.encode(), email).data

    assert data.institution == institution
    assert data.measurement_kind == kind


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
