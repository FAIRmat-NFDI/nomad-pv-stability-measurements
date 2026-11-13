import re

from nomad import utils
from nomad.datamodel import EntryArchive, EntryMetadata, User

from nomad_pv_stability_measurements.parsers import (
    stability_file_parser_entry_point,
)
from nomad_pv_stability_measurements.schema_packages.schema_package import (
    ProjectData,
    StabilityFileGroup,
    StabilityFileReference,
)

UNITOV_JV = (
    '## Header ##\t\t\r\n'
    'Device\t3C_C1_1\t\r\n'
    'Test\tStability (JV)\t\r\n'
    'Date\t2023-10-19\t\r\n'
    'Time\t18:34:18\t\r\n'
)


def normalize(upload, files: dict[str, str], summary: ProjectData):
    """Adds `files` to the upload, makes the entries of the files that the file
    parser takes, and normalizes `summary` as the upload's summary."""
    upload.add(files)
    name_re = stability_file_parser_entry_point.mainfile_name_re
    for path in files:
        if re.fullmatch(name_re, upload.os_path(path)):
            upload.parse(path)

    archive = EntryArchive(
        metadata=EntryMetadata(
            upload_id=upload.upload_id,
            mainfile='project_data.archive.json',
            main_author=upload.main_author,
        ),
        data=summary,
        m_context=upload.context,
    )
    summary.normalize(archive, utils.get_logger(__name__))


def records(summary: ProjectData) -> list[StabilityFileReference]:
    """The file records of all sample groups of `summary`, ordered by file path."""
    return sorted(
        (
            record
            for group in [*summary.sample_series, *summary.general_groups]
            for record in group.files
        ),
        key=lambda record: record.file,
    )


def test_summary_references_the_entry_of_every_file(staging_upload):
    summary = ProjectData(
        proposal='https://example.org/proposals/42',
        general_groups=[
            StabilityFileGroup(
                files=[StabilityFileReference(file='UNITOV/removed.txt')]
            )
        ],
    )
    normalize(
        staging_upload,
        {
            'UNITOV/run_1/001_JV.txt': UNITOV_JV,
            'UNITOV/run_1/plot.pdf': '%PDF-1.4',
            'UNITOV/.DS_Store': '',
            'UNITOV/.backup/001_JV.txt': UNITOV_JV,
            'UNITOV/~lock.txt': '',
            'sample.archive.yaml': 'data: {}',
            'stability_upload.archive.json': '{}',
        },
        summary,
    )

    assert [record.file for record in records(summary)] == [
        'UNITOV/run_1/001_JV.txt',
        'UNITOV/run_1/plot.pdf',
    ]
    assert summary.institutions == ['UNITOV']
    assert summary.proposal == 'https://example.org/proposals/42'

    # Following a reference gives the entry of that file.
    jv, pdf = (record.entry for record in records(summary))
    assert (jv.file, jv.stability_file_type, jv.sample_identity.sample_id) == (
        'UNITOV/run_1/001_JV.txt',
        'jv',
        '3C_C1_1',
    )
    assert (pdf.file, pdf.stability_file_type) == ('UNITOV/run_1/plot.pdf', 'unknown')


def test_summary_names_every_institution_of_the_upload(staging_upload):
    summary = ProjectData(institutions=['TEMPLATE'])
    normalize(
        staging_upload,
        {
            'UNITOV/run_1/001_JV.txt': UNITOV_JV,
            'HZB/jv_001.csv': 'V,J\n',
            'results/notes.txt': 'in no institution folder',
        },
        summary,
    )

    assert summary.institutions == ['HZB', 'UNITOV']
    assert [record.entry.institution for record in records(summary)] == [
        'HZB',
        'UNITOV',
        None,
    ]


def test_summary_names_the_uploaders_institution_for_files_in_no_folder(
    staging_upload,
):
    staging_upload.main_author = User(email='researcher@uniroma2.it')
    summary = ProjectData()
    normalize(
        staging_upload,
        {'HZB/jv_001.csv': 'V,J\n', 'results/001_JV.txt': UNITOV_JV},
        summary,
    )

    assert summary.institutions == ['HZB', 'UNITOV']
    assert [record.entry.institution for record in records(summary)] == [
        'HZB',
        'UNITOV',
    ]


def test_summary_links_to_the_files_app_filtered_to_its_upload(staging_upload):
    from nomad_pv_stability_measurements.apps.stability_files import (
        stability_files_app,
    )

    summary = ProjectData()
    normalize(staging_upload, {'UNITOV/run_1/001_JV.txt': UNITOV_JV}, summary)

    query = f'?upload_id={staging_upload.upload_id}'
    path = stability_files_app.path
    assert summary.files_app.endswith(f'/apps/{path}{query}')


def test_summary_does_not_need_the_entries_of_the_files(staging_upload):
    # NOMAD may process the project entry before the entries of the files.
    staging_upload.add({'UNITOV/run_1/001_JV.txt': UNITOV_JV, 'HZB/jv_001.csv': ''})
    summary = ProjectData()
    normalize(staging_upload, {}, summary)

    assert summary.institutions == ['HZB', 'UNITOV']
    assert [
        (group.name, [record.file for record in group.files])
        for group in [*summary.sample_series, *summary.general_groups]
    ] == [('3C_C1_1', ['UNITOV/run_1/001_JV.txt']), ('Unknown', ['HZB/jv_001.csv'])]
    assert len(summary.figures) == 1
