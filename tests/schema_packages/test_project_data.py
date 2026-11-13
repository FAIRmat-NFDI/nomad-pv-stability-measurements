from datetime import datetime, timezone
from pathlib import Path

import openpyxl
import pytest
from structlog.testing import capture_logs

import nomad_pv_stability_measurements
from nomad_pv_stability_measurements.parsers.project_data_utils import (
    write_project_data_template,
)

UNITOV_JV = (
    '## Header ##\t\t\r\n'
    'Device\t{device}\t\r\n'
    'Test\tStability (JV)\t\r\n'
    'Date\t2023-10-19\t\r\n'
    'Time\t18:34:18\t\r\n'
)

PROJECT = {
    'proposal_number': 'RPV-261-00001-EF',
    'proposal': 'https://example.org/proposals/42',
    'title': 'Outdoor stability of nip perovskite cells',
    'funding_requested': False,
    'co_proposers': 'A. Rossi, B. Bianchi',
    'experiment_start': '2026-09-13',
}


def spreadsheet(tmp_path, project=None, files=(), samples=(), extra_headers=()):
    """A filled copy of the template in `tmp_path`: the `project` row, `files` rows
    and `samples` rows, given as dictionaries from header to value. `extra_headers`
    are added at the end of the sheet `samples`, as pasted columns are."""
    path = tmp_path / 'project_data.xlsx'
    write_project_data_template(str(path))
    workbook = openpyxl.load_workbook(path)

    def fill(sheet, rows):
        headers = [cell.value for cell in sheet[1]]
        for row in rows:
            sheet.append([row.get(header) for header in headers])

    samples_sheet = workbook['samples']
    for header in extra_headers:
        samples_sheet.cell(row=1, column=samples_sheet.max_column + 1, value=header)
    fill(workbook['project'], [project] if project else [])
    fill(workbook['files'], files)
    fill(samples_sheet, samples)
    workbook.save(path)
    return path


def process(upload, spreadsheet_path, files: dict[str, str]):
    """Processes an upload with the spreadsheet at `spreadsheet_path` and the text
    `files`: the files, then the project entry, which writes the sample entries,
    then those. Returns the project entry."""
    import json

    from nomad_pv_stability_measurements.schema_packages.schema_package import (
        ProjectData,
    )

    upload.source_dir.mkdir(parents=True, exist_ok=True)
    if spreadsheet_path is not None:
        (upload.source_dir / 'project_data.xlsx').write_bytes(
            spreadsheet_path.read_bytes()
        )
    upload.add(files)
    for path in files:
        upload.parse(path)
    # Without files, nothing has created the project entry yet.
    if not upload.context.raw_path_exists('project_data.archive.json'):
        with upload.context.raw_file('project_data.archive.json', 'w') as file:
            json.dump({'data': ProjectData().m_to_dict(with_root_def=True)}, file)
    project = upload.process_archive_file('project_data.archive.json').data
    for path in upload.processed:
        if path.startswith('samples/'):
            upload.process_archive_file(path)
    return project


def project_data(upload):
    """The project entry of `upload` as NOMAD stored it."""
    from nomad.utils import generate_entry_id

    entry_id = generate_entry_id(upload.upload_id, 'project_data.archive.json')
    return upload.context.load_archive(entry_id, upload.upload_id, None).data


def test_project_data_is_read_from_the_spreadsheet(staging_upload, tmp_path):
    path = spreadsheet(
        tmp_path,
        PROJECT,
        files=[
            {'files': 'UNITOV/*', 'provenance': 'measured'},
            {
                'files': 'HZB/simulation/*.csv',
                'stability_file_type': 'jv',
                'provenance': 'simulated',
                'datetime': '2026-01-05T10:00:00+01:00',
                'sample_id': ' S1 ',
            },
            {'files': '../outside/*', 'stability_file_type': 'jv'},
            {'files': 'UNITOV/*.txt', 'stability_file_type': 'JV curve'},
        ],
    )
    with capture_logs() as logs:
        process(staging_upload, path, {})
    project = project_data(staging_upload)

    assert project.proposal_number == 'RPV-261-00001-EF'
    assert project.title == 'Outdoor stability of nip perovskite cells'
    assert project.funding_requested is False
    assert project.co_proposers == ['A. Rossi', 'B. Bianchi']
    assert project.experiment_start == datetime(2026, 9, 13, tzinfo=timezone.utc)

    # The import reports the rows of the sheet `files` that cannot be used: the
    # pattern leaving the upload, and a kind that does not exist.
    errors = [
        (log['row'], log['column']) for log in logs if log['log_level'] == 'error'
    ]
    assert errors == [(4, 'files'), (5, 'stability_file_type')]


