def strings(value) -> list[str]:
    """All strings within `value`, a structure of dicts, lists and values."""
    if isinstance(value, str):
        return [value]
    if isinstance(value, dict):
        value = list(value.values())
    if isinstance(value, list | tuple):
        return [string for item in value for string in strings(item)]
    return []


def is_quantity(section_def, path: str) -> bool:
    """Whether `path`, e.g. `sample_identity.sample_id`, is a quantity of the section
    `section_def` or of its sub-sections."""
    name, _, rest = path.partition('.')
    if not rest:
        return name in section_def.all_quantities
    sub_section = section_def.all_sub_sections.get(name)
    return sub_section is not None and is_quantity(sub_section.sub_section, rest)


def test_stability_files_app_uses_quantities_of_the_file_entries():
    from nomad_pv_stability_measurements.apps import stability_files_app_entry_point
    from nomad_pv_stability_measurements.apps.stability_files import (
        STABILITY_ACTIVITY,
    )
    from nomad_pv_stability_measurements.schema_packages.schema_package import (
        StabilityActivity,
    )

    app = stability_files_app_entry_point.app
    # Every search quantity of the file entries that the app shows or filters by.
    used = {
        value.split('#')[0].removeprefix('data.')
        for value in strings(app.model_dump())
        if value.endswith(f'#{STABILITY_ACTIVITY}') and '*' not in value
    }
    assert {
        'sample_identity.sample_id',
        'stability_file_type',
        'datetime',
        'duration',
        'file.path',
    } <= used
    assert all(is_quantity(StabilityActivity.m_def, path) for path in used)
    assert app.filters_locked == {
        'section_defs.definition_qualified_name': [STABILITY_ACTIVITY]
    }
