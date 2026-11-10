import re

from nomad import utils
from nomad.datamodel import EntryArchive, EntryMetadata, User

from nomad_pv_stability_measurements.parsers import (
    stability_file_parser_entry_point,
)
from nomad_pv_stability_measurements.schema_packages.schema_package import (
    StabilityFileReference,
    StabilitySampleGroup,
    StabilityUploadSummary,
)

UNITOV_JV = (
    '## Header ##\t\t\r\n'
    'Device\t3C_C1_1\t\r\n'
    'Test\tStability (JV)\t\r\n'
    'Date\t2023-10-19\t\r\n'
    'Time\t18:34:18\t\r\n'
)


def normalize(upload, files: dict[str, str], summary: StabilityUploadSummary):
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
            mainfile='stability_upload.archive.json',
            main_author=upload.main_author,
        ),
        data=summary,
        m_context=upload.context,
    )
    summary.normalize(archive, utils.get_logger(__name__))


def records(summary: StabilityUploadSummary) -> list[StabilityFileReference]:
    """The file records of all sample groups of `summary`, ordered by file path."""
    return sorted(
        (record for sample in summary.file_groups for record in sample.files),
        key=lambda record: record.file,
    )


def test_summary_references_the_entry_of_every_file(staging_upload):
    summary = StabilityUploadSummary(
        proposal='https://example.org/proposals/42',
        file_groups=[
            StabilitySampleGroup(
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
    assert (jv.file, jv.measurement_kind, jv.sample_id) == (
        'UNITOV/run_1/001_JV.txt',
        'jv',
        '3C_C1_1',
    )
    assert (pdf.file, pdf.measurement_kind) == ('UNITOV/run_1/plot.pdf', 'unknown')


def test_summary_names_every_institution_of_the_upload(staging_upload):
    summary = StabilityUploadSummary(institutions=['TEMPLATE'])
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
    summary = StabilityUploadSummary()
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
