import json
import re

import pytest
from nomad import utils
from nomad.datamodel import EntryArchive, EntryMetadata

from nomad_pv_stability_measurements.parsers import (
    stability_file_parser_entry_point,
    summary_parser_entry_point,
)
from nomad_pv_stability_measurements.schema_packages.schema_package import (
    StabilityUploadSummary,
)

SUPPLIED_SUMMARY = """
data:
  m_def: nomad_pv_stability_measurements.schema_packages.schema_package.StabilityUploadSummary
  proposal: https://example.org/proposals/42
"""


def test_parsing_a_file_creates_the_summary(staging_upload):
    staging_upload.add({'UNITOV/run_1/001_JV.txt': 'V,J\n'})
    staging_upload.parse('UNITOV/run_1/001_JV.txt')

    with staging_upload.context.raw_file('stability_upload.archive.json') as file:
        summary = json.load(file)['data']
    assert summary['m_def'].endswith('.StabilityUploadSummary')
    assert staging_upload.processed == ['stability_upload.archive.json']


def test_a_supplied_summary_is_kept(staging_upload):
    staging_upload.add(
        {
            'UNITOV/run_1/001_JV.txt': 'V,J\n',
            'stability_upload.archive.yaml': SUPPLIED_SUMMARY,
        }
    )
    staging_upload.parse('UNITOV/run_1/001_JV.txt')

    assert not staging_upload.context.raw_path_exists('stability_upload.archive.json')
    with staging_upload.context.raw_file('stability_upload.archive.yaml', 'r') as file:
        assert file.read() == SUPPLIED_SUMMARY
    assert staging_upload.processed == []


def test_parsing_outside_nomad_processing_creates_no_summary(tmp_path):
    (tmp_path / 'UNITOV').mkdir()
    (tmp_path / 'UNITOV' / '001_JV.txt').write_text('V,J\n')
    archive = EntryArchive(metadata=EntryMetadata(mainfile='UNITOV/001_JV.txt'))
    parser = stability_file_parser_entry_point.load()
    parser.parse(
        str(tmp_path / 'UNITOV' / '001_JV.txt'), archive, utils.get_logger(__name__)
    )

    assert sorted(path.name for path in tmp_path.iterdir()) == ['UNITOV']


def test_summary_parser_reads_a_supplied_summary(tmp_path):
    summary_file = tmp_path / 'stability_upload.archive.yaml'
    summary_file.write_text(SUPPLIED_SUMMARY)
    archive = EntryArchive(metadata=EntryMetadata())
    summary_parser_entry_point.load().parse(
        str(summary_file), archive, utils.get_logger(__name__)
    )

    assert isinstance(archive.data, StabilityUploadSummary)
    assert archive.data.proposal == 'https://example.org/proposals/42'


@pytest.mark.parametrize(
    'path, is_summary',
    [
        ('/app/.volumes/fs/staging/ab/abc/raw/stability_upload.archive.json', True),
        ('/app/.volumes/fs/staging/ab/abc/raw/stability_upload.archive.yaml', True),
        ('/app/.volumes/fs/staging/ab/abc/raw/sample.archive.json', False),
        ('/app/.volumes/fs/staging/ab/abc/raw/UNITOV/001_JV.txt', False),
    ],
)
def test_summary_parser_takes_only_summary_files(path, is_summary):
    name_re = summary_parser_entry_point.mainfile_name_re
    assert (re.fullmatch(name_re, path) is not None) == is_summary


def test_summaries_are_processed_after_the_files():
    # NOMAD processes the parsers' levels in increasing order, so the summary's
    # references to the files' entries can be followed when it is normalized.
    assert summary_parser_entry_point.level > stability_file_parser_entry_point.level
