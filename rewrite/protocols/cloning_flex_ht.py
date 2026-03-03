"""Golden Gate Cloning — Opentrons Flex (High-Throughput)

Dynamic tip rack calculation, batched buffer distribution, and multi-tube
competent cells for large runs (up to 96 assemblies).

Steps:
  1. Buffer/water (batched distribution)
  2. DNA parts (one tip per transfer)
  3. Enzyme (fresh tip per reaction, with mixing)
  4. Golden Gate cycling (manual, off-robot)
  5. Competent cells (multi-tube for large volumes)
  6. Heat shock (manual, off-robot)
  7. Spiral plating onto 6-well agar plates
"""

import math
from opentrons import protocol_api, types
from slowpoke.types import CloningInputs, Part
from slowpoke.parsing import parse_cloning_inputs, add_cloning_parameters

metadata = {
    "protocolName": "Golden Gate Cloning (Flex HT)",
    "description": "High-throughput Golden Gate assembly, transformation, and spiral plating.",
}
requirements = {"robotType": "Flex", "apiLevel": "2.20"}

# ── Volumes (µL) ────────────────────────────────────────────────────────────

VOLUME_ENZYME = 1.2
VOLUME_DNA = 1
NUM_PARTS = 6
REACTION_VOLUME = 12
VOLUME_WATER_BUFFER = REACTION_VOLUME - VOLUME_ENZYME - NUM_PARTS * VOLUME_DNA
VOLUME_COMPETENT = 50
TEMP = 4  # °C

# ── Competent cell tube capacity ────────────────────────────────────────────