def save(upload, path: str, data) -> None:
    """Saves the archive file `path` with `data`, as the GUI does, and processes it."""
    import json

    with upload.context.raw_file(path, 'w') as file:
        json.dump({'data': data.m_to_dict(with_root_def=True)}, file)
    upload.process_archive_file(path)


def test_edits_to_the_project_data_stay_until_the_next_import(staging_upload, tmp_path):
    process(staging_upload, spreadsheet(tmp_path, PROJECT), {})
    project = project_data(staging_upload)

    project.title = 'Edited title'
    save(staging_upload, 'project_data.archive.json', project)
    assert project_data(staging_upload).title == 'Edited title'

    project.fill_archive_from_datafile = True
    save(staging_upload, 'project_data.archive.json', project)
    assert project_data(staging_upload).title == PROJECT['title']


def applied_standards(project) -> dict:
    """The applied standards of each sample series that has any, by sample, each as
    name, variant and the name of the referenced standard."""
    return {
        group.sample_identity.sample_id: [
            (each.name, each.variant, each.standard.name if each.standard else None)
            for each in group.applied_standards
        ]
        for group in project.sample_series
        if group.applied_standards
    }


def test_each_sample_gets_the_standards_of_its_row(staging_upload, tmp_path):
    samples = [
        {'sample_id': 'S1', 'standard': 'ISOS-L-2 (65 °C, MPP), ISOS-L-1'},
        {'sample_id': 'S2', 'standard': 'ISOS-X-9'},
        {'sample_id': 'S3'},
    ]
    with capture_logs() as logs:
        process(staging_upload, spreadsheet(tmp_path, PROJECT, samples=samples), {})

    # Several standards in their order, a comma in parentheses not separating; a
    # sample without files has its group for its standards; a standard that no
    # catalogue holds keeps its name, with a warning.
    assert applied_standards(project_data(staging_upload)) == {
        'S1': [
            ('ISOS-L-2', '65 °C, MPP', 'ISOS-L-2'),
            ('ISOS-L-1', None, 'ISOS-L-1'),
        ],
        'S2': [('ISOS-X-9', None, None)],
    }
    assert [log['standard'] for log in logs if 'standard' in log] == ['ISOS-X-9']


def test_files_stored_or_described_as_measurement_kind_keep_their_type(
    staging_upload, tmp_path
):
    """`stability_file_type` was called `measurement_kind`."""
    from nomad_pv_stability_measurements.schema_packages.schema_package import (
        StabilityActivity,
    )

    assert StabilityActivity.m_from_dict(
        {'measurement_kind': 'jv'}
    ).stability_file_type == ('jv')

    path = spreadsheet(
        tmp_path,
        PROJECT,
        files=[{'files': 'env/chamber.csv', 'stability_file_type': 'environment_log'}],
    )
    workbook = openpyxl.load_workbook(path)
    for cell in workbook['files'][1]:
        if cell.value == 'stability_file_type':
            cell.value = 'measurement_kind'
    workbook.save(path)
    with capture_logs() as logs:
        process(staging_upload, path, {'env/chamber.csv': 'time,T\n'})

    assert [log for log in logs if log['log_level'] == 'error'] == []
    # A spreadsheet of before 2026-11, with its names of column and file type.
    assert [each.name for each in project_data(staging_upload).general_groups] == [
        'Setup logs'
    ]


def test_files_that_belong_to_no_sample_form_general_groups(staging_upload, tmp_path):
    files = [
        {'files': 'UNITOV/*', 'provenance': 'measured'},
        # A general type ignores the sample, also for a simulation.
        {'files': 'env/chamber.csv', 'stability_file_type': 'setup_log'},
        {
            'files': 'env/sim.csv',
            'stability_file_type': 'setup_log',
            'provenance': 'simulated',
            'sample_id': 'S1',
        },
        {'files': 'env/weather.csv', 'stability_file_type': 'weather_information'},
        {'files': 'notes.txt', 'stability_file_type': 'metadata'},
        # Reference data without sample, such as a calibration, are general too.
        {
            'files': 'calibration.csv',
            'stability_file_type': 'jv',
            'provenance': 'reference',
        },
        # A file about a sample that names none is of an unknown sample.
        {'files': 'lost.csv', 'stability_file_type': 'jv'},
    ]
    process(
        staging_upload,
        spreadsheet(tmp_path, PROJECT, files=files),
        {
            'UNITOV/run_1/001_JV.txt': UNITOV_JV.format(device='S1'),
            'env/chamber.csv': 'time,T\n',
            'env/sim.csv': 'time,T\n',
            'env/weather.csv': 'time,G\n',
            'notes.txt': 'notes',
            'calibration.csv': 'V,J\n',
            'lost.csv': 'V,J\n',
        },
    )
    project = project_data(staging_upload)

    assert [
        (
            each.sample_identity.sample_id,
            [activity.file.path for activity in each.activities],
        )
        for each in project.sample_series
    ] == [('S1', ['UNITOV/run_1/001_JV.txt'])]
    assert [
        (each.name, [activity.file.path for activity in each.activities])
        for each in project.general_groups
    ] == [
        ('Setup logs', ['env/chamber.csv', 'env/sim.csv']),
        ('Weather information', ['env/weather.csv']),
        ('General', ['calibration.csv', 'notes.txt']),
        ('Unknown', ['lost.csv']),
    ]


