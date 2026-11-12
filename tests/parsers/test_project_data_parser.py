import json

import pytest
from nomad import utils
from nomad.datamodel import EntryArchive, EntryMetadata
from nomad.parsing.parser import ArchiveParser
from nomad.parsing.parsers import match_parser

from nomad_pv_stability_measurements.parsers import (
    stability_file_parser_entry_point,
)
from nomad_pv_stability_measurements.schema_packages.schema_package import (
    StabilityUploadSummary,
)

SUPPLIED_SUMMARY = """
data:
  m_def: nomad_pv_stability_measurements.schema_packages.schema_package.StabilityUploadSummary
  proposal: https://example.org/proposals/42
"""


def test_parsing_a_file_creates_the_project_entry(staging_upload):
    staging_upload.add({'UNITOV/run_1/001_JV.txt': 'V,J\n'})
    staging_upload.parse('UNITOV/run_1/001_JV.txt')

    with staging_upload.context.raw_file('project_data.archive.json') as file:
        project = json.load(file)['data']
    assert project['m_def'].endswith('.ProjectData')
    assert staging_upload.processed == ['project_data.archive.json']


def test_a_summary_of_an_earlier_version_stays_the_project_entry(staging_upload):
    staging_upload.add(
        {
            'UNITOV/run_1/001_JV.txt': 'V,J\n',
            'stability_upload.archive.yaml': SUPPLIED_SUMMARY,
        }
    )
    staging_upload.parse('UNITOV/run_1/001_JV.txt')

    assert not staging_upload.context.raw_path_exists('project_data.archive.json')
    with staging_upload.context.raw_file('stability_upload.archive.yaml', 'r') as file:
        assert file.read() == SUPPLIED_SUMMARY
    assert staging_upload.processed == []


def test_parsing_outside_nomad_processing_creates_no_project_entry(tmp_path):
    (tmp_path / 'UNITOV').mkdir()
    (tmp_path / 'UNITOV' / '001_JV.txt').write_text('V,J\n')
    archive = EntryArchive(metadata=EntryMetadata(mainfile='UNITOV/001_JV.txt'))
    parser = stability_file_parser_entry_point.load()
    parser.parse(
        str(tmp_path / 'UNITOV' / '001_JV.txt'), archive, utils.get_logger(__name__)
    )

    assert sorted(path.name for path in tmp_path.iterdir()) == ['UNITOV']


def test_nomad_reads_a_summary_of_an_earlier_version(tmp_path):
    summary_file = tmp_path / 'stability_upload.archive.yaml'
    summary_file.write_text(SUPPLIED_SUMMARY)
    archive = EntryArchive(metadata=EntryMetadata())
    ArchiveParser().parse(str(summary_file), archive, utils.get_logger(__name__))

    assert isinstance(archive.data, StabilityUploadSummary)
    assert archive.data.proposal == 'https://example.org/proposals/42'


@pytest.mark.parametrize(
    'name',
    [
        'project_data.archive.json',
        'stability_upload.archive.json',
        'stability_upload.archive.yaml',
    ],
)
def test_project_entries_are_read_by_nomads_archive_parser(tmp_path, name):
    # Only entries of NOMAD's archive parser can be edited in NOMAD's new GUI.
    path = tmp_path / name
    path.write_text('{"data": {}}' if name.endswith('.json') else 'data: {}\n')
    parser, _ = match_parser(str(path))
    assert parser.name == 'parsers/archive'
