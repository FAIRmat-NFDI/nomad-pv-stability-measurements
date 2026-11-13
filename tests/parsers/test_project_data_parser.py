import json

from nomad import utils
from nomad.datamodel import EntryArchive, EntryMetadata
from nomad.parsing.parsers import match_parser

from nomad_pv_stability_measurements.parsers import (
    stability_file_parser_entry_point,
)


def test_parsing_a_file_creates_the_project_entry(staging_upload):
    staging_upload.add({'UNITOV/run_1/001_JV.txt': 'V,J\n'})
    staging_upload.parse('UNITOV/run_1/001_JV.txt')

    with staging_upload.context.raw_file('project_data.archive.json') as file:
        project = json.load(file)['data']
    assert project['m_def'].endswith('.ProjectData')
    assert staging_upload.processed == ['project_data.archive.json']


def test_parsing_outside_nomad_processing_creates_no_project_entry(tmp_path):
    (tmp_path / 'UNITOV').mkdir()
    (tmp_path / 'UNITOV' / '001_JV.txt').write_text('V,J\n')
    archive = EntryArchive(metadata=EntryMetadata(mainfile='UNITOV/001_JV.txt'))
    parser = stability_file_parser_entry_point.load()
    parser.parse(
        str(tmp_path / 'UNITOV' / '001_JV.txt'), archive, utils.get_logger(__name__)
    )

    assert sorted(path.name for path in tmp_path.iterdir()) == ['UNITOV']


def test_the_project_entry_is_read_by_nomads_archive_parser(tmp_path):
    # Only entries of NOMAD's archive parser can be edited in NOMAD's new GUI.
    path = tmp_path / 'project_data.archive.json'
    path.write_text('{"data": {}}')
    parser, _ = match_parser(str(path))
    assert parser.name == 'parsers/archive'
