from nomad.config.models.plugins import SchemaPackageEntryPoint


class StabilitySchemaPackageEntryPoint(SchemaPackageEntryPoint):
    def load(self):
        from nomad_pv_stability_measurements.schema_packages.schema_package import (
            m_package,
        )

        return m_package


schema_package_entry_point = StabilitySchemaPackageEntryPoint(
    name='StabilityFiles',
    description="""
    The files of a stability upload and its project: the proposal, the file series
    of each sample with the standard applied to it, and the timeline.
    """,
)


class SampleSchemaEntryPoint(SchemaPackageEntryPoint):
    def load(self):
        from nomad_pv_stability_measurements.schema_packages.sample_schema import (
            m_package,
        )

        return m_package


sample_schema_entry_point = SampleSchemaEntryPoint(
    name='StabilitySamples',
    description="""
    The solar cell samples of a stability project: device, substrate with its layer
    stack, module configuration and encapsulation.
    """,
)
