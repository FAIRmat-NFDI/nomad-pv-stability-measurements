"""The template for recognizing the files of one institution.

To add your institution:

Adapt the `match_<kind>` functions below to your files, delete those you do not
need, and add one for each further kind you upload.

Available measurement kinds are:
    'jv',
    'dark_jv',
    'mpp_tracking',
    'stability_series',
    'eqe',
    'pl',
    'el',
    'impedance',
    'uv_vis',
    'image',
    'environment_log',
    'metadata',
    'other',
    'unknown',

Do not forget to store your files in a folder named after your institution, for example
HZB/folder1/jv1.csv. Your functions will be called only on files in this folder structure.
"""

from nomad_pv_stability_measurements.file_reading.file_reading_utils import (
    file_format_from_path,
)

#: Your institution's short name, as in the module's name and your upload folder.
INSTITUTION = 'TEMPLATE'


def match_jv(path: str, content: str) -> bool:
    """A current–voltage (J–V) sweep.

    Example: recognized by its file name, such as `sample_A/JV_001.csv`."""
    file_name = path.rsplit('/', 1)[-1].lower()
    return file_name.startswith('jv') and file_format_from_path(path) == 'csv'


def match_mpp_tracking(path: str, content: str) -> bool:
    """Maximum power point tracking.

    Example: recognized by the header line that the measurement software writes,
    such as `# MPP tracking`."""
    first_line = content.split('\n', 1)[0]
    return first_line.startswith('# MPP tracking')


def match_image(path: str, content: str) -> bool:
    """A photo or other image of a sample.

    Example: recognized by its file format alone."""
    return file_format_from_path(path) in ('png', 'jpg', 'tiff', 'bmp')
