from nomad.config.models.plugins import ParserEntryPoint


class StabilityFileParserEntryPoint(ParserEntryPoint):
    def load(self):
        from nomad_pv_stability_measurements.parsers.stability_file_parser import (
            StabilityFileParser,
        )

        return StabilityFileParser(**self.model_dump())


stability_file_parser_entry_point = StabilityFileParserEntryPoint(
    name='StabilityFileParser',
    description="""
    Registers every file of a stability upload with its stability file type, file
    format, provenance, times and sample.
    """,
    # Any file except NOMAD archive files, which must stay with NOMAD's own parser,
    # files whose name starts with a dot, and the project data spreadsheet and its
    # template, which the project entry reads. Matched against the path on disk, so
    # it must not reject dots in the folders above the upload.
    mainfile_name_re=(
        r'(?!.*\.archive\.(json|ya?ml)$)(?!.*/\.[^/]*$)'
        r'(?!(.*/)?project_data(_template)?\.xlsx$).*'
    ),
)
