# Template for one institution. Copy to `file_reading_<INSTITUTION>.py` and add the
# module to `INSTITUTIONS` in `__init__.py`.
#
# Files belong to the institution if they lie in a folder named `INSTITUTION`
# (e.g. `HZB/run_1/jv.csv`), or else if the uploader's email domain is listed in
# `EMAIL_DOMAINS`.

from zoneinfo import ZoneInfo

#: Short name, as in the module name and the upload folder.
INSTITUTION = 'TEMPLATE'

#: Email domains, such as 'uni.edu'; subdomains count too.
EMAIL_DOMAINS: tuple[str, ...] = ()

#: Time zone of the measurement computers, for times written without one.
LOCAL_TIME_ZONE = ZoneInfo('Europe/Berlin')

#: Bytes from the start of a file passed as `content`.
HEAD_SIZE = 4096

#: Bytes from the end of a file passed as `tail`; 0 for none.
TAIL_SIZE = 4096

# One function per measurement kind you upload, named `match_<kind>`, with <kind>
# from `MEASUREMENT_KINDS` in `schema_packages/schema_package.py` (e.g. `match_jv`).
# Functions are tried in that order; the first that does not return `False` wins.
#
# def match_jv(path: str, content: str, tail: str) -> tuple | bool:
#     # path:    file path within the upload
#     # content: beginning of the file as text; tail: end of the file as text
#     # Return `False` if the file is not of this kind, otherwise:
#     return start_time, end_time, provenance, sample_id, sample_reference, data
#     # start_time: `datetime` with time zone,
#     #     e.g. datetime(2026, 1, 5, 10, 0, tzinfo=LOCAL_TIME_ZONE)
#     # end_time: `datetime` with time zone; `None` = same as start,
#     #     e.g. start_time + timedelta(hours=2)
#     # provenance: where the data comes from, one of `PROVENANCES` in
#     #     `schema_packages/schema_package.py`: 'measured', 'simulated',
#     #     'derived', 'imported', 'literature', 'note', 'reference' or 'other'
#     # sample_id: text, e.g. 'AI03-1A'
#     # sample_reference: URI text, e.g. 'https://example.org/samples/AI03-1A'
#     # data: dict with anything else, `{}` if nothing, e.g. {'separator': ','}
#     # Use `None` for anything unknown.
#
# Shared helpers, such as `file_format_from_path`, are in `file_reading_utils.py`.
