"""Golden Gate Cloning — Opentrons Flex

Temperature modules for cooling. No on-board thermocycler — Golden Gate
cycling and heat shock are performed off-robot on a benchtop PCR machine.

Steps:
  1. Buffer/water (premixed, one tube)
  2. DNA parts (one tip per transfer)
  3. Enzyme (fresh tip per reaction, with mixing)
  4. Golden Gate cycling (manual, off-robot)
  5. Competent cell addition
  6. Heat shock (manual, off-robot)
  7. Spiral plating onto 6-well agar plates
"""

from opentrons import protocol_api, types
from slowpoke.types import CloningInputs, Part
from slowpoke.parsing import parse_cloning_inputs, add_cloning_parameters

metadata = {
    "protocolName": "Golden Gate Cloning (Flex)",
    "description": "Golden Gate assembly, transformation, and spiral plating.",
}
requirements = {"robotType": "Flex", "apiLevel": "2.20"}

# ── Volumes (µL) ────────────────────────────────────────────────────────────

VOLUME_ENZYME = 1
VOLUME_DNA = 1
NUM_PARTS = 4
REACTION_VOLUME = 10
VOLUME_WATER_BUFFER = REACTION_VOLUME - VOLUME_ENZYME - NUM_PARTS * VOLUME_DNA
VOLUME_COMPETENT = 50
TEMP = 4  # °C

# ── Spiral plating pattern (13 points on 6-well agar plate) ─────────────────

SPIRAL = [
    types.Point(x=0, y=0, z=6),      types.Point(x=0, y=6, z=5),
    types.Point(x=6, y=0, z=6),      types.Point(x=0, y=-6, z=5),
    types.Point(x=-6, y=0, z=6),     types.Point(x=0, y=12, z=5),
    types.Point(x=7.5, y=7.5, z=6),  types.Point(x=12, y=0, z=5),
    types.Point(x=7.5, y=-7.5, z=6), types.Point(x=0, y=-12, z=5),
    types.Point(x=-7.5, y=-7.5, z=6),types.Point(x=-12, y=0, z=5),
    types.Point(x=-7.5, y=7.5, z=6),
]

# ── Opentrons runtime parameters ────────────────────────────────────────────

add_parameters = add_cloning_parameters

# ── Helpers ─────────────────────────────────────────────────────────────────


def find_dna_well(part: Part, inputs: CloningInputs, fixed_plate, custom_plate):
    """Look up the physical well for a DNA part across both source plates."""
    if part in inputs.fixed_parts:
        return fixed_plate.wells_by_name()[inputs.fixed_parts[part]]
    if part in inputs.custom_parts:
        return custom_plate.wells_by_name()[inputs.custom_parts[part]]
    raise ValueError(f"Unknown DNA part: {part!r}")


# ── Protocol ────────────────────────────────────────────────────────────────


