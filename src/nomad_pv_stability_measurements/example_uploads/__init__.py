from nomad.config.models.plugins import ExampleUploadEntryPoint

example_upload_entry_point = ExampleUploadEntryPoint(
    title='New Example Upload',
    category='Examples',
    description='Description of this example upload.',
    path='example_uploads/getting_started',
)

stability_example_upload_entry_point = ExampleUploadEntryPoint(
    title='PV stability project',
    category='Experiment',
    description="""
    A small stability project: the spreadsheet `project_data.xlsx` with a proposal,
    two samples and descriptions of the files, measurement files of UNITOV, and a
    simulated J-V curve that no reading code recognizes. Processing makes the
    project entry with its timeline, the sample entries and one entry per file.
    The measurement files are made up.
    """,
    resources=['example_uploads/stability_project/*'],
)