def test_applied_standards_edited_by_hand_stay(staging_upload, tmp_path):
    samples = [{'sample_id': 'S1', 'standard': 'ISOS-L-1'}]
    process(staging_upload, spreadsheet(tmp_path, PROJECT, samples=samples), {})
    project = project_data(staging_upload)

    project.sample_series[0].applied_standards[0].notes = 'J–V scans every 12 h.'
    save(staging_upload, 'project_data.archive.json', project)
    project = project_data(staging_upload)
    assert project.sample_series[0].applied_standards[0].notes == (
        'J–V scans every 12 h.'
    )

    # An import keeps an applied standard that is written the same.
    project.fill_archive_from_datafile = True
    save(staging_upload, 'project_data.archive.json', project)
    [applied] = project_data(staging_upload).sample_series[0].applied_standards
    assert (applied.name, applied.notes) == ('ISOS-L-1', 'J–V scans every 12 h.')


def test_an_existing_project_entry_is_kept(staging_upload):
    staging_upload.add(
        {
            'project_data.archive.json': '{"data": {}}',
            'UNITOV/run_1/001_JV.txt': UNITOV_JV.format(device='S1'),
        }
    )
    staging_upload.parse('UNITOV/run_1/001_JV.txt')

    # An existing project entry, which may hold edits, is not overwritten.
    with staging_upload.context.raw_file('project_data.archive.json', 'r') as file:
        assert file.read() == '{"data": {}}'


def test_a_spreadsheet_in_a_folder_is_not_project_data(staging_upload, tmp_path):
    path = spreadsheet(tmp_path, PROJECT)
    (staging_upload.source_dir / 'results').mkdir(parents=True)
    (staging_upload.source_dir / 'results' / 'project_data.xlsx').write_bytes(
        path.read_bytes()
    )
    project = process(staging_upload, None, {})

    assert (project.data_file, project.title) == (None, None)


ENCAPSULATED = {
    'sample_id': 'S1',
    'architecture': 'nip',
    'number_of_junctions': 1,
    'substrate': 'Glass',
    'active_area [cm^2]': 0.1,
    'dead_area [cm^2]': 0.02,
    'encapsulation_method': 'Sheet-to-Sheet (S2S)',
    'sides_encapsulated': 'Both Sides',
    'Layer1: layer_type': 'Electron Transport Layer',
    'Layer1: layer_material_name': 'SnO2',
    'Layer1: layer_thickness [nm]': 30,
    # Layer 2 is left empty and skipped.
    'Layer3: layer_type': 'Absorber Layer',
    'Layer3: layer_material_name': 'MAPbI3',
    'Layer3: layer_thickness [nm]': 500,
    # A pasted block after the template's eight, in micrometres.
    'Layer9: layer_type': 'Back Contact',
    'Layer9: layer_material_name': 'Au',
    'Layer9: layer_thickness [µm]': 0.08,
}

PASTED_BLOCK = (
    'Layer9: layer_type',
    'Layer9: layer_material_name',
    'Layer9: layer_thickness [µm]',
)