def run(protocol: protocol_api.ProtocolContext):
    inputs = parse_cloning_inputs(
        protocol.params.fixed_plate_map.parse_as_csv(),
        protocol.params.custom_plate_map.parse_as_csv(),
        protocol.params.combinations.parse_as_csv(),
    )
    num_rxns = len(inputs.assemblies)
    if num_rxns > 96:
        raise ValueError(f"Too many assemblies ({num_rxns}), max 96")

    parts_index = inputs.parts_to_assemblies()

    # ── Labware ──────────────────────────────────────────────────────────
    trash = protocol.load_trash_bin("A3")
    p50 = protocol.load_instrument("flex_1channel_50", "right", tip_racks=[
        protocol.load_labware("opentrons_flex_96_tiprack_50ul", "B3"),
        protocol.load_labware("opentrons_flex_96_tiprack_50ul", "C3"),
    ])

    temp_rxn = protocol.load_module("temperature module gen2", "A1")
    temp_rxn.set_temperature(celsius=TEMP)
    reaction_plate = temp_rxn.load_labware("biorad_96_wellplate_200ul_pcr", "A1")

    temp_reagent = protocol.load_module("temperature module gen2", "D3")
    temp_reagent.set_temperature(celsius=TEMP)
    trough = temp_reagent.load_labware(
        "opentrons_24_aluminumblock_nest_1.5ml_snapcap", "D3",
    )
    buffer_water = trough.wells_by_name()["A1"]
    enzyme_well = trough.wells_by_name()["B1"]
    competent_cell = trough.wells_by_name()["D1"]

    fixed_plate = protocol.load_labware("biorad_96_wellplate_200ul_pcr", "C2", "Fixed DNA")
    custom_plate = protocol.load_labware(
        "opentrons_24_tuberack_eppendorf_1.5ml_safelock_snapcap", "D2", "Custom DNA",
    )
    agar_plate = protocol.load_labware("corning_6_wellplate_16.8ml_flat", "C1", "Agar Plate")

    assembly_well = {}
    for i, asm in enumerate(inputs.assemblies):
        assembly_well[asm.name] = reaction_plate.wells()[i]

    protocol.pause("Temperature modules ready!")

    # ── Step 1: Buffer/water ─────────────────────────────────────────────
    p50.configure_for_volume(VOLUME_WATER_BUFFER)
    p50.pick_up_tip()
    for i in range(num_rxns):
        p50.aspirate(VOLUME_WATER_BUFFER, buffer_water)
        p50.dispense(VOLUME_WATER_BUFFER, reaction_plate.wells()[i].bottom(z=0.5))
    p50.drop_tip()

    # ── Step 2: DNA parts (fresh tip per transfer) ───────────────────────
    p50.configure_for_volume(VOLUME_DNA)
    for part, asm_names in parts_index.items():
        source = find_dna_well(part, inputs, fixed_plate, custom_plate)
        for name in asm_names:
            p50.pick_up_tip()
            p50.aspirate(VOLUME_DNA, source)
            p50.dispense(VOLUME_DNA, assembly_well[name].bottom(z=0.5))
            p50.drop_tip()

    # ── Step 3: Enzyme (fresh tip per reaction, with mixing) ─────────────
    protocol.pause("Add enzyme tube in B1.")
    p50.configure_for_volume(VOLUME_ENZYME)
    for i in range(num_rxns):
        p50.pick_up_tip()
        p50.aspirate(VOLUME_ENZYME, enzyme_well.bottom(z=1.5))
        p50.dispense(VOLUME_ENZYME, reaction_plate.wells()[i].bottom(z=1))
        p50.mix(3, 7, reaction_plate.wells()[i].bottom(z=1))
        p50.blow_out()
        p50.drop_tip()

    # ── Step 4: Golden Gate (manual, off-robot) ──────────────────────────
    temp_reagent.deactivate()
    temp_rxn.deactivate()
    protocol.pause(
        "Seal PCR plate. Run Golden Gate off-robot "
        "(25x 37C/16C, then 60C 5 min). Resume when done.",
    )

    # ── Step 5: Competent cells ──────────────────────────────────────────
    temp_rxn.set_temperature(celsius=TEMP)
    temp_reagent.set_temperature(celsius=TEMP)
    protocol.pause("Modules ready. Add competent cells in D1.")
    p50.configure_for_volume(VOLUME_COMPETENT)
    for i in range(num_rxns):
        p50.pick_up_tip()
        p50.aspirate(VOLUME_COMPETENT, competent_cell.bottom(z=2), rate=0.2)
        p50.dispense(VOLUME_COMPETENT, reaction_plate.wells()[i].bottom(z=2), rate=0.2)
        p50.mix(1, 25, reaction_plate.wells()[i].bottom(z=2), rate=0.2)
        p50.blow_out()
        p50.drop_tip()

    # ── Step 6: Heat shock (manual, off-robot) ───────────────────────────
    temp_reagent.deactivate()
    temp_rxn.deactivate()
    protocol.pause("Re-seal. Run heat shock off-robot. Resume when done.")

    # ── Step 7: Spiral plating ───────────────────────────────────────────
    wells_per_plate = len(agar_plate.wells())
    p50.configure_for_volume(VOLUME_COMPETENT)
    for i in range(num_rxns):
        well_idx = i % wells_per_plate
        if i >= wells_per_plate and well_idx == 0:
            protocol.pause("Replace with a new agar plate.")
        p50.pick_up_tip()
        p50.mix(3, VOLUME_COMPETENT, reaction_plate.wells()[i].bottom(z=2))
        spiral_dests = []
        for pt in SPIRAL:
            spiral_dests.append(agar_plate.wells()[well_idx].bottom(z=0).move(pt))
        p50.distribute(
            2.5, reaction_plate.wells()[i].bottom(z=2),
            spiral_dests,
            disposal_volume=1.5, new_tip="never",
        )
        p50.blow_out(trash)
        p50.drop_tip()
