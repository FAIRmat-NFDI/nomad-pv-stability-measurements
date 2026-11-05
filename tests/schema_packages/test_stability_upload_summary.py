import re
from types import SimpleNamespace

import pytest
from nomad import config, utils
from nomad.datamodel import EntryArchive, EntryMetadata
from nomad.datamodel.context import ServerContext
from nomad.files import StagingUploadFiles

from nomad_pv_stability_measurements.parsers import (
    stability_file_parser_entry_point,
)
from nomad_pv_stability_measurements.parsers.stability_file_parser import (
    StabilityFileParser,
)
from nomad_pv_stability_measurements.schema_packages.schema_package import (
    StabilityFileReference,
    StabilityUploadSummary,
)

UPLOAD_ID = 'test_upload'

UNITOV_JV = (
    '## Header ##\t\t\r\n'
    'Device\t3C_C1_1\t\r\n'
    'Test\tStability (JV)\t\r\n'
    'Date\t2023-10-19\t\r\n'
    'Time\t18:34:18\t\r\n'
)


@pytest.fixture
def upload(tmp_path, monkeypatch):
    """Returns a function that makes a NOMAD staging upload in `tmp_path` from a text
    per path, processes its files with the file parser, and normalizes a summary of
    the upload."""
    monkeypatch.setattr(config.fs, 'staging', str(tmp_path / 'staging'))

    def normalize(files: dict[str, str], summary: StabilityUploadSummary) -> None:
        source = tmp_path / 'source'
        for path, content in files.items():
            (source / path).parent.mkdir(parents=True, exist_ok=True)
            (source / path).write_text(content)
        upload_files = StagingUploadFiles(UPLOAD_ID, create=True)
        upload_files.add_rawfiles(str(source))
        # The context sees the upload only through its id and files.
        context = ServerContext(
            upload=SimpleNamespace(upload_id=UPLOAD_ID, upload_files=upload_files)
        )

        # The entries that NOMAD's processing makes of the files the parser takes.
        for path in files:
            os_path = upload_files.raw_file_object(path).os_path
            if re.fullmatch(
                stability_file_parser_entry_point.mainfile_name_re, os_path
            ):
                archive = EntryArchive(
                    metadata=EntryMetadata(upload_id=UPLOAD_ID, mainfile=path),
                    m_context=context,
                )
                StabilityFileParser().parse(
                    os_path, archive, utils.get_logger(__name__)
                )
                entry_id = utils.generate_entry_id(UPLOAD_ID, path)
                upload_files.write_archive(entry_id, archive.m_to_dict())

        archive = EntryArchive(
            metadata=EntryMetadata(
                upload_id=UPLOAD_ID, mainfile='stability_upload.archive.json'
            ),
            data=summary,
            m_context=context,
        )
        summary.normalize(archive, utils.get_logger(__name__))

    return normalize


def test_summary_references_the_entry_of_every_file(upload):
    summary = StabilityUploadSummary(
        proposal='https://example.org/proposals/42',
        files=[StabilityFileReference(file='UNITOV/removed.txt')],
    )
    upload(
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

    assert [record.file for record in summary.files] == [
        'UNITOV/run_1/001_JV.txt',
        'UNITOV/run_1/plot.pdf',
    ]
    assert summary.institutions == ['UNITOV']
    assert summary.proposal == 'https://example.org/proposals/42'

    # Following a reference gives the entry of that file.
    jv, pdf = (record.entry for record in summary.files)
    assert (jv.file, jv.measurement_kind, jv.sample_id) == (
        'UNITOV/run_1/001_JV.txt',
        'jv',
        '3C_C1_1',
    )
    assert (pdf.file, pdf.measurement_kind) == ('UNITOV/run_1/plot.pdf', 'unknown')


def test_summary_names_every_institution_of_the_upload(upload):
    summary = StabilityUploadSummary(institutions=['TEMPLATE'])
    upload(
        {
            'UNITOV/run_1/001_JV.txt': UNITOV_JV,
            'HZB/jv_001.csv': 'V,J\n',
            'results/notes.txt': 'in no institution folder',
        },
        summary,
    )

    assert summary.institutions == ['HZB', 'UNITOV']
    assert [record.entry.institution for record in summary.files] == [
        'HZB',
        'UNITOV',
        None,
    ]
