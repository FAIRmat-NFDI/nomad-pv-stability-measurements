#
# Copyright The NOMAD Authors.
#
# This file is part of NOMAD. See https://nomad-lab.eu for further info.
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#     http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.
#
"""The solar cell samples of a stability project: device, substrate with its layer
stack, module configuration and encapsulation.

The definitions are taken from `nomad-baseclasses` (nomad-hzb/nomad-baseclasses,
version 1.0.1), reduced to what a stability project describes, so that this plugin
does not depend on that package. Names and units are kept, including the class name
`SolcarCellSample`, so that the data maps one to one. Differences: the sections that
are entries of their own also inherit `EntryData`, and the normalizers that rely on
other parts of `nomad-baseclasses` (naming normalizers, solar cell results) are left
out.
"""

import numpy as np
from nomad.datamodel.data import ArchiveSection, EntryData
from nomad.datamodel.metainfo.basesections import (
    CompositeSystem,
    CompositeSystemReference,
    Entity,
    Process,
    ReadableIdentifiers,
)
from nomad.metainfo import Quantity, Reference, SchemaPackage, Section, SubSection

m_package = SchemaPackage()


class ReadableIdentifiersCustom(ReadableIdentifiers):
    """The identifiers of a sample, with the identifier the lab writes on it."""

    m_def = Section(a_eln=dict(hide=['sample_owner', 'sample_short_name', 'sample_id']))

    sample_owner = Quantity(
        type=str, shape=[], a_eln=dict(component='StringEditQuantity')
    )

    sample_short_name = Quantity(
        type=str, shape=[], a_eln=dict(component='StringEditQuantity')
    )

    sample_id = Quantity(type=str, shape=[], a_eln=dict(component='StringEditQuantity'))

    def normalize(self, archive, logger):
        if self.sample_owner:
            self.owner = self.sample_owner
        if self.sample_short_name:
            self.short_name = self.sample_short_name
        if self.sample_id and self.lab_id is None:
            self.lab_id = self.sample_id

        super().normalize(archive, logger)


class LayerProperties(ArchiveSection):
    """One layer of the device stack."""

    m_def = Section(
        links=['https://purl.archive.org/tfsco/TFSCO_00000007'],
        label_quantity='layer_material_name',
    )

    layer_type = Quantity(
        links=['https://purl.archive.org/tfsco/TFSCO_00000007'],
        type=str,
        shape=[],
        a_eln=dict(
            component='EnumEditQuantity',
            props=dict(
                suggestions=[
                    'Hole Transport Layer',
                    'Electron Transport Layer',
                    'Absorber Layer',
                    'Buffer Layer',
                    'A.R.C.',
                    'Back reflection',
                    'Down conversion',
                    'Encapsulation',
                    'Light management',
                    'Upconversion',
                    'Back Contact',
                    'Passivation',
                    'Carbon Paste Layer',
                    'Substrate Conductive Layer',
                ]
            ),
        ),
    )

    layer_material_name = Quantity(
        type=str,
        description=(
            'The chemical formula using common abreviations. '
            'This will be used to set layer material, if not set, e.g. MAPbI3.'
        ),
        a_eln=dict(component='StringEditQuantity'),
    )

    layer_material = Quantity(
        type=str,
        description=(
            'The chemical formula of the layer. This will be used directly and '
            'indirectly in the search. The formula will be used itself as well as '
            'the extracted chemical elements.'
        ),
    )

    layer_thickness = Quantity(
        type=np.dtype(np.float64),
        description='The thickness of the sample, either measured or assumed.',
        unit='nm',
        shape=[],
        a_eln=dict(component='NumberEditQuantity', defaultDisplayUnit='nm'),
    )

    layer_transmission = Quantity(
        type=np.dtype(np.float64),
        description='Percentage of light that gets transmitted through the layer.',
        a_eln=dict(component='NumberEditQuantity', props=dict(minValue=0)),
    )

    layer_morphology = Quantity(
        type=str,
        description='A description of the morphology of the film',
        shape=[],
        a_eln=dict(component='StringEditQuantity'),
    )

    layer_sheet_resistance = Quantity(
        type=np.dtype(np.float64),
        unit='ohm',
        a_eln=dict(
            component='NumberEditQuantity',
            defaultDisplayUnit='ohm',
            props=dict(minValue=0),
        ),
    )

    layer_chemical_id = Quantity(
        type=str,
        description='Identifier of the product used for creating the layer'
        'in case it is purchased from supplier',
        a_eln=dict(component='StringEditQuantity'),
    )


