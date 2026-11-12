from nomad.config.models.plugins import AppEntryPoint
from nomad.config.models.ui import App, Column, Columns, FilterMenu, FilterMenus

from nomad_pv_stability_measurements.apps.stability_files import stability_files_app

app_entry_point = AppEntryPoint(
    name='NewApp',
    description='New app entry point configuration.',
    app=App(
        label='NewApp',
        path='app',
        category='simulation',
        columns=Columns(
            selected=['entry_id'],
            options={
                'entry_id': Column(),
            },
        ),
        filter_menus=FilterMenus(
            options={
                'material': FilterMenu(label='Material'),
            }
        ),
    ),
)

#: A search app over the files of all stability uploads, next to the timeline that
#: each upload's project entry shows.
stability_files_app_entry_point = AppEntryPoint(
    name='Stability files',
    description='Search and plot the files of stability measurement uploads.',
    app=stability_files_app,
)
