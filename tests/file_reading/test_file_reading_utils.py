import pytest

from nomad_pv_stability_measurements.file_reading.file_reading_utils import (
    FORMAT_BY_EXTENSION,
    file_format_from_path,
    is_in_institution_folder,
)
from nomad_pv_stability_measurements.schema_packages.schema_package import (
    StabilityFile,
)


@pytest.mark.parametrize(
    'path, file_format',
    [
        ('sample_A/jv_scan.csv', 'csv'),
        ('sample_A/JV_SCAN.CSV', 'csv'),
        ('mpp/run.2026-01-05.dat', 'dat'),
        ('settings.yml', 'yaml'),
        ('raw/data.h5', 'hdf5'),
        ('raw/data.nxs', 'nexus'),
        ('images/cell.jpeg', 'jpg'),
        ('images/cell.tif', 'tiff'),
        ('notes.md', 'other'),
        ('README', 'unknown'),
    ],
)
def test_file_format_from_path(path, file_format):
    assert file_format_from_path(path) == file_format


@pytest.mark.parametrize(
    'path, belongs',
    [
        ('HZB/sample_A/jv.csv', True),
        ('project/hzb/jv.csv', True),
        ('HZB_old/jv.csv', False),
        ('sample_A/HZB', False),
        ('jv.csv', False),
    ],
)
def test_is_in_institution_folder(path, belongs):
    assert is_in_institution_folder(path, 'HZB') == belongs


def test_every_recognized_extension_is_a_valid_file_format():
    for extension in FORMAT_BY_EXTENSION:
        StabilityFile(file_format=file_format_from_path(f'file.{extension}'))
