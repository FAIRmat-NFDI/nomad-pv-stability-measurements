import pytest


@pytest.fixture
def staging_upload(tmp_path, monkeypatch):
    """An empty NOMAD staging upload in `tmp_path`, in which the standards of
    `staging_upload.CATALOGUE` are found in a catalogue every user can see."""
    # NOMAD is imported only here: imported by this file, while pytest starts, it
    # changes the root logger, which the template parser's test relies on.
    from nomad import config
    from staging_upload import StagingUpload

    monkeypatch.setattr(config.fs, 'staging', str(tmp_path / 'staging'))
    upload = StagingUpload(tmp_path / 'source')
    monkeypatch.setattr(
        'nomad_pv_stability_measurements.schema_packages.utils.find_standard',
        upload.published_standard,
    )
    return upload
