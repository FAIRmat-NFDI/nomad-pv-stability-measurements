from datetime import datetime, timedelta
from zoneinfo import ZoneInfo
import os

#: Short name of the institution
INSTITUTION = 'TEMPLATE'

#: Email domains, such as 'uni.edu'; subdomains count too.
EMAIL_DOMAINS: tuple[str, ...] = ('uni.edu',)

#: Time zone of the computers that write the files.
LOCAL_TIME_ZONE = ZoneInfo('Europe/Berlin')

# Please write one such function per for each filetype provided by the institution.
def match_jv(path: str) -> tuple | bool:

    with open(path, encoding='utf-8', errors='replace') as file:
        content = file.read() # read the file content, use different decoding or delete if not needed

    condition = False  # If this condition is met, we have a match. (i.e. this file is a JV file)

    if(not condition): 
        return False  # Return False for every file that is not a match.
    
    # extract the time, the measurement/simulation was started
    start_time = datetime(2026, 1, 5, 10, 0, tzinfo=LOCAL_TIME_ZONE) # Replace by date extracted from file
    
    # extract the time, the measurement/simulation ended
    end_time = start_time + timedelta(hours=2) # Replace by end date extracted from file, if not available, use None

    # specify the provenance of the data. listed below.
    provenance = 'measured'  # Determine

    # specify the id of the sample/simulation run refering to the file. 
    sample_id = os.path.splitext(os.path.basename(path))[0]  # file name without folder and extension, e.g. 'AI03-1A' for '.../AI03-1A.txt'; replace by sample id extracted from file

    # you can provide an external reference to the sample
    sample_reference = 'https://example.org/samples/AI03-1A' # Replace if external reference available, otherwise None
    
    # dict for file-type specific file contents, can stay empty for now
    data = {}
    return start_time, end_time, provenance, sample_id, sample_reference, data

# AVAILABLE PROVANCE VALUES:
# 'measured': 'Measured on the sample.',
# 'simulated': 'Computed by a model of the sample.',
# 'derived': 'Computed from other data, such as figures of merit fitted to measured curves.'
# 'imported': 'Taken from another source, such as a database.',
# 'literature': 'Taken from a publication.',
# 'note': 'Written by hand, such as lab notes or values typed in.',
# 'reference': 'Measured on a reference device or standard rather than on the sample or studied, such as a calibration.'
# 'other': 'From a source that none of the other values describes.',
# 'unknown': 'Not known.',