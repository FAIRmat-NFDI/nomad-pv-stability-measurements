"""Reading the summary file of a stability upload one processing level later."""

from nomad.parsing.parser import ArchiveParser


class StabilityUploadSummaryParser(ArchiveParser):
    """Reads a summary file exactly as NOMAD's `ArchiveParser` reads archive files.

    It differs only in its name pattern and processing level, given by its entry
    point: NOMAD processes the files of an upload level by level, so a summary of a
    higher level than the file parser is normalized only after the entries of all
    files exist, and its references to them can be followed."""

    def __init__(self, **kwargs):
        # Skips `ArchiveParser.__init__`, which fixes level -1, so the level and
        # file pattern of `summary_parser_entry_point` apply. No domain, like archives.
        super(ArchiveParser, self).__init__(domain=None, **kwargs)
