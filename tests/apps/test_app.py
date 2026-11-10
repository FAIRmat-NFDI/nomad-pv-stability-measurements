def test_importing_app():
    # this will raise an exception if pydantic model validation fails for the app
    from nomad_pv_stability_measurements.apps import app_entry_point

    assert app_entry_point.app.label == 'NewApp'


def strings(value) -> list[str]:
    """All strings within `value`, a structure of dicts, lists and values."""
    if isinstance(value, str):
        return [value]
    if isinstance(value, dict):
        value = list(value.values())
    if isinstance(value, list | tuple):
        return [string for item in value for string in strings(item)]
    return []


def test_stability_files_app_uses_quantities_of_the_file_entries():
    from nomad_pv_stability_measurements.apps import stability_files_app_entry_point
    from nomad_pv_stability_measurements.apps.stability_files import STABILITY_FILE
    from nomad_pv_stability_measurements.schema_packages.schema_package import (
        StabilityFile,
    )

    app = stability_files_app_entry_point.app
    # Every search quantity of the file entries that the app shows or filters by.
    used = {
        value.split('#')[0].removeprefix('data.')
        for value in strings(app.model_dump())
        if value.endswith(f'#{STABILITY_FILE}') and '*' not in value
    }
    assert {'sample_id', 'measurement_kind', 'start_time', 'duration'} <= used
    assert used <= set(StabilityFile.m_def.all_quantities)
    assert app.filters_locked == {
        'section_defs.definition_qualified_name': [STABILITY_FILE]
    }
