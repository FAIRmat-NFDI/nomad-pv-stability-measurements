"""Recognizing the files of UNITOV (University of Rome Tor Vergata).

UNITOV's stations write tab-separated text files that begin with `## Header ##`. The
header names the measurement in a line `Test<TAB><name>`:

    Stability (JV)          one J–V sweep during a stability test
    Stability (Tracking)    the series recorded while the load is held or tracked;
                            its `Algorithm` line says how: `MPPT` or `Fixed Voltage`
    Stability (Parameters)  the figures of merit of every J–V sweep over the test
    Dark JV                 a J–V sweep in the dark
    IPCE                    the external quantum efficiency

The header also gives the measured sample in `Device`, and the start of the
measurement in `Date` (`2023-10-19`) and `Time` (`18:34:18`). These times are the
local time of the stations in Rome.

The two series, `Stability (Tracking)` and `Stability (Parameters)`, have one row per
sample after the header, the first column `Time (Hours)` counting from the start. The
last row's time gives the end of the measurement. The other files have no end time.

Other files, such as the PDF plots exported next to Dark JV and IPCE measurements,
are of kind `unknown`.
"""

from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

from nomad_ready_pv.file_reading.file_reading_utils import (
    read_head,
    read_tail,
)

INSTITUTION = 'UNITOV'

#: Email domains of the University of Rome Tor Vergata, with their subdomains.
EMAIL_DOMAINS = ('uniroma2.it',)

#: Bytes read from the beginning: the header, whose `Algorithm` line
#: lies up to 556 bytes in.
HEAD_SIZE = 4096

#: Bytes read from the end of a series: enough for the last data row of a series.
TAIL_SIZE = 4096

#: Time zone of the measurement computers, for times written without one.
LOCAL_TIME_ZONE = ZoneInfo('Europe/Rome')


def _match(
    path: str,
    test: str,
    mppt: bool | None = None,
    series: bool = False,
) -> tuple | bool:
    """What every `match_<kind>` function returns: `False` unless the file at `path`
    is a UNITOV text file whose `Test` line is `test`, otherwise its start and end
    time, method and sample. Every UNITOV file is measured at a station.

    `mppt` also checks the `Algorithm` line: `True` if it must be `MPPT`, `False` if
    it must not, `None` to ignore it. For a `series`, the last row gives the end
    time; otherwise, the end time is not known."""
    content = read_head(path, HEAD_SIZE)
    if not content.startswith('## Header ##'):
        return False

    # The first value of each `<key><TAB><value>` line; the header comes first.
    header = {}
    for line in content.splitlines():
        key, _, values = line.partition('\t')
        header.setdefault(key.strip(), values.split('\t')[0].strip())

    if header.get('Test') != test:
        return False
    if mppt is not None and (header.get('Algorithm') == 'MPPT') != mppt:
        return False

    start_time = None
    if header.get('Date') and header.get('Time'):
        start = datetime.fromisoformat(f'{header["Date"]}T{header["Time"]}')
        start_time = start.replace(tzinfo=LOCAL_TIME_ZONE)
    end_time = None
    if start_time is not None and series:
        hours = _hours_of_last_row(read_tail(path, TAIL_SIZE))
        if hours is not None:
            end_time = start_time + timedelta(hours=hours)
    method = 'measurement'
    sample_id = header.get('Device') or None
    sample_reference = None
    data = {}
    return start_time, end_time, method, sample_id, sample_reference, data


def _hours_of_last_row(tail: str) -> float | None:
    """The `Time (Hours)` of the last data row of a series file, from the file's end
    `tail`, or `None` if the last line is not a data row."""
    lines = [line for line in tail.splitlines() if line.strip()]
    if not lines:
        return None
    try:
        return float(lines[-1].split('\t')[0])
    except ValueError:
        return None


def match_jv(path: str) -> tuple | bool:
    """A J–V sweep under light during a stability test."""
    return _match(path, 'Stability (JV)')


def match_dark_jv(path: str) -> tuple | bool:
    """A J–V sweep in the dark."""
    return _match(path, 'Dark JV')


def match_mpp_tracking(path: str) -> tuple | bool:
    """The series of a stability test that tracks the maximum power point."""
    return _match(path, 'Stability (Tracking)', mppt=True, series=True)


def match_stability_series(path: str) -> tuple | bool:
    """The series of a stability test that holds the load at a fixed voltage."""
    return _match(path, 'Stability (Tracking)', mppt=False, series=True)


def match_jv_parameters(path: str) -> tuple | bool:
    """The figures of merit of every J–V sweep of a stability test over time, such
    as efficiency, fill factor, Voc and Jsc."""
    return _match(path, 'Stability (Parameters)', series=True)


def match_eqe(path: str) -> tuple | bool:
    """An external quantum efficiency spectrum, which UNITOV calls IPCE."""
    return _match(path, 'IPCE')
