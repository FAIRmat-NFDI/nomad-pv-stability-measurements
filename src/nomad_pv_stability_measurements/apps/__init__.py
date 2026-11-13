from nomad.config.models.plugins import AppEntryPoint

from nomad_pv_stability_measurements.apps.stability_files import stability_files_app

#: A search app over the files of all stability uploads, next to the timeline that
#: each upload's project entry shows.
stability_files_app_entry_point = AppEntryPoint(
    name='Stability files',
    description='Search and plot the files of stability uploads.',
    app=stability_files_app,
)
