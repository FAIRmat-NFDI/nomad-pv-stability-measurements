import pytest


@pytest.fixture
def staging_upload(tmp_path, monkeypatch):
    """An empty NOMAD staging upload in `tmp_path`."""
    # NOMAD is imported only here: imported by this file, while pytest starts, it
    # changes the root logger, which the template parser's test relies on.
    from nomad import config
    from staging_upload import StagingUpload

    monkeypatch.setattr(config.fs, 'staging', str(tmp_path / 'staging'))
    return StagingUpload(tmp_path / 'source')