class Substrate(Entity, EntryData):
    """The substrate of a device, with its areas and its layer stack."""

    substrate_dimension = Quantity(
        type=str,
        description='Physical dimensions of the substrate (e.g. "10 cm × 10 cm").',
        a_eln=dict(component='StringEditQuantity'),
    )

    solar_cell_area = Quantity(
        type=np.dtype(np.float64),
        unit='cm**2',
        shape=[],
        description=(
            'Sample area. Kept for legacy compatibility; in practice often used as '
            'pixel area.'
        ),
        a_eln=dict(component='NumberEditQuantity'),
    )

    pixel_area = Quantity(
        type=np.dtype(np.float64),
        unit='cm**2',
        shape=[],
        description=(
            'Total area of the cell.'
            'Defined as the overlap between front and back contacts.'
        ),
        a_eln=dict(component='NumberEditQuantity'),
    )

    active_area = Quantity(
        type=np.dtype(np.float64),
        unit='cm**2',
        shape=[],
        description=(
            'The effective area of the cell during IV and stability measurements '
            'under illumination. If measured with a mask, this corresponds to the '
            'area of the hole in the mask. Otherwise equals the pixel area.'
        ),
        a_eln=dict(component='NumberEditQuantity'),
    )

    dead_area = Quantity(
        type=np.dtype(np.float64),
        unit='cm**2',
        shape=[],
        description=(
            'Interconnect area of the cell, inactive to solar conversion. '
            'Includes scribing lines and borders between cells in a module.'
        ),
        a_eln=dict(component='NumberEditQuantity'),
    )

    aperture_area = Quantity(
        type=np.dtype(np.float64),
        unit='cm**2',
        shape=[],
        description=(
            'Sum of active area and dead area per cell. '
            'Not to be confused with the illumination aperture.'
        ),
        a_eln=dict(component='NumberEditQuantity'),
    )

    geometrical_fill_factor = Quantity(
        type=np.dtype(np.float64),
        shape=[],
        description='Ratio of active area to the total aperture area.',
        a_eln=dict(component='NumberEditQuantity'),
    )

    number_of_pixels = Quantity(
        type=np.dtype(np.float64),
        shape=[],
        a_eln=dict(component='NumberEditQuantity'),
        description='Number of pixels/cells.',
    )

    substrate = Quantity(
        type=str,
        a_eln=dict(
            component='EnumEditQuantity',
            props=dict(
                suggestions=[
                    'Glass',
                    'Ti-foil',
                    'silicon wafer',
                    'SLG',
                    'PET',
                    'Quartz',
                    'PDMS',
                ]
            ),
        ),
    )

    conducting_material = Quantity(
        type=str,
        shape=['*'],
        a_eln=dict(
            component='EnumEditQuantity',
            props=dict(
                suggestions=[
                    'FTO',
                    'ITO',
                    'PEN',
                    'AZO',
                    'IZO',
                    'Graphene',
                    'Ti',
                    'Ag',
                    'Ag-nw',
                    'Ag-grid',
                    'Au',
                ]
            ),
        ),
    )

    substrate_properties = SubSection(section_def=LayerProperties, repeats=True)

    def normalize(self, archive, logger):
        # The aperture is the active and the dead area; the geometrical fill factor
        # is the active part of it. Values that are given are kept.
        if self.active_area is not None and self.dead_area is not None:
            if self.aperture_area is None:
                self.aperture_area = self.active_area + self.dead_area
        if self.active_area is not None and self.aperture_area is not None:
            if self.geometrical_fill_factor is None and self.aperture_area:
                self.geometrical_fill_factor = float(
                    self.active_area / self.aperture_area
                )
        super().normalize(archive, logger)


class ModuleConfiguration(ArchiveSection):
    """
    Tracks whether this solar cell device is a module, i.e. multiple pixels
    are electrically connected. This is orthogonal to the multi-junction concept:
    a tandem can also be a module.

    The total number of pixels on the substrate is tracked on the Substrate section
    (number_of_pixels). This section captures which and how those pixels are
    connected at the device level.
    """

    is_module = Quantity(
        type=bool,
        default=False,
        description=(
            'Whether this device has pixels electrically connected (module '
            'configuration).'
        ),
        a_eln=dict(component='BoolEditQuantity'),
    )

    pixel_connection = Quantity(
        type=str,
        description='How the pixels are electrically connected within the module.',
        a_eln=dict(
            component='EnumEditQuantity',
            props=dict(suggestions=['Parallel', 'Series', 'Mixed']),
        ),
    )

    module_active_area = Quantity(
        type=np.dtype(np.float64),
        unit='cm**2',
        description='Total active area of the module.',
        a_eln=dict(component='NumberEditQuantity', defaultDisplayUnit='cm**2'),
    )


