from test_stability_upload_summary import normalize

from nomad_pv_stability_measurements.schema_packages.schema_package import (
    StabilitySample,
    StabilitySampleIdentity,
    StabilityUploadSummary,
)


def unitov_jv(device: str, date: str, time: str) -> str:
    """A UNITOV JV file of `device`, measured at `date` and `time`."""
    return (
        '## Header ##\t\t\r\n'
        f'Device\t{device}\t\r\n'
        'Test\tStability (JV)\t\r\n'
        f'Date\t{date}\t\r\n'
        f'Time\t{time}\t\r\n'
    )


def test_summary_groups_the_files_by_sample_in_measurement_order(staging_upload):
    summary = StabilityUploadSummary(
        samples=[StabilitySample(sample=StabilitySampleIdentity(id='entered'))]
    )
    normalize(
        staging_upload,
        {
            'UNITOV/run_1/000_JV.txt': unitov_jv('A1', '', ''),
            'UNITOV/run_1/001_JV.txt': unitov_jv('B2', '2023-10-20', '09:00:00'),
            'UNITOV/run_1/002_JV.txt': unitov_jv('A1', '2023-10-21', '09:00:00'),
            'UNITOV/run_1/003_JV.txt': unitov_jv('A1', '', ''),
            'UNITOV/run_2/001_JV.txt': unitov_jv('A1', '2023-10-19', '18:34:18'),
            'UNITOV/run_1/plot.pdf': '%PDF-1.4',
        },
        summary,
    )

    assert [
        (sample.sample.id, [record.file for record in sample.files])
        for sample in summary.samples
    ] == [
        (
            'A1',
            [
                'UNITOV/run_2/001_JV.txt',
                'UNITOV/run_1/002_JV.txt',
                'UNITOV/run_1/000_JV.txt',
                'UNITOV/run_1/003_JV.txt',
            ],
        ),
        ('B2', ['UNITOV/run_1/001_JV.txt']),
        (None, ['UNITOV/run_1/plot.pdf']),
    ]
    # Following a reference gives the entry of that file.
    first_of_a1 = summary.samples[0].files[0].entry
    assert (first_of_a1.file, first_of_a1.sample.id) == (
        'UNITOV/run_2/001_JV.txt',
        'A1',
    )


def test_summary_preserves_the_sample_reference(staging_upload, monkeypatch):
    from nomad_pv_stability_measurements.file_reading import file_reading_UNITOV

    reference = 'https://example.org/samples/A1'
    file_references = {
        'UNITOV/001_JV.txt': None,
        'UNITOV/002_JV.txt': reference,
        'UNITOV/003_JV.txt': 'https://example.org/samples/another-reference',
    }
    monkeypatch.setattr(
        file_reading_UNITOV,
        'match_jv',
        lambda path, content: (None, 'A1', file_references[path], {}),
    )
    summary = StabilityUploadSummary()
    normalize(
        staging_upload,
        {path: 'measurement' for path in file_references},
        summary,
    )

    group = summary.samples[0]
    assert (group.sample.id, group.sample.reference) == ('A1', reference)
    for record in group.files:
        entry = record.entry
        assert (entry.sample.id, entry.sample.reference) == (
            'A1',
            file_references[record.file],
        )
