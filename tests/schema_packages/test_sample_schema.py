from nomad import utils
from nomad.datamodel import EntryArchive, EntryMetadata

from nomad_pv_stability_measurements.schema_packages.sample_schema import (
    SolarCellSample,
)


def normalized(**values) -> SolarCellSample:
    sample = SolarCellSample(**values)
    archive = EntryArchive(
        metadata=EntryMetadata(mainfile='sample.archive.json'), data=sample
    )
    sample.normalize(archive, utils.get_logger(__name__))
    return sample


def test_the_sample_id_is_the_lab_id_unless_one_is_given():
    assert normalized(sample_id=' RPV-S1 ').lab_id == 'RPV-S1'
    assert normalized(sample_id='RPV-S1', lab_id='HZB-0042').lab_id == 'HZB-0042'
