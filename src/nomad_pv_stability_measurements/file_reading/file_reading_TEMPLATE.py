"""The template for recognizing the files of one institution.

To add your institution:

Adapt the `match_<kind>` functions below to your files, delete those you do not
need, and add one for each further kind you upload.

Each function gets the file's path within the upload, the beginning of its content
as text, and the end of its content as text (`tail`), for example to find the time of
the last data row. `HEAD_SIZE` and `TAIL_SIZE` below set how many bytes of each;
with `TAIL_SIZE = 0`, `tail` is empty. For a short file, the two overlap. If the file
is not of its kind, it must return `False`. Otherwise it must return five values, in
this order:

    time_stamp        when the measurement started, a `datetime` with its time zone
    end_time          when the measurement finished, a `datetime` with its time zone;
                      if `None`, the end is taken to be the start
    sample_id         the identifier of the measured sample, a text
    sample_reference  a URI of the sample, a text
    data              a dict with anything else that is specific to the kind of measurement

Use `None` for each value you do not know, and an empty dict `{}` for `data`.

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
    'pl_image',
    'el_image',
    'environment_log',
    'metadata',
    'other',
    'unknown',

Do not forget to store your files in a folder named after your institution, for example
HZB/folder1/jv1.csv. Your functions will be called only on files in this folder structure,
and on files in no institution's folder that someone with an address of your
`EMAIL_DOMAINS` uploads.
"""

import re
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

from nomad_pv_stability_measurements.file_reading.file_reading_utils import (
    file_format_from_path,
)

#: Your institution's short name, as in the module's name and your upload folder.
INSTITUTION = 'TEMPLATE'

#: Email domains of your institution, such as 'uni.edu', with their subdomains. A file
#: in no institution folder belongs to the institution of its uploader's email domain.
EMAIL_DOMAINS: tuple[str, ...] = ()

#: The time zone of your measurement computers, for times written without one.
LOCAL_TIME_ZONE = ZoneInfo('Europe/Berlin')

#: How many bytes from the beginning of a file your functions get as `content`.
HEAD_SIZE = 4096

#: How many bytes from the end of a file your functions get as `tail`; 0 for none.
TAIL_SIZE = 4096


def match_jv(path: str, content: str, tail: str) -> tuple | bool:
    """A current–voltage (J–V) sweep.

    Example: recognized by its file name, which also gives the start time, such as
    `TEMPLATE/sample_A/JV_20260105_100000.csv`. The sample is named by the folder
    the file is in, and the file's columns are separated by commas."""
    folders_and_name = path.split('/')
    file_name = folders_and_name[-1]
    name_match = re.fullmatch(r'JV_(\d{8}_\d{6})\.csv', file_name, re.IGNORECASE)
    if name_match is None:
        return False

    start = datetime.strptime(name_match.group(1), '%Y%m%d_%H%M%S')
    time_stamp = start.replace(tzinfo=LOCAL_TIME_ZONE)
    sample_id = folders_and_name[-2]
    sample_reference = f'https://example.org/samples/{sample_id}'
    data = {'separator': ','}
    # A sweep takes seconds; its end is not written down.
    end_time = None
    return time_stamp, end_time, sample_id, sample_reference, data


def match_mpp_tracking(path: str, content: str, tail: str) -> tuple | bool:
    """Maximum power point tracking.

    Example: recognized by the header that the measurement software writes, which
    gives the start time with its time zone, the sample and its URI. The columns of
    the data are separated by tabs, the first one giving the seconds since the start,
    so the last row gives the end of the measurement.

        # MPP tracking
        # Start: 2026-01-05T10:00:00+01:00
        # Sample: sample_A
        # Sample URI: https://example.org/samples/sample_A
        0.0\t0.81\t19.2
        60.0\t0.80\t19.1
    """
    lines = content.split('\n')
    if not lines[0].startswith('# MPP tracking'):
        return False

    header = {}
    for line in lines[1:]:
        if line.startswith('# ') and ':' in line:
            key, value = line[2:].split(':', 1)
            header[key.strip()] = value.strip()

    time_stamp = datetime.fromisoformat(header['Start'])
    sample_id = header['Sample']
    sample_reference = header['Sample URI']
    last_row = tail.strip().split('\n')[-1]
    end_time = time_stamp + timedelta(seconds=float(last_row.split('\t')[0]))
    data = {'separator': '\t'}
    return time_stamp, end_time, sample_id, sample_reference, data


def match_image(path: str, content: str, tail: str) -> tuple | bool:
    """A photo or other image of a sample.

    Example: recognized by its file format and a file name that gives the sample and
    the time the image was taken, such as
    `TEMPLATE/images/sample_A_20260105_100000.png`. An image needs nothing more for
    reading it later, so `data` stays empty."""
    if file_format_from_path(path) not in ('png', 'jpg', 'tiff', 'bmp'):
        return False
    file_name = path.rsplit('/', maxsplit=1)[-1]
    name_match = re.fullmatch(r'(.+)_(\d{8}_\d{6})\.\w+', file_name)
    if name_match is None:
        return False

    start = datetime.strptime(name_match.group(2), '%Y%m%d_%H%M%S')
    time_stamp = start.replace(tzinfo=LOCAL_TIME_ZONE)
    sample_id = name_match.group(1)
    sample_reference = f'https://example.org/samples/{sample_id}'
    end_time = None
    data = {}
    return time_stamp, end_time, sample_id, sample_reference, data
