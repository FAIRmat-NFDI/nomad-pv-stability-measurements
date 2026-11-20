"""Helpers that every institution's `file_reading_<INSTITUTION>.py` can use."""

import os
from pathlib import PurePosixPath

#: How many bytes `read_head` and `read_tail` read unless told otherwise.
READ_SIZE = 4096

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


def read_head(path: str, size: int = READ_SIZE) -> str:
    """The first `size` bytes of the file at `path`, on disk, as text.

    Decoded as UTF-8: before parsing, NOMAD rewrites text files that it recognizes as
    Latin-1 in UTF-8. Bytes that are not UTF-8, as in binary files, become `�`
    instead of an error, so such a file gives text that no `match_<kind>` function
    recognizes."""
    with open(path, 'rb') as file:
        return file.read(size).decode('utf-8', errors='replace')


def read_tail(path: str, size: int = READ_SIZE) -> str:
    """The last `size` bytes of the file at `path`, on disk, as text, decoded like
    `read_head`; empty for `size` 0. For a file shorter than `size`, the tail is the
    whole file. The tail may begin within a line."""
    if size == 0:
        return ''
    with open(path, 'rb') as file:
        file.seek(0, os.SEEK_END)
        file.seek(max(0, file.tell() - size))
        return file.read().decode('utf-8', errors='replace')
