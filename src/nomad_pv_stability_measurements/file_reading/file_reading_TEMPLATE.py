import os
import re
from datetime import datetime, timedelta, timezone
from zoneinfo import ZoneInfo

#: Short name of the institution
INSTITUTION = 'TEMPLATE'

#: Email domains, such as 'uni.edu'; subdomains count too.
EMAIL_DOMAINS: tuple[str, ...] = ('uni.edu',)

#: Time zone of the computers that write the files.
LOCAL_TIME_ZONE = ZoneInfo('Europe/Berlin')


#----------------------------- HELPER FUNCTIONS -----------------------------
# Please write your own file reading helper functions
# Feel free to ignore/delete the current ones
def _helper_header_value(content: str, key: str) -> str | None:
    """The value of the header line `<key><TAB><value>` in `content`, or None."""
    match = re.search(rf'^{re.escape(key)}\t([^\t\r\n]*)', content, re.MULTILINE)
    return match.group(1).strip() if match else None


def _helper_header_start_time(content: str) -> datetime:
    """The start of the measurement, from the header lines `Date` and `Time`,
    in the local time of the setup."""
    start = datetime.strptime(
        f'{_helper_header_value(content, "Date")} {_helper_header_value(content, "Time")}',
        '%Y-%m-%d %H:%M:%S',
    )
    return start.replace(tzinfo=LOCAL_TIME_ZONE)  # times always need a time zone



#----------------------------- MATCHING FUNCTIONS -----------------------------
# Please write one such function for each filetype provided by the institution.
# The functions should return False for every file that is not a match, and a tuple of
# (start_time, end_time, method, sample_id, sample_reference, data) for
# every file that is a match. return values should be as follows:

# start_time: Absolute start time of the measurement, as a datetime with time zone. 
# end_time: Absolute end time of the measurement, as a datetime with time zone. If not known, return None.
# method: How the data came to be, one of the available method values (see below).
# sample_id: The id of the sample/simulation run refering to the file.
# sample_reference: An external reference to the sample, if available.
# data: A dictionary for file-type specific file contents, can stay empty for now.

# AVAILABLE METHOD VALUES:
# 'measurement': 'Measured on the studied sample.',
# 'calibration': 'Measured on a reference device or standard rather than on the studied sample, such as the light source with a reference cell.',
# 'simulation': 'Computed from a model of the sample without measured input, such as a drift-diffusion simulation.',
# 'analysis': 'Computed from other data, such as figures of merit fitted to J-V curves or lifetimes such as T80 from a series.',
# 'database': 'Taken from a database.',
# 'literature': 'Taken from a publication.',
# 'note': 'Written by hand, such as lab notes or values typed in.',
# 'other': 'In a way that none of the other values describes.',
# 'unknown': 'Not known.',

#Exemplary JV matching function.
def match_jv(path: str) -> tuple | bool:
    """One J-V sweep, e.g. `jv.txt`."""

    with open(path, encoding='utf-8', errors='replace') as file:
        content = file.read() 

    condition = _helper_header_value(content, 'Test') == 'Stability (JV)'  # If this condition is met, we have a match. (i.e. this file is a JV file)

    if not condition:
        return False  # Return False for every file that is not a match.

    start_time = _helper_header_start_time(content) 

    end_time = None

    method = 'measurement'  # Determine

    sample_id = _helper_header_value(content, 'Device') or os.path.splitext(os.path.basename(path))[0]  

    sample_reference = None 

    data = {}
    return start_time, end_time, method, sample_id, sample_reference, data

#Exemplary MPPT matching function.
def match_mpp_tracking(path: str) -> tuple | bool:
    """Maximum power point tracking over time, e.g. `mppt.txt`."""

    with open(path, encoding='utf-8', errors='replace') as file:
        content = file.read()

    condition = (
        _helper_header_value(content, 'Test') == 'Stability (Tracking)'
        and _helper_header_value(content, 'Algorithm') == 'MPPT'
    )

    if not condition:
        return False

    start_time = _helper_header_start_time(content)

    # the end: the start plus the hours in the first column of the last data row
    last_row = content.strip().splitlines()[-1]
    end_time = start_time + timedelta(hours=float(last_row.split('\t')[0]))

    method = 'measurement'
    sample_id = (
        _helper_header_value(content, 'Device') or os.path.splitext(os.path.basename(path))[0]
    )
    sample_reference = None
    data = {}
    return start_time, end_time, method, sample_id, sample_reference, data



# You can execute this file as a script on sample data located in the same folder to check the matching works as expected. 
if __name__ == '__main__':
    test_files = ['jv.txt', 'mppt.txt']  # add your test files here

    match_functions = [match_jv, match_mpp_tracking] #add all your match functios here

    names = ('datetime', 'end_time', 'method', 'sample_id', 'sample_reference', 'data')

    for file_name in test_files:
        file_path = os.path.join(os.path.dirname(__file__), file_name)
        print(file_name)
        for match in match_functions:
            result = match(file_path)
            if result is False:
                print(f'  {match.__name__}: no match')
                continue
            print(f'  {match.__name__}:')
            for name, value in zip(names, result):
                text = value
                if isinstance(value, datetime):
                    # NOMAD stores times in UTC; a time without time zone is taken as UTC
                    if value.tzinfo is None:
                        text = f'{value.isoformat()}  WARNING: no time zone, NOMAD takes it as UTC'
                    else:
                        text = f'{value.isoformat()}  (stored as {value.astimezone(timezone.utc).isoformat()})'
                print(f'    {name:<17}{text}')
