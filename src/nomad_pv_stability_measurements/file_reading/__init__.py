"""How the files of each institution are recognized.

One module `file_reading_<INSTITUTION>.py` per institution, with the interface of
`file_reading_TEMPLATE.py`. Helpers that every institution can use are in
`file_reading_utils.py`.

A file belongs to an institution if it lies in a folder of the upload named like
the institution's `INSTITUTION`. `INSTITUTIONS` lists the institutions that are
looked for.
"""

from types import ModuleType

from nomad_pv_stability_measurements.file_reading import (
    file_reading_HZB,
    file_reading_UNITOV,
)

INSTITUTIONS: tuple[ModuleType, ...] = (file_reading_HZB, file_reading_UNITOV)
