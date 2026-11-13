import re

from nomad import utils
from nomad.datamodel import EntryArchive, EntryMetadata, User
from nomad.utils import generate_entry_id

from nomad_pv_stability_measurements.parsers import (
    stability_file_parser_entry_point,
)
from nomad_pv_stability_measurements.schema_packages.schema_package import (
    ProjectData,
    StabilityActivityGroup,
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


def activities(summary: ProjectData) -> list:
    """The activities of all groups of `summary`, ordered by the path of their
    file."""
    return sorted(
        (
            reference.m_resolved()
            for group in [*summary.sample_series, *summary.general_groups]
            for reference in group.activities
        ),
        key=lambda activity: activity.file.path,
    )


def test_summary_references_the_entry_of_every_file(staging_upload):
    summary = ProjectData(
        proposal='https://example.org/proposals/42',
        general_groups=[
            StabilityActivityGroup(
                activities=['../upload/archive/mainfile/UNITOV/removed.txt#data']
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

    assert [activity.file.path for activity in activities(summary)] == [
        'UNITOV/run_1/001_JV.txt',
        'UNITOV/run_1/plot.pdf',
    ]
    assert summary.institutions == ['UNITOV']
    assert summary.proposal == 'https://example.org/proposals/42'

    # Following a reference gives the activity of that file.
    jv, pdf = activities(summary)
    assert (jv.file.path, jv.stability_file_type, jv.sample_identity.sample_id) == (
        'UNITOV/run_1/001_JV.txt',
        'jv',
        '3C_C1_1',
    )
    assert (pdf.file.path, pdf.stability_file_type) == (
        'UNITOV/run_1/plot.pdf',
        'unknown',
    )


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
    assert [activity.institution for activity in activities(summary)] == [
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
    assert [activity.institution for activity in activities(summary)] == [
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

    # The references name the entries the files will have, by their ids.
    def activity_of(path):
        entry_id = generate_entry_id(staging_upload.upload_id, path)
        return f'../uploads/{staging_upload.upload_id}/archive/{entry_id}#data'

    assert [
        (group.name, [activity.m_proxy_value for activity in group.activities])
        for group in [*summary.sample_series, *summary.general_groups]
    ] == [
        ('3C_C1_1', [activity_of('UNITOV/run_1/001_JV.txt')]),
        ('Unknown', [activity_of('HZB/jv_001.csv')]),
    ]
    assert len(summary.figures) == 1
