from nomad.config.models.plugins import ExampleUploadEntryPoint

stability_example_upload_entry_point = ExampleUploadEntryPoint(
    title='PV stability project',
    category='Experiment',
    description="""
    A small stability project: the spreadsheet `project_data.xlsx` with a proposal,
    two samples with their standard and descriptions of the files; measured files of
    UNITOV; simulations, of a J-V curve and of a degradation series over model time;
    and logs of the climate chamber and a weather station. Processing makes the
    project entry with its file series and timeline, the sample entries and one entry
    per file. All data are made up.
    """,
    resources=['example_uploads/stability_project/*'],
)