class SolcarCellSample(CompositeSystem, EntryData):
    """A photovoltaic device: its substrate with the layer stack, its architecture
    and, for a module, how its pixels are connected."""

    substrate = Quantity(
        type=Reference(Substrate.m_def), a_eln=dict(component='ReferenceEditQuantity')
    )

    architecture = Quantity(
        type=str,
        shape=[],
        description="""
            The cell architecture with respect to the direction of current flow and
            the order in which layers are deposited.
            The two most common are nip (also referred to as normal) and pin
            (also referred to as inverted)
            but there are also a few others, e.g. Back contacted.
            - *nip* architecture means that the electrons are collected at the
            substrate side.
            - *pin* architecture means that it instead is the holes that are
            collected at the substrate side.
        """,
        a_eln=dict(
            component='EnumEditQuantity',
            props=dict(
                suggestions=[
                    'Unknown',
                    'Pn-Heterojunction',
                    'Front contacted',
                    'Back contacted',
                    'pin',
                    'nip',
                    'Schottky',
                ]
            ),
        ),
    )

    number_of_junctions = Quantity(type=int, a_eln=dict(component='NumberEditQuantity'))

    sample_id = SubSection(section_def=ReadableIdentifiersCustom)
    parent = SubSection(section_def=CompositeSystemReference)

    module_configuration = SubSection(
        section_def=ModuleConfiguration,
        description=(
            'Module-level configuration: whether pixels are connected and how. '
            'Orthogonal to the number of junctions — a tandem can also be a module.'
        ),
    )


class LayerDeposition(Process):
    """A material processing which deposits thin layers onto an material entity."""

    m_def = Section(
        links=['https://purl.archive.org/tfsco/TFSCO_00000067'], label_quantity='layer'
    )

    layer = SubSection(
        links=['http://purl.obolibrary.org/obo/RO_0002234'],
        section_def=LayerProperties,
        repeats=True,
    )


class UVCuring(ArchiveSection):
    """Curing of a UV-curable adhesive using a UV-lamp."""

    lamp_details = Quantity(
        type=str, shape=[], a_eln=dict(component='StringEditQuantity')
    )

    wavelength = Quantity(
        links=['http://purl.obolibrary.org/obo/PATO_0001242'],
        type=np.dtype(np.float64),
        unit='nm',
        shape=[],
        a_eln=dict(
            component='NumberEditQuantity',
            defaultDisplayUnit='nm',
            props=dict(minValue=0),
        ),
    )

    intensity = Quantity(
        links=['https://purl.archive.org/tfsco/TFSCO_00001128'],
        type=np.dtype(np.float64),
        unit='mW/cm**2',
        shape=[],
        a_eln=dict(
            component='NumberEditQuantity',
            defaultDisplayUnit='mW/cm**2',
            props=dict(minValue=0),
        ),
    )

    exposure_time = Quantity(
        type=np.dtype(np.float64),
        unit='s',
        shape=[],
        a_eln=dict(
            component='NumberEditQuantity',
            defaultDisplayUnit='s',
            props=dict(minValue=0),
        ),
    )

    distance = Quantity(
        links=['https://purl.archive.org/tfsco/TFSCO_00005720'],
        type=np.dtype(np.float64),
        unit='mm',
        shape=[],
        a_eln=dict(
            component='NumberEditQuantity',
            defaultDisplayUnit='mm',
            props=dict(minValue=0),
        ),
    )

    atmosphere = Quantity(
        type=str,
        shape=[],
        a_eln=dict(
            component='EnumEditQuantity',
            props=dict(suggestions=['N2', 'ambient', 'Ar']),
        ),
    )


