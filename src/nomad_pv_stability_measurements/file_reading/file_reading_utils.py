"""Helpers that every institution's `file_reading_<INSTITUTION>.py` can use."""

from pathlib import PurePosixPath

#: The value of `StabilityFile.file_format` for each file name extension, written in
#: lower case and without the dot. Several extensions can stand for one format.
FORMAT_BY_EXTENSION = {
    'csv': 'csv',
    'tsv': 'tsv',
    'txt': 'txt',
    'dat': 'dat',
    'json': 'json',
    'yaml': 'yaml',
    'yml': 'yaml',
    'xml': 'xml',
    'xlsx': 'xlsx',
    'xls': 'xls',
    'ods': 'ods',
    'h5': 'hdf5',
    'hdf5': 'hdf5',
    'hdf': 'hdf5',
    'nxs': 'nexus',
    'mat': 'mat',
    'png': 'png',
    'jpg': 'jpg',
    'jpeg': 'jpg',
    'tif': 'tiff',
    'tiff': 'tiff',
    'bmp': 'bmp',
    'pdf': 'pdf',
    'docx': 'docx',
    'zip': 'zip',
}


def file_format_from_path(path: str) -> str:
    """The file format of the file at `path`, from its extension, ignoring case.

    `'other'` for an extension not in `FORMAT_BY_EXTENSION`, `'unknown'` for a file
    name without an extension."""
    extension = PurePosixPath(path).suffix.lower().lstrip('.')
    if not extension:
        return 'unknown'
    return FORMAT_BY_EXTENSION.get(extension, 'other')


def is_in_institution_folder(path: str, institution: str) -> bool:
    """`True` if one of the folders of `path`, a path within the upload, is named
    `institution`, ignoring case. The file's own name does not count."""
    folders = PurePosixPath(path).parts[:-1]
    return institution.lower() in (folder.lower() for folder in folders)
