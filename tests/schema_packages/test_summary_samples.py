import pytest
from nomad.datamodel.metainfo.plot import PlotlyFigure
from test_stability_upload_summary import normalize

from nomad_pv_stability_measurements.schema_packages.schema_package import (
    StabilitySampleGroup,
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
        file_groups=[StabilitySampleGroup(sample_id='entered')]
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
        (sample.sample_id, [record.file for record in sample.files])
        for sample in summary.file_groups
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
        ('Unknown', ['UNITOV/run_1/plot.pdf']),
    ]
    # Following a reference gives the entry of that file.
    first_of_a1 = summary.file_groups[0].files[0].entry
    assert (first_of_a1.file, first_of_a1.sample_id) == (
        'UNITOV/run_2/001_JV.txt',
        'A1',
    )


def test_summary_keeps_each_files_own_sample_reference(staging_upload, monkeypatch):
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

    # One group for the sample, whose files keep their different references.
    (group,) = summary.file_groups
    assert group.sample_id == 'A1'
    for record in group.files:
        entry = record.entry
        assert (entry.sample_id, entry.sample_reference) == (
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
    the label of the row it lies on, its vertical position, and the times, marker
    symbols, sizes and colours of its points, from start to end, read from the
    markers, which carry the hover text."""
    labels = figure['layout']['yaxis']['ticktext']
    drawn = {}
    for trace in figure['data']:
        if 'customdata' not in trace:
            continue
        marker = trace['marker']
        for time, y, hover in zip(trace['x'], trace['y'], trace['customdata']):
            file = drawn.setdefault(
                hover[0],
                {'kind': trace['name'], 'row': labels[round(y)], 'y': y, 'points': []},
            )
            file['points'].append((time, marker['symbol'], marker['size']))
    for file in drawn.values():
        points = sorted(file.pop('points'))
        file['times'] = [time for time, _, _ in points]
        file['symbols'] = [symbol for _, symbol, _ in points]
        file['sizes'] = [size for _, _, size in points]
    return drawn


def timeline(staging_upload) -> PlotlyFigure:
    """The measurement timeline of an upload with files of several kinds and
    samples."""
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
            # Of no known sample: plotted in the row of the unknown sample.
            'UNITOV/run_1/004_JV.txt': unitov_jv('', '2023-10-19', '20:00:00'),
            # Not plotted: no start time.
            'UNITOV/run_1/003_JV.txt': unitov_jv('A1', '', ''),
            'UNITOV/run_1/plot.pdf': '%PDF-1.4',
        },
        summary,
    )

    (figure,) = summary.figures
    return figure


def test_summary_plots_each_file_from_start_to_end_in_its_sample_row(
    staging_upload,
):
    figure = timeline(staging_upload)
    drawn = drawn_files(figure.figure)
    # The times are as written in the files, in the institution's Rome time. The
    # tracking runs until its last row, half an hour after its start; the other
    # files end when they start.
    assert {
        file_name: (file['kind'], file['row'], file['times'][0], file['times'][-1])
        for file_name, file in drawn.items()
    } == {
        '001_JV.txt': (
            'jv',
            'B2',
            '2023-10-19T19:00:00',
            '2023-10-19T19:00:00',
        ),
        '002_JV.txt': (
            'jv',
            'A1',
            '2023-10-19T18:00:00',
            '2023-10-19T18:00:00',
        ),
        '002_Tracking.txt': (
            'mpp_tracking',
            'A1',
            '2023-10-19T18:00:00',
            '2023-10-19T18:30:00',
        ),
        'A1_dark.txt': (
            'dark_jv',
            'A1',
            '2023-10-20T09:00:00',
            '2023-10-20T09:00:00',
        ),
        '004_JV.txt': (
            'jv',
            'Unknown',
            '2023-10-19T20:00:00',
            '2023-10-19T20:00:00',
        ),
    }
    assert figure.figure['layout']['yaxis']['ticktext'] == ['A1', 'B2', 'Unknown']
    assert figure.figure['layout']['xaxis']['title']['text'] == 'Time (Europe/Rome)'

    # Hovering over a file's markers shows its values with labels, in the same time
    # zone, and no separate box with the kind.
    tracking = next(
        trace
        for trace in figure.figure['data']
        if trace['name'] == 'mpp_tracking' and 'customdata' in trace
    )
    hover = tracking['hovertemplate']
    for index, label in enumerate(['sample_id', 'start_time', 'end_time', 'type']):
        assert f'{label}: %{{customdata[{index + 1}]}}' in hover
    assert hover.endswith('<extra></extra>')
    assert list(tracking['customdata'][0]) == [
        '002_Tracking.txt',
        'A1',
        '2023-10-19 18:00:00',
        '2023-10-19 18:30:00',
        'mpp_tracking',
    ]

    # In one row, each kind lies at its own height, and a kind at the same height
    # in every row.
    heights = {(file['kind'], file['row']): file['y'] for file in drawn.values()}
    kinds_of_a1 = ('jv', 'dark_jv', 'mpp_tracking')
    assert len({heights[kind, 'A1'] for kind in kinds_of_a1}) == len(kinds_of_a1)
    assert heights['jv', 'B2'] - heights['jv', 'A1'] == pytest.approx(1)


def test_summary_timeline_draws_markers_over_lines_and_explains_them(
    staging_upload,
):
    figure = timeline(staging_upload)
    drawn = drawn_files(figure.figure)
    data = figure.figure['data']
    # NOMAD's new GUI shows no trace without data, nor its legend entry, so every
    # trace has data, without gaps.
    for trace in data:
        assert len(trace['x']) > 0
        assert None not in trace['x'] and None not in trace['y']

    # Each kind has its own opaque colour for its markers, with an outline, and
    # the same colour, translucent, for its files' lines.
    markers = [trace for trace in data if 'customdata' in trace]
    color_of = {}
    for trace in markers:
        assert channels(trace['marker']['color'])[3] == 1
        assert trace['marker']['opacity'] == 1
        assert trace['marker']['line']['width'] > 0
        assert (
            color_of.setdefault(trace['name'], trace['marker']['color'])
            == (trace['marker']['color'])
        )
    assert len(set(color_of.values())) == len(color_of)
    file_lines = [
        trace for trace in data if trace['mode'] == 'lines' and len(trace['x']) > 1
    ]
    assert file_lines
    for trace in file_lines:
        line = channels(trace['line']['color'])
        assert line[:3] == channels(color_of[trace['name']])[:3]
        assert line[3] < 1

    # A file starts with a circle and ends with a smaller triangle, wider than the
    # line; a file that ends when it starts is a circle.
    tracking_file = drawn['002_Tracking.txt']
    assert tracking_file['symbols'] == ['circle', 'triangle-up']
    circle_size, triangle_size = tracking_file['sizes']
    assert file_lines[0]['line']['width'] < triangle_size < circle_size
    assert drawn['002_JV.txt']['symbols'] == ['circle']
    # Circles are drawn over all triangles, and triangles over all lines.
    layers = [
        'circle'
        if 'customdata' in trace and trace['marker']['symbol'] == 'circle'
        else 'triangle'
        if 'customdata' in trace
        else 'line'
        for trace in data
        if trace in file_lines or 'customdata' in trace
    ]
    assert layers == sorted(layers, key=['line', 'triangle', 'circle'].index)

    # The legend lists the kinds, as lines that show and hide their files, and
    # explains the start and end markers, whose entries are never drawn: they lie
    # out of the fixed range of the rows.
    legend = [trace for trace in data if trace.get('showlegend', True)]
    assert [trace['name'] for trace in legend[:-2]] == ['jv', 'dark_jv', 'mpp_tracking']
    assert 'start' in legend[-2]['name'] and 'end' in legend[-1]['name']
    yaxis = figure.figure['layout']['yaxis']
    low, high = sorted(yaxis['range'])
    assert yaxis['autorange'] is False
    for trace in legend[-2:]:
        assert not low <= trace['y'][0] <= high
    # The legend lies above the plot, out of the side margins that NOMAD's GUI fixes.
    legend_layout = figure.figure['layout']['legend']
    assert legend_layout['orientation'] == 'h'
    assert legend_layout['y'] > 1
    assert figure.figure['layout']['showlegend'] is True
    # Hovering is switched on by the figure itself, not only by its template, which
    # NOMAD's new GUI replaces with one that switches hovering off.
    assert figure.figure['layout']['hovermode'] == 'closest'
    # Scrolling zooms in time, which the template would forbid, but not across rows.
    assert figure.figure['layout']['xaxis']['fixedrange'] is False
    assert yaxis['fixedrange'] is True