class LaminationSettings(ArchiveSection):
    """The settings of a lamination step."""

    temperature = Quantity(
        links=[
            'http://purl.obolibrary.org/obo/PATO_0000146',
            'https://purl.archive.org/tfsco/TFSCO_00002111',
        ],
        type=np.dtype(np.float64),
        unit='°C',
        shape=[],
        a_eln=dict(component='NumberEditQuantity', defaultDisplayUnit='°C'),
    )

    time = Quantity(
        links=[
            'http://purl.obolibrary.org/obo/PATO_0000165',
            'https://purl.archive.org/tfsco/TFSCO_00005085',
        ],
        type=np.dtype(np.float64),
        unit='s',
        shape=[],
        a_eln=dict(
            component='NumberEditQuantity',
            defaultDisplayUnit='s',
            props=dict(minValue=0),
        ),
    )

    pressure = Quantity(
        type=np.dtype(np.float64),
        unit='MPa',
        shape=[],
        a_eln=dict(
            component='NumberEditQuantity',
            defaultDisplayUnit='MPa',
            props=dict(minValue=0),
        ),
    )

    force = Quantity(
        type=np.dtype(np.float64),
        unit='N',
        shape=[],
        a_eln=dict(
            component='NumberEditQuantity',
            defaultDisplayUnit='N',
            props=dict(minValue=0),
        ),
    )

    area = Quantity(
        type=np.dtype(np.float64),
        unit='mm**2',
        shape=[],
        a_eln=dict(
            component='NumberEditQuantity',
            defaultDisplayUnit='mm**2',
            props=dict(minValue=0),
        ),
    )

    heat_up_time = Quantity(
        type=np.dtype(np.float64),
        unit='s',
        shape=[],
        a_eln=dict(
            component='NumberEditQuantity',
            defaultDisplayUnit='s',
            props=dict(minValue=0),
        ),
    )

    cool_down_time = Quantity(
        type=np.dtype(np.float64),
        unit='s',
        shape=[],
        a_eln=dict(
            component='NumberEditQuantity',
            defaultDisplayUnit='s',
            props=dict(minValue=0),
        ),
    )


class BarrierFoilLamination(LaminationSettings):
    """Lamination of the barrier foil onto the (wet or pre-applied) adhesive layer."""

    barrier_foil = Quantity(
        type=str,
        shape=[],
        a_eln=dict(component='StringEditQuantity'),
        description='Name/product of the barrier foil laminated onto the adhesive.',
    )

    line_speed = Quantity(
        type=np.dtype(np.float64),
        unit='mm/s',
        shape=[],
        a_eln=dict(
            component='NumberEditQuantity',
            defaultDisplayUnit='mm/s',
            props=dict(minValue=0),
        ),
        description='Web/line speed, for roll-to-roll lamination.',
    )


class AdhesiveApplication(ArchiveSection):
    """Application of the adhesive that bonds the barrier foil to the sample.

    Depending on the lab and equipment, this can be a wet chemical coating step
    (spiral bar coating, slot-die coating, blade coating, dispensing) of a
    UV-curable resin, or simply laminating a ready-made pressure sensitive
    adhesive (PSA) film, in which case no separate curing step is needed.
    """

    m_def = Section(label_quantity='method')

    method = Quantity(
        type=str,
        shape=[],
        a_eln=dict(
            component='EnumEditQuantity',
            props=dict(
                suggestions=[
                    'Spiral Bar Coating',
                    'Slot Die Coating',
                    'Blade Coating',
                    'Dispensing',
                    'Pressure Sensitive Adhesive Film',
                    'Other',
                ]
            ),
        ),
    )

    adhesive_layer_info = SubSection(section_def=LayerProperties)


class Encapsulation(LayerDeposition, EntryData):
    """The encapsulation of a solar cell or module.

    Encapsulation is typically a lamination stack: an adhesive (a UV-curable
    resin or a pressure sensitive adhesive) is applied and a barrier foil is
    laminated on top of it, after which the adhesive may be cured (e.g. under a
    UV-lamp). This sequence can be applied to a single side of the sample (e.g.
    if the substrate itself is already a barrier foil) or to both sides.
    """

    encapsulation_method = Quantity(
        type=str,
        shape=[],
        a_eln=dict(
            component='EnumEditQuantity',
            props=dict(suggestions=['Sheet-to-Sheet (S2S)', 'Roll-to-Roll (R2R)']),
        ),
    )

    sides_encapsulated = Quantity(
        type=str,
        shape=[],
        a_eln=dict(
            component='EnumEditQuantity',
            props=dict(suggestions=['Single Side', 'Both Sides']),
        ),
        description='Whether the encapsulation sequence was applied to a '
        'single side of the sample (e.g. because the substrate itself is already '
        'a barrier foil) or to both sides.',
    )

    adhesive_application = SubSection(section_def=AdhesiveApplication)
    barrier_lamination = SubSection(section_def=BarrierFoilLamination)
    curing = SubSection(section_def=UVCuring)

    def normalize(self, archive, logger):
        if not self.method:
            self.method = 'Encapsulation'
        super().normalize(archive, logger)


m_package.__init_metainfo__()
