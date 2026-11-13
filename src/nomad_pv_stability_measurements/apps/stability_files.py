"""A search app over the files of all stability uploads, one entry per file."""

from nomad.config.models.ui import (
    App,
    Axis,
    Column,
    Dashboard,
    Layout,
    Menu,
    MenuItemHistogram,
    MenuItemTerms,
    SearchQuantities,
    WidgetHistogram,
    WidgetTerms,
)

#: The section whose entries the app lists: one per file of a stability upload.
STABILITY_ACTIVITY = (
    'nomad_pv_stability_measurements.schema_packages.schema_package.StabilityActivity'
)


#: The full width of the dashboard for each screen size, in grid columns.
WIDTHS = {'xxl': 36, 'xl': 30, 'lg': 24, 'md': 18, 'sm': 12}


def quantity(name: str) -> str:
    """The search quantity of the `StabilityActivity` quantity at the path `name`,
    e.g. `datetime`, `file.path` or `sample_identity.sample_id`."""
    return f'data.{name}#{STABILITY_ACTIVITY}'


stability_files_app = App(
    label='Stability files',
    path='stabilityfiles',
    category='Experiment',
    description='Search and plot the files of stability uploads.',
    readme="""
    Every file of a stability upload, measured, simulated or from elsewhere, with its
    sample, stability file type and the period its data cover. Files appear here as
    soon as their upload is processed. Narrow
    the files down with the menu on the left, for example to one upload or one
    sample, or by selecting a range in the histograms; open a file's entry from the
    table.
    """,
    filters_locked={'section_defs.definition_qualified_name': [STABILITY_ACTIVITY]},
    search_quantities=SearchQuantities(include=[f'*#{STABILITY_ACTIVITY}']),
    columns=[
        Column(quantity=quantity('file.path'), label='File', selected=True),
        Column(
            quantity=quantity('sample_identity.sample_id'),
            label='Sample',
            selected=True,
        ),
        Column(
            quantity=quantity('stability_file_type'),
            label='File type',
            selected=True,
        ),
        Column(quantity=quantity('datetime'), label='Start', selected=True),
        Column(
            quantity=quantity('duration'),
            label='Duration',
            unit='hour',
            format={'decimals': 2, 'mode': 'standard'},
            selected=True,
        ),
        Column(quantity=quantity('institution'), label='Institution', selected=True),
        Column(quantity='upload_name', label='Upload', selected=True),
        Column(quantity=quantity('datetime_end'), label='End'),
        Column(quantity=quantity('file.file_format'), label='Format'),
        Column(quantity=quantity('provenance'), label='Provenance'),
        Column(
            quantity=quantity('sample_identity.external_reference'),
            label='Sample reference',
        ),
        Column(quantity='upload_id'),
        Column(quantity='upload_create_time', label='Upload time'),
        Column(quantity='authors'),
    ],
    menu=Menu(
        title='Stability files',
        items=[
            MenuItemTerms(search_quantity='upload_name', title='Upload'),
            MenuItemTerms(
                search_quantity=quantity('stability_file_type'),
                title='Stability file type',
            ),
            MenuItemTerms(search_quantity=quantity('institution'), title='Institution'),
            MenuItemTerms(search_quantity=quantity('provenance'), title='Provenance'),
            MenuItemHistogram(x={'search_quantity': quantity('datetime')}),
            MenuItemHistogram(x={'search_quantity': quantity('duration')}),
        ],
    ),
    dashboard=Dashboard(
        widgets=[
            WidgetHistogram(
                title='Files over time',
                x=Axis(search_quantity=quantity('datetime'), title='Start'),
                n_bins=100,
                autorange=True,
                show_input=False,
                layout={
                    size: Layout(x=0, y=0, w=width, h=8, minW=8, minH=4)
                    for size, width in WIDTHS.items()
                },
            ),
            WidgetHistogram(
                title='Periods covered by the files',
                x=Axis(
                    search_quantity=quantity('duration'), title='Duration', unit='hour'
                ),
                n_bins=50,
                autorange=True,
                show_input=False,
                # The left half of the row below the files over time.
                layout={
                    size: Layout(x=0, y=8, w=width // 2, h=8, minW=6, minH=4)
                    for size, width in WIDTHS.items()
                },
            ),
            WidgetTerms(
                title='Files per sample',
                search_quantity=quantity('sample_identity.sample_id'),
                scale='linear',
                show_input=True,
                # The right half of the row, next to the durations.
                layout={
                    size: Layout(
                        x=width // 2, y=8, w=width - width // 2, h=8, minW=4, minH=4
                    )
                    for size, width in WIDTHS.items()
                },
            ),
        ]
    ),
)
