from nomad.config.models.plugins import ParserEntryPoint
from pydantic import Field


class NewParserEntryPoint(ParserEntryPoint):
    parameter: int = Field(0, description='Custom configuration parameter')

    def load(self):
        from nomad_pv_stability_measurements.parsers.parser import NewParser

        return NewParser(**self.model_dump())


parser_entry_point = NewParserEntryPoint(
    name='NewParser',
    description='New parser entry point configuration.',
    mainfile_name_re=r'.*\.newmainfilename',
)


class StabilityFileParserEntryPoint(ParserEntryPoint):
    def load(self):
        from nomad_pv_stability_measurements.parsers.stability_file_parser import (
            StabilityFileParser,
        )

        return StabilityFileParser(**self.model_dump())


stability_file_parser_entry_point = StabilityFileParserEntryPoint(
    name='StabilityFileParser',
    description="""
    Registers every file of a stability upload with its measurement kind, file
    format, start time and sample.
    """,
    # Any file except NOMAD archive files, which must stay with NOMAD's own parser,
    # and files whose name starts with a dot. Matched against the path on disk, so
    # it must not reject dots in the folders above the upload.
    mainfile_name_re=r'(?!.*\.archive\.(json|ya?ml)$)(?!.*/\.[^/]*$).*',
)
