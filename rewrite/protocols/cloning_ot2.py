"""Golden Gate Cloning — Opentrons OT-2

On-robot thermocycling via Thermocycler Module, dual pipettes (p10 + p300).

Steps:
  1. Buffer + water (volume varies by part count)
  2. DNA parts (one tip per part, batched across assemblies)
  3. Golden Gate thermocycling (25× 37°C/16°C, then 60°C)
  4. Competent cell addition (fresh tip per reaction)
  5. Heat shock (4°C → 42°C → 4°C → 37°C)
  6. Spiral plating onto 6-well agar plates
"""

from opentrons import protocol_api, types
from slowpoke.types import CloningInputs, Part
from slowpoke.parsing import parse_cloning_inputs, add_cloning_parameters

metadata = {
    "protocolName": "Golden Gate Cloning (OT-2)",
    "description": "Golden Gate assembly with on-robot thermocycling, transformation, and spiral plating.",
    "apiLevel": "2.20",
}

# ── Volumes (µL) ────────────────────────────────────────────────────────────

VOLUME_DNA = 1
VOLUME_BUFFER = 2
VOLUME_COMPETENT = 50
REACTION_VOLUME = 10

# ── Thermocycling ───────────────────────────────────────────────────────────

GOLDEN_GATE_CYCLES = [
    {"temperature": 37, "hold_time_seconds": 120},
    {"temperature": 16, "hold_time_seconds": 300},
]
GOLDEN_GATE_REPETITIONS = 25

HEAT_SHOCK = [
    {"temperature": 4, "hold_time_seconds": 600},
    {"temperature": 42, "hold_time_seconds": 90},
    {"temperature": 4, "hold_time_seconds": 120},
    {"temperature": 37, "hold_time_seconds": 3600},
]

# ── Spiral plating pattern (13 points on 6-well agar plate) ─────────────────

SPIRAL = [
    types.Point(x=0, y=0),
    types.Point(x=0, y=4),    types.Point(x=4, y=0),
    types.Point(x=0, y=-4),   types.Point(x=-4, y=0),
    types.Point(x=0, y=8),    types.Point(x=5.5, y=5.5),
    types.Point(x=8, y=0),    types.Point(x=5.5, y=-5.5),
    types.Point(x=0, y=-8),   types.Point(x=-5.5, y=-5.5),
    types.Point(x=-8, y=0),   types.Point(x=-5.5, y=5.5),
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
    p10 = protocol.load_instrument(
        "p10_single", "right",
        tip_racks=[protocol.load_labware("opentrons_96_tiprack_20ul", "3")],
    )
    p300 = protocol.load_instrument(
        "p300_single", "left",
        tip_racks=[protocol.load_labware("opentrons_96_tiprack_300ul", "6")],
    )

    tc = protocol.load_module("Thermocycler Module")
    reaction_plate = tc.load_labware("biorad_96_wellplate_200ul_pcr")
    tc.open_lid()
    tc.set_block_temperature(4)

    temp_mod = protocol.load_module("Temperature Module", "3")
    trough = temp_mod.load_labware("opentrons_24_aluminumblock_nest_1.5ml_snapcap", "3")
    buffer_well = trough.wells_by_name()["A1"]
    water_well = trough.wells_by_name()["B1"]
    competent_cell = trough.wells_by_name()["D1"]

    fixed_plate = protocol.load_labware("biorad_96_wellplate_200ul_pcr", "1", "Fixed DNA")
    custom_plate = protocol.load_labware(
        "opentrons_24_tuberack_eppendorf_1.5ml_safelock_snapcap", "2", "Custom DNA",
    )
    agar_plate = protocol.load_labware("corning_6_wellplate_16.8ml_flat", "5", "Agar Plate")

    assembly_well = {}
    for i, asm in enumerate(inputs.assemblies):
        assembly_well[asm.name] = reaction_plate.wells()[i]

    # ── Step 1: Buffer + water (volume varies by part count) ─────────────
    p10.pick_up_tip()
    for asm in inputs.assemblies:
        water_vol = REACTION_VOLUME - VOLUME_BUFFER - len(asm.parts) * VOLUME_DNA
        p10.consolidate(
            [VOLUME_BUFFER, water_vol],
            [buffer_well, water_well],
            assembly_well[asm.name].bottom(z=0.5),
            new_tip="never",
        )
    p10.drop_tip()

    # ── Step 2: DNA parts (one tip per part, batched across assemblies) ──
    for part, asm_names in parts_index.items():
        source = find_dna_well(part, inputs, fixed_plate, custom_plate)
        dest_wells = []
        for n in asm_names:
            dest_wells.append(assembly_well[n])
        p10.pick_up_tip()
        while dest_wells:
            batch = dest_wells[:10]
            dest_wells = dest_wells[10:]
            p10.aspirate(VOLUME_DNA * len(batch), source)
            for well in batch:
                p10.dispense(VOLUME_DNA, well.bottom(z=0.5))
            if dest_wells:
                p10.mix(2, 10, water_well.bottom(z=0.5))
                p10.blow_out()
        p10.drop_tip()

    # ── Step 3: Golden Gate thermocycling ─────────────────────────────────
    protocol.pause("Seal the PCR plate, then resume.")
    tc.close_lid()
    tc.set_lid_temperature(105)
    tc.execute_profile(
        steps=[{"temperature": 98, "hold_time_seconds": 300}],
        repetitions=1, block_max_volume=REACTION_VOLUME,
    )
    tc.execute_profile(
        steps=GOLDEN_GATE_CYCLES,
        repetitions=GOLDEN_GATE_REPETITIONS, block_max_volume=REACTION_VOLUME,
    )
    tc.execute_profile(
        steps=[{"temperature": 60, "hold_time_seconds": 300}],
        repetitions=1, block_max_volume=REACTION_VOLUME,
    )
    tc.set_block_temperature(4)
    tc.open_lid()

    # ── Step 4: Competent cells (fresh tip per reaction) ──────────────────
    protocol.pause("Remove seal. Resume for competent cell addition.")
    for i in range(num_rxns):
        p300.pick_up_tip()
        p300.transfer(
            VOLUME_COMPETENT, competent_cell.bottom(z=0.5),
            reaction_plate.wells()[i].bottom(z=0.5), new_tip="never",
        )
        p300.mix(1, 25, reaction_plate.wells()[i].bottom(z=0.5))
        p300.blow_out()
        p300.drop_tip()
    temp_mod.deactivate()

    # ── Step 5: Heat shock ────────────────────────────────────────────────
    protocol.pause("Re-seal. Resume for heat shock.")
    tc.close_lid()
    tc.execute_profile(
        steps=HEAT_SHOCK, repetitions=1, block_max_volume=40,
    )
    tc.set_block_temperature(37)
    tc.open_lid()

    # ── Step 6: Spiral plating ────────────────────────────────────────────
    protocol.pause("Remove seal. Resume for plating.")
    wells_per_plate = len(agar_plate.wells())
    for i in range(num_rxns):
        well_idx = i % wells_per_plate
        if i >= wells_per_plate and well_idx == 0:
            protocol.pause("Replace with a new agar plate.")
        p300.pick_up_tip()
        p300.mix(1, 25, reaction_plate.wells()[i].bottom(z=0.5))
        spiral_dests = []
        for pt in SPIRAL:
            spiral_dests.append(agar_plate.wells()[well_idx].bottom(z=6).move(pt))
        p300.distribute(
            4.5, reaction_plate.wells()[i].bottom(z=0.5),
            spiral_dests,
            disposal_volume=1.5, new_tip="never",
        )
        p300.blow_out()
        p300.drop_tip()

    tc.deactivate()
