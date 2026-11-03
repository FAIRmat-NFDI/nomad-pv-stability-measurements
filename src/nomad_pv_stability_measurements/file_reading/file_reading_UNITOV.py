"""Recognizing the files of UNITOV (University of Rome Tor Vergata).

UNITOV's stations write tab-separated text files that begin with `## Header ##`. The
header names the measurement in a line `Test<TAB><name>`:

    Stability (JV)          one J–V sweep during a stability test
    Stability (Tracking)    the series recorded while the load is held or tracked;
                            its `Algorithm` line says how: `MPPT` or `Fixed Voltage`
    Stability (Parameters)  the figures of merit of every J–V sweep over the test
    Dark JV                 a J–V sweep in the dark
    IPCE                    the external quantum efficiency

Other files, such as the PDF plots exported next to Dark JV and IPCE measurements,
are of kind `unknown`.
"""

import re

INSTITUTION = 'UNITOV'

_TEST = re.compile(r'^Test\t([^\t\r\n]*)', re.MULTILINE)
_ALGORITHM = re.compile(r'^Algorithm\t([^\t\r\n]*)', re.MULTILINE)


def _header_value(pattern: re.Pattern, content: str) -> str | None:
    """The value of a header line, or `None` if the file is not a UNITOV text file
    or has no such line."""
    if not content.startswith('## Header ##'):
        return None
    match = pattern.search(content)
    return match.group(1).strip() if match else None


def match_jv(path: str, content: str) -> bool:
    """A J–V sweep under light during a stability test."""
    return _header_value(_TEST, content) == 'Stability (JV)'


def match_dark_jv(path: str, content: str) -> bool:
    """A J–V sweep in the dark."""
    return _header_value(_TEST, content) == 'Dark JV'


def match_mpp_tracking(path: str, content: str) -> bool:
    """The series of a stability test that tracks the maximum power point."""
    return (
        _header_value(_TEST, content) == 'Stability (Tracking)'
        and _header_value(_ALGORITHM, content) == 'MPPT'
    )


def match_stability_series(path: str, content: str) -> bool:
    """The other series of a stability test: one held at a fixed voltage, and the
    figures of merit of its J–V sweeps over time."""
    test = _header_value(_TEST, content)
    if test == 'Stability (Parameters)':
        return True
    return (
        test == 'Stability (Tracking)' and _header_value(_ALGORITHM, content) != 'MPPT'
    )


def match_eqe(path: str, content: str) -> bool:
    """An external quantum efficiency spectrum, which UNITOV calls IPCE."""
    return _header_value(_TEST, content) == 'IPCE'