COMP_TUBE_CAPACITY = 1100  # µL per tube
COMP_TUBE_SAFE = COMP_TUBE_CAPACITY - 100
RXNS_PER_COMP_TUBE = int(COMP_TUBE_SAFE // VOLUME_COMPETENT)

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

# ── Extra tip rack slots (used as needed) ───────────────────────────────────

EXTRA_TIP_SLOTS = ["A2", "B1", "B2", "D1", "C3", "D2"]

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

    # ── Tip calculation ──────────────────────────────────────────────────
    batch_size = max(1, 2 * (30 // math.ceil(VOLUME_WATER_BUFFER)))
    buffer_tips = math.ceil(num_rxns / batch_size)
    dna_tips = sum(len(asm.parts) for asm in inputs.assemblies)
    total_tips = int((buffer_tips + dna_tips + 3 * num_rxns) * 1.1)
    racks_needed = math.ceil(total_tips / 96)
    slots = EXTRA_TIP_SLOTS[:racks_needed]

    protocol.pause(
        f"Tip setup: {num_rxns} assemblies, ~{total_tips} tips, {racks_needed} racks.\n"
        f"Place 50 µL racks at: B3, {', '.join(slots)}",
    )

    # ── Labware ──────────────────────────────────────────────────────────
    trash = protocol.load_trash_bin("A3")
    tip_racks = [protocol.load_labware("opentrons_flex_96_tiprack_50ul", "B3", "Rack 1")]
    for i, slot in enumerate(slots):
        tip_racks.append(
            protocol.load_labware("opentrons_flex_96_tiprack_50ul", slot, f"Rack {i + 2}"),
        )
    p50 = protocol.load_instrument("flex_1channel_50", "right", tip_racks=tip_racks)

    temp_rxn = protocol.load_module("temperature module gen2", "A1")
    temp_rxn.set_temperature(celsius=TEMP)
    reaction_plate = temp_rxn.load_adapter(
        "opentrons_96_well_aluminum_block",
    ).load_labware("biorad_96_wellplate_200ul_pcr")

    temp_reagent = protocol.load_module("temperature module gen2", "D3")
    temp_reagent.set_temperature(celsius=TEMP)
    trough = temp_reagent.load_labware(
        "opentrons_24_aluminumblock_nest_1.5ml_snapcap", "D3",
    )
    buffer_well = trough.wells_by_name()["A1"]
    enzyme_well = trough.wells_by_name()["B1"]
    # Competent cell tubes at positions D1–D5 (indices 3, 7, 11, 15, 19)
    comp_cells = []
    for idx in (3, 7, 11, 15, 19):
        comp_cells.append(trough.wells()[idx])

    fixed_plate = protocol.load_labware("biorad_96_wellplate_200ul_pcr", "C2", "Fixed DNA")
    agar_plate = protocol.load_labware("corning_6_wellplate_16.8ml_flat", "C1", "Agar Plate")

    assembly_well = {}
    for i, asm in enumerate(inputs.assemblies):
        assembly_well[asm.name] = reaction_plate.wells()[i]

    total_buffer = VOLUME_WATER_BUFFER * num_rxns
    total_enzyme = VOLUME_ENZYME * num_rxns
    total_comp = VOLUME_COMPETENT * num_rxns

    # ── Step 1: Buffer/water (batched distribution) ──────────────────────
    protocol.pause(f"Modules ready! Put {total_buffer * 1.2:.0f} µL buffer/water in A1.")
    p50.configure_for_volume(VOLUME_WATER_BUFFER)
    for start in range(0, num_rxns, batch_size):
        wells = reaction_plate.wells()[start : start + batch_size]
        if wells:
            p50.distribute(
                VOLUME_WATER_BUFFER, [buffer_well], wells,
                disposal_volume=1, new_tip="always",
            )

    # ── Step 2: DNA parts (one tip per transfer) ─────────────────────────
    p50.configure_for_volume(VOLUME_DNA)
    for part, asm_names in parts_index.items():
        source = find_dna_well(part, inputs, fixed_plate, fixed_plate)
        for name in asm_names:
            p50.pick_up_tip()
            p50.aspirate(VOLUME_DNA, source.bottom(z=1))
            p50.dispense(VOLUME_DNA, assembly_well[name].bottom(z=1))
            p50.drop_tip()

    # ── Step 3: Enzyme (fresh tip per reaction, with mixing) ─────────────
    protocol.pause(f"Put {total_enzyme:.0f} µL enzyme in B1.")
    p50.configure_for_volume(10)
    mix_vol = min(REACTION_VOLUME * 0.75, 10)
    for i in range(num_rxns):
        p50.pick_up_tip()
        p50.aspirate(VOLUME_ENZYME, enzyme_well.bottom(z=1.5))
        p50.dispense(VOLUME_ENZYME, reaction_plate.wells()[i].bottom(z=1))
        p50.mix(3, mix_vol, reaction_plate.wells()[i].bottom(z=1))
        p50.blow_out()
        p50.drop_tip()

    # ── Step 4: Golden Gate (manual, off-robot) ──────────────────────────
    temp_reagent.deactivate()
    temp_rxn.deactivate()
    protocol.pause("Seal PCR plate. Run Golden Gate (37C/16C x25, 60C 5 min). Resume when done.")

    # ── Step 5: Competent cells (multi-tube for large runs) ──────────────
    temp_rxn.set_temperature(celsius=TEMP)
    temp_reagent.set_temperature(celsius=TEMP)
    protocol.pause(
        f"Add {total_comp:.0f} µL total competent cells "
        f"({COMP_TUBE_CAPACITY} µL/tube in D1–D5).",
    )
    p50.configure_for_volume(VOLUME_COMPETENT)
    for i in range(num_rxns):
        tube = comp_cells[i // RXNS_PER_COMP_TUBE]
        p50.pick_up_tip()
        p50.aspirate(VOLUME_COMPETENT, tube.bottom(z=2), rate=0.2)
        p50.dispense(VOLUME_COMPETENT, reaction_plate.wells()[i].bottom(z=2), rate=0.2)
        p50.mix(1, 25, reaction_plate.wells()[i].bottom(z=2), rate=0.2)
        p50.blow_out()
        p50.drop_tip()
    temp_reagent.deactivate()
    temp_rxn.deactivate()

    # ── Step 6: Heat shock (manual, off-robot) ───────────────────────────
    protocol.pause("Re-seal. Run heat shock. Resume for plating.")

    # ── Step 7: Spiral plating ───────────────────────────────────────────
    num_agar = math.ceil(num_rxns / 6)
    protocol.pause(f"Place agar plate 1/{num_agar} in C1. Resume to begin.")
    p50.configure_for_volume(VOLUME_COMPETENT)
    for i in range(num_rxns):
        idx = i % 6
        if idx == 0 and i > 0:
            protocol.pause(f"Replace agar plate (now {i // 6 + 1}/{num_agar}).")
        p50.pick_up_tip()
        p50.mix(3, VOLUME_COMPETENT, reaction_plate.wells()[i].bottom(z=2))
        spiral_dests = []
        for pt in SPIRAL:
            spiral_dests.append(agar_plate.wells()[idx].bottom(z=0).move(pt))
        p50.distribute(
            2.5, reaction_plate.wells()[i].bottom(z=2),
            spiral_dests,
            disposal_volume=1.5, new_tip="never",
        )
        p50.blow_out(trash)
        p50.drop_tip()

    protocol.pause("DONE! Remove agar plates. Incubate 37C overnight.")
