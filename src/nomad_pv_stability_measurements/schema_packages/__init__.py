from nomad.config.models.plugins import SchemaPackageEntryPoint
from pydantic import Field


class NewSchemaPackageEntryPoint(SchemaPackageEntryPoint):
    parameter: int = Field(0, description='Custom configuration parameter')

    def load(self):
        from nomad_pv_stability_measurements.schema_packages.schema_package import (
            m_package,
        )

        return m_package


schema_package_entry_point = NewSchemaPackageEntryPoint(
    name='NewSchemaPackage',
    description='New schema package entry point configuration.',
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
