import pytest
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
        lambda path, content, tail: (None, None, 'A1', file_references[path], {}),
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


def unitov_tracking(device: str, date: str, time: str, hours: list[float]) -> str:
    """A UNITOV MPP tracking file of `device`, started at `date` and `time`, with one
    data row at each of `hours` after the start."""
    rows = ''.join(f'{hour}\t0.41\t5.29\t2.17\r\n' for hour in hours)
    return (
        '## Header ##\t\t\r\n'
        f'Device\t{device}\t\r\n'
        'Test\tStability (Tracking)\t\r\n'
        f'Date\t{date}\t\r\n'
        f'Time\t{time}\t\r\n'
        'Algorithm\tMPPT\t\r\n'
        'Time (Hours)\tVoltage (V)\tCurrent Density (mA/cm2)\tPower (mW/cm2)\r\n'
        f'{rows}'
    )


def channels(color: str) -> tuple[float, ...]:
    """The red, green, blue and alpha values of a colour `rgba(r, g, b, a)`."""
    return tuple(float(value) for value in color[5:-1].split(','))


def drawn_files(figure: dict) -> dict:
    """What the measurement timeline draws for each file, by file name: its kind,
    the label of the row it lies on, its vertical position, and the times and dot
    colours of its points, from start to end."""
    labels = figure['layout']['yaxis']['ticktext']
    drawn = {}
    for trace in figure['data']:
        if 'customdata' not in trace:  # a legend entry without data
            continue
        points = zip(
            trace['x'], trace['y'], trace['customdata'], trace['marker']['color']
        )
        for time, y, hover, color in points:
            if time is None:
                continue
            file = drawn.setdefault(
                hover[0],
                {'kind': trace['name'], 'row': labels[round(y)], 'y': y},
            )
            file.setdefault('times', []).append(time)
            file.setdefault('colors', []).append(color)
    return drawn


def test_summary_plots_each_file_from_start_to_end_in_its_sample_row(
    staging_upload,
):
    dark_jv = unitov_jv('A1', '2023-10-20', '09:00:00').replace(
        'Stability (JV)', 'Dark JV'
    )
    summary = StabilityUploadSummary()
    normalize(
        staging_upload,
        {
            'UNITOV/run_1/001_JV.txt': unitov_jv('B2', '2023-10-19', '19:00:00'),
            'UNITOV/run_1/002_JV.txt': unitov_jv('A1', '2023-10-19', '18:00:00'),
            'UNITOV/run_1/002_Tracking.txt': unitov_tracking(
                'A1', '2023-10-19', '18:00:00', [0.01, 0.25, 0.5]
            ),
            'UNITOV/dark/A1_dark.txt': dark_jv,
            # Not plotted: no time stamp, and no sample.
            'UNITOV/run_1/003_JV.txt': unitov_jv('A1', '', ''),
            'UNITOV/run_1/plot.pdf': '%PDF-1.4',
        },
        summary,
    )

    (figure,) = summary.figures
    drawn = drawn_files(figure.figure)
    # The times are the files' local Rome times in UTC. The tracking runs until its
    # last row, half an hour after its start; the other files end when they start.
    assert {
        file_name: (file['kind'], file['row'], file['times'][0], file['times'][-1])
        for file_name, file in drawn.items()
    } == {
        '001_JV.txt': (
            'jv',
            'B2',
            '2023-10-19T17:00:00+00:00',
            '2023-10-19T17:00:00+00:00',
        ),
        '002_JV.txt': (
            'jv',
            'A1',
            '2023-10-19T16:00:00+00:00',
            '2023-10-19T16:00:00+00:00',
        ),
        '002_Tracking.txt': (
            'mpp_tracking',
            'A1',
            '2023-10-19T16:00:00+00:00',
            '2023-10-19T16:30:00+00:00',
        ),
        'A1_dark.txt': (
            'dark_jv',
            'A1',
            '2023-10-20T07:00:00+00:00',
            '2023-10-20T07:00:00+00:00',
        ),
    }
    assert figure.figure['layout']['yaxis']['ticktext'] == ['A1', 'B2']

    # In one row, each kind lies at its own height, and a kind at the same height
    # in every row.
    heights = {(file['kind'], file['row']): file['y'] for file in drawn.values()}
    kinds_of_a1 = ('jv', 'dark_jv', 'mpp_tracking')
    assert len({heights[kind, 'A1'] for kind in kinds_of_a1}) == len(kinds_of_a1)
    assert heights['jv', 'B2'] - heights['jv', 'A1'] == pytest.approx(1)

    # Each kind has its own translucent colour, and lines are as thick as dots.
    traces = [trace for trace in figure.figure['data'] if 'customdata' in trace]
    line_colors = [trace['line']['color'] for trace in traces]
    assert len(set(line_colors)) == len(line_colors)
    for trace in traces:
        assert channels(trace['line']['color'])[3] < 1
        assert trace['line']['width'] == trace['marker']['size']

    # A file starts with a dot in its kind's colour and ends with a paler one; a
    # file that ends when it starts is a dot in its kind's colour.
    line_color = {trace['name']: trace['line']['color'] for trace in traces}
    start_color, end_color = drawn['002_Tracking.txt']['colors']
    assert start_color == line_color['mpp_tracking']
    start, end = channels(start_color), channels(end_color)
    assert all(paler >= color for paler, color in zip(end[:3], start[:3]))
    assert sum(end[:3]) > sum(start[:3])
    assert drawn['002_JV.txt']['colors'] == [line_color['jv']]

    # The legend lists the kinds and explains the paler dots.
    legend = [
        trace['name']
        for trace in figure.figure['data']
        if trace.get('showlegend', True)
    ]
    assert legend[:-1] == ['jv', 'dark_jv', 'mpp_tracking']
    assert 'end' in legend[-1]
    assert figure.figure['layout']['showlegend'] is True
    # Hovering is switched on by the figure itself, not only by its template, which
    # NOMAD's new GUI replaces with one that switches hovering off.
    assert figure.figure['layout']['hovermode'] == 'closest'