def test_samples_become_entries_with_their_layer_stack(staging_upload, tmp_path):
    path = spreadsheet(
        tmp_path,
        PROJECT,
        samples=[ENCAPSULATED, {'sample_id': ' S2 ', 'is_module': True}],
        extra_headers=PASTED_BLOCK,
    )
    process(staging_upload, path, {})
    samples = {
        sample.sample_id: sample.entry.m_resolved()
        for sample in project_data(staging_upload).samples
    }

    assert sorted(samples) == ['S1', 'S2']
    s1 = samples['S1']
    assert (s1.architecture, s1.number_of_junctions) == ('nip', 1)
    substrate = s1.substrate.m_resolved()
    assert substrate.active_area.to('cm**2').magnitude == pytest.approx(0.1)
    # Derived from active and dead area.
    assert substrate.aperture_area.to('cm**2').magnitude == pytest.approx(0.12)
    layers = [
        (layer.layer_material_name, layer.layer_thickness.to('nm').magnitude)
        for layer in substrate.substrate_properties
    ]
    assert layers == [('SnO2', 30), ('MAPbI3', 500), ('Au', pytest.approx(80))]

    s2 = samples['S2']
    assert s2.module_configuration.is_module is True
    # Only the encapsulated device has an encapsulation entry.
    assert staging_upload.context.raw_path_exists(
        'samples/S1_encapsulation.archive.json'
    )
    assert not staging_upload.context.raw_path_exists(
        'samples/S2_encapsulation.archive.json'
    )


def test_sample_lab_ids_are_unique_by_the_proposal_number(staging_upload, tmp_path):
    process(staging_upload, spreadsheet(tmp_path, PROJECT, samples=[ENCAPSULATED]), {})
    [identity] = project_data(staging_upload).samples
    sample = identity.entry.m_resolved()

    # The sample keeps the identifier its files use; the lab ID adds the proposal.
    assert (sample.sample_id, sample.lab_id) == ('S1', 'RPV-261-00001-EF:S1')
    assert sample.substrate.m_resolved().lab_id == 'RPV-261-00001-EF:S1-substrate'


def test_without_proposal_number_the_upload_makes_the_lab_ids_unique(
    staging_upload, tmp_path
):
    project = {**PROJECT, 'proposal_number': None}
    process(staging_upload, spreadsheet(tmp_path, project, samples=[ENCAPSULATED]), {})
    [identity] = project_data(staging_upload).samples

    lab_id = identity.entry.m_resolved().lab_id
    assert lab_id == f'{staging_upload.upload_id}:S1'


def test_a_changed_proposal_number_is_reported(staging_upload, tmp_path):
    process(staging_upload, spreadsheet(tmp_path, PROJECT, samples=[ENCAPSULATED]), {})
    project = project_data(staging_upload)
    project.fill_archive_from_datafile = True
    changed = {**PROJECT, 'proposal_number': 'RPV-261-00002-EF'}
    with staging_upload.context.raw_file('project_data.xlsx', 'wb') as file:
        file.write(spreadsheet(tmp_path, changed, samples=[ENCAPSULATED]).read_bytes())
    with capture_logs() as logs:
        save(staging_upload, 'project_data.archive.json', project)

    assert [log['previous'] for log in logs if 'previous' in log] == [
        'RPV-261-00001-EF'
    ]


def test_unreadable_sample_rows_are_reported(staging_upload, tmp_path):
    path = spreadsheet(
        tmp_path,
        PROJECT,
        samples=[
            {'sample_id': 'S1', 'Layer10: layer_type': 'Absorber Layer'},
            {'sample_id': 'S2', 'number_of_junctions': 1.5},
            {'sample_id': 'S3'},
            {'sample_id': 'S3'},
        ],
        # A block of which only one column was pasted.
        extra_headers=('Layer10: layer_type',),
    )
    with capture_logs() as logs:
        process(staging_upload, path, {})

    # The incomplete block is left out, the other rows of S1 are read.
    samples = project_data(staging_upload).samples
    assert [sample.sample_id for sample in samples] == ['S1', 'S3']
    errors = [
        (log['row'], log['column']) for log in logs if log['log_level'] == 'error'
    ]
    assert errors == [(1, 'Layer10'), (3, 'number_of_junctions'), (5, 'sample_id')]


