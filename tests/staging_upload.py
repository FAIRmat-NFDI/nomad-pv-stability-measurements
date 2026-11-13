"""A NOMAD staging upload for tests, as during NOMAD's processing."""

from types import SimpleNamespace

from nomad import utils
from nomad.datamodel import EntryArchive, EntryMetadata
from nomad.datamodel.context import ServerContext
from nomad.files import StagingUploadFiles

from nomad_pv_stability_measurements.parsers.stability_file_parser import (
    StabilityFileParser,
)

#: The standards the tests find in a catalogue every user can see, by name.
CATALOGUE = ('ISOS-D-1', 'ISOS-L-1', 'ISOS-L-2')


class StagingUpload:
    """A NOMAD staging upload with its `ServerContext`, as during processing.

    `processed` lists the files that parsers ask NOMAD to process during
    processing. `main_author` is the uploader, a NOMAD `User`, or `None`.
    `published_standard` stands in for NOMAD's search of the visible standards:
    the standards of `CATALOGUE` are entries of this upload."""

    upload_id = 'test_upload'
    main_author = None

    def __init__(self, source_dir):
        self.source_dir = source_dir
        self.files = StagingUploadFiles(self.upload_id, create=True)
        self.processed = []
        # The context sees the upload only through these attributes.
        upload = SimpleNamespace(
            upload_id=self.upload_id,
            upload_files=self.files,
            process_updated_raw_file=lambda path, allow_modify: self.processed.append(
                path
            ),
        )
        self.context = ServerContext(upload=upload)

    def add(self, files: dict[str, str]) -> None:
        """Adds files to the upload, given as a text per path."""
        for path, content in files.items():
            (self.source_dir / path).parent.mkdir(parents=True, exist_ok=True)
            (self.source_dir / path).write_text(content)
        self.files.add_rawfiles(str(self.source_dir))

    def os_path(self, path: str) -> str:
        return self.files.raw_file_object(path).os_path

    def parse(self, path: str) -> EntryArchive:
        """Makes and stores the entry of the file at `path` with the file parser."""
        archive = EntryArchive(
            metadata=EntryMetadata(
                upload_id=self.upload_id, mainfile=path, main_author=self.main_author
            ),
            m_context=self.context,
        )
        StabilityFileParser().parse(
            self.os_path(path), archive, utils.get_logger(__name__)
        )
        entry_id = utils.generate_entry_id(self.upload_id, path)
        self.files.write_archive(entry_id, archive.m_to_dict())
        return archive

    def process_archive_file(self, path: str) -> EntryArchive:
        """Makes and stores the entry of the archive file at `path` as NOMAD's
        archive parser and normalization do."""
        import json

        from nomad.datamodel import EntryData

        with self.files.raw_file(path, 'r') as file:
            data = json.load(file)['data']
        archive = EntryArchive(
            metadata=EntryMetadata(
                upload_id=self.upload_id, mainfile=path, main_author=self.main_author
            ),
            m_context=self.context,
        )
        archive.data = EntryData.m_from_dict(data, m_context=self.context)
        archive.data.normalize(archive, utils.get_logger(__name__))
        entry_id = utils.generate_entry_id(self.upload_id, path)
        self.files.write_archive(entry_id, archive.m_to_dict())
        return archive

    def published_standard(self, name: str) -> str | None:
        """A reference to the standard `name` of `CATALOGUE`, written into the upload
        as its entry; `None` for any other name."""
        from nomad_pv_stability_standards.schema_packages.standard import (
            StabilityStandard,
        )

        if name not in CATALOGUE:
            return None
        path = f'catalogue/{name}.archive.json'
        entry_id = utils.generate_entry_id(self.upload_id, path)
        archive = EntryArchive(
            metadata=EntryMetadata(upload_id=self.upload_id, mainfile=path),
            data=StabilityStandard(name=name),
        )
        self.files.write_archive(entry_id, archive.m_to_dict())
        return f'../uploads/{self.upload_id}/archive/{entry_id}#data'