def test_file_entries_take_the_project_data_first(staging_upload, tmp_path):
    path = spreadsheet(
        tmp_path,
        PROJECT,
        files=[
            {'files': 'UNITOV/*', 'provenance': 'reference'},
            {'files': 'UNITOV/run_2/*', 'provenance': 'derived'},
            {
                'files': 'HZB/simulation/*.csv',
                'stability_file_type': 'jv',
                'provenance': 'simulated',
                'datetime': '2026-01-05T10:00:00+01:00',
                'sample_id': 'S1',
                'description': 'Drift-diffusion simulation of the fresh cell.',
            },
        ],
        samples=[{'sample_id': 'S1'}, {'sample_id': 's2'}],
    )
    project = process(
        staging_upload,
        path,
        {
            'UNITOV/run_1/001_JV.txt': UNITOV_JV.format(device=' S1 '),
            'UNITOV/run_2/001_JV.txt': UNITOV_JV.format(device='S2'),
            'HZB/simulation/jv.csv': 'V,J\n0,1\n',
        },
    )
    entries = {
        activity.file.path: activity.m_resolved()
        for group in [*project.sample_series, *project.general_groups]
        for activity in group.activities
    }

    measured = entries['UNITOV/run_1/001_JV.txt']
    # Matching gives kind, start and sample; the project data the provenance.
    assert (measured.stability_file_type, measured.provenance) == ('jv', 'reference')
    assert measured.datetime == datetime(2023, 10, 19, 16, 34, 18, tzinfo=timezone.utc)
    assert measured.sample_identity.entry.m_resolved().sample_id == 'S1'
    # Unique in NOMAD: the proposal number and the path, which runs do not share.
    assert measured.lab_id == 'RPV-261-00001-EF:UNITOV/run_1/001_JV.txt'
    # A later row overrides an earlier one; the identifier differs in case.
    other = entries['UNITOV/run_2/001_JV.txt']
    identity = other.sample_identity
    assert (other.provenance, identity.sample_id, identity.entry) == (
        'derived',
        'S2',
        None,
    )
    # A file that no reading code recognizes is described completely.
    simulated = entries['HZB/simulation/jv.csv']
    assert (simulated.stability_file_type, simulated.provenance) == ('jv', 'simulated')
    assert simulated.datetime_end == simulated.datetime
    assert simulated.description == 'Drift-diffusion simulation of the fresh cell.'

    assert project.proposal == PROJECT['proposal']
    # Neither the spreadsheet nor the project entry or samples are files of it.
    assert sorted(entries) == [
        'HZB/simulation/jv.csv',
        'UNITOV/run_1/001_JV.txt',
        'UNITOV/run_2/001_JV.txt',
    ]


def test_the_template_reads_without_errors(staging_upload, tmp_path):
    with capture_logs() as logs:
        process(staging_upload, spreadsheet(tmp_path), {})

    project = project_data(staging_upload)
    assert (project.title, project.samples) == (None, [])
    assert [log for log in logs if log['log_level'] in ('warning', 'error')] == []


EXAMPLE_UPLOADS = (
    Path(nomad_pv_stability_measurements.__file__).parent / 'example_uploads'
)


def headers(path) -> dict[str, list]:
    workbook = openpyxl.load_workbook(path)
    return {
        sheet: [cell.value for cell in workbook[sheet][1]]
        for sheet in workbook.sheetnames
    }


def test_the_shipped_template_has_the_columns_of_the_schema(tmp_path):
    write_project_data_template(str(tmp_path / 'template.xlsx'))

    assert headers(EXAMPLE_UPLOADS / 'project_data_template.xlsx') == headers(
        tmp_path / 'template.xlsx'
    )


def test_the_example_upload_is_processed_without_problems(staging_upload):
    folder = EXAMPLE_UPLOADS / 'stability_project'
    files = {
        path.relative_to(folder).as_posix(): path.read_text()
        for path in folder.rglob('*')
        if path.is_file() and path.suffix != '.xlsx'
    }
    with capture_logs() as logs:
        project = process(staging_upload, folder / 'project_data.xlsx', files)

    assert [log for log in logs if log['log_level'] in ('warning', 'error')] == []
    entries = {
        activity.file.path: activity.m_resolved()
        for group in [*project.sample_series, *project.general_groups]
        for activity in group.activities
    }
    assert sorted(entries) == sorted(files)
    simulated = entries['HZB/simulation/jv_simulated.csv']
    assert (simulated.stability_file_type, simulated.provenance) == ('jv', 'simulated')
    # A simulation over model time has no times, only the length it covers.
    model = entries['simulation/degradation_model.csv']
    assert (model.datetime, model.duration.to('hour').magnitude) == (None, 1000)
    # Every UNITOV file is linked to the sample entry of its device.
    for path, entry in entries.items():
        if path.startswith('UNITOV/'):
            identity = entry.sample_identity
            assert identity.entry.m_resolved().sample_id == identity.sample_id
    assert applied_standards(project) == {
        'RPV-S1': [('ISOS-L-1', 'MPP', 'ISOS-L-1')],
        'RPV-S2': [('ISOS-L-1', 'MPP', 'ISOS-L-1')],
    }
    assert [each.name for each in project.general_groups] == [
        'Setup logs',
        'Weather information',
        'General',
    ]
    # The series of a sample references its sample entry.
    assert [
        each.sample_identity.entry.m_resolved().sample_id
        for each in project.sample_series
    ] == ['RPV-S1', 'RPV-S2']
