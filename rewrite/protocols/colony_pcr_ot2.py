"""Colony PCR — Opentrons OT-2

On-robot thermocycling. Multiple primer groups supported — reactions sharing
the same reagent tubes get a shared master mix.

Steps:
  1. Prepare master mix per primer group (water + mastermix + primers)
  2. Distribute master mix to reaction wells
  3. Colony template transfer (shared tip per colony source)
  4. Thermocycling (30× 98°C/55°C/72°C)
"""

from opentrons import protocol_api
from slowpoke.types import ColonyPcrInputs, ReagentVolumes, Reaction
from slowpoke.parsing import parse_colony_pcr_inputs, add_colony_pcr_parameters

metadata = {
    "protocolName": "Colony PCR (OT-2)",
    "description": "Colony PCR with on-robot thermocycling.",
    "apiLevel": "2.20",
}

# ── Volumes (µL) ────────────────────────────────────────────────────────────

REACTION_VOLUME = 10
VOLUME_WATER = REACTION_VOLUME / 2 - 3
VOLUME_MASTERMIX = REACTION_VOLUME / 2
VOLUME_FWD_PRIMER = 1
VOLUME_REV_PRIMER = 1
VOLUME_COLONY = 1

REAGENT_VOLUMES = ReagentVolumes(
    water=VOLUME_WATER,
    mastermix=VOLUME_MASTERMIX,
    fwd_primer=VOLUME_FWD_PRIMER,
    rev_primer=VOLUME_REV_PRIMER,
)

# ── Thermocycling ───────────────────────────────────────────────────────────

PCR_CYCLES = [
    {"temperature": 98, "hold_time_seconds": 15},
    {"temperature": 55, "hold_time_seconds": 30},
    {"temperature": 72, "hold_time_seconds": 200},
]
PCR_CYCLE_COUNT = 30

# ── Opentrons runtime parameters ────────────────────────────────────────────

add_parameters = add_colony_pcr_parameters

# ── Protocol ────────────────────────────────────────────────────────────────


def run(protocol: protocol_api.ProtocolContext):
    inputs = parse_colony_pcr_inputs(
        protocol.params.pcr_deck_map.parse_as_csv(),
        protocol.params.colony_template_map.parse_as_csv(),
        protocol.params.pcr_recipe.parse_as_csv(),
    )

    # Reaction name → sequential well index
    rxn_index: dict[Reaction, int] = {
        rxn.name: i for i, rxn in enumerate(inputs.reactions)
    }

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
    overflow_plate = protocol.load_labware("corning_96_wellplate_360ul_flat", "4")
    tc.open_lid()

    colony_plate = protocol.load_labware(
        "biorad_96_wellplate_200ul_pcr", "2", "Colony Templates",
    )
    reagent_rack = protocol.load_labware(
        "opentrons_24_tuberack_eppendorf_1.5ml_safelock_snapcap", "9", "PCR Reagents",
    )
    mix_rack = protocol.load_labware(
        "opentrons_24_tuberack_eppendorf_1.5ml_safelock_snapcap", "5", "PCR Mix Tubes",
    )

    def rxn_well(name: Reaction):
        i = rxn_index[name]
        return reaction_plate.wells()[i] if i < 96 else overflow_plate.wells()[i - 96]

    # ── Step 1: Prepare and distribute master mixes ──────────────────────
    for mix_idx, group in enumerate(inputs.primer_groups):
        n_samples = len(group.reaction_names) + 2  # +2 dead volume

        # Transfer each reagent into the mix tube
        for reagent_name, vol in REAGENT_VOLUMES.pairs(group.reagents):
            source = reagent_rack.wells_by_name()[inputs.reagent_rack[reagent_name]]
            p300.pick_up_tip()
            p300.transfer(
                n_samples * vol, source.bottom(z=2),
                mix_rack.wells()[mix_idx].bottom(z=3),
                blow_out=True, blowout_location="destination well", new_tip="never",
            )
            p300.drop_tip()

        # Mix and distribute to reaction wells
        p300.pick_up_tip()
        p300.mix(2, 2 * (n_samples + 4), mix_rack.wells()[mix_idx].bottom(z=1))
        p300.distribute(
            REACTION_VOLUME - VOLUME_COLONY,
            mix_rack.wells()[mix_idx].bottom(z=1),
            [rxn_well(n) for n in group.reaction_names],
            disposal_volume=5, new_tip="never",
        )
        p300.drop_tip()

    # ── Step 2: Colony templates (shared tip per colony source) ──────────
    colonies_index = inputs.colonies_to_reactions()
    for colony, rxn_names in colonies_index.items():
        source = colony_plate.wells_by_name()[inputs.colony_plate[colony]]
        p10.pick_up_tip()
        p10.distribute(
            VOLUME_COLONY, source.bottom(z=1),
            [rxn_well(n) for n in rxn_names],
            disposal_volume=1.5, new_tip="never",
        )
        p10.drop_tip()

    # ── Step 3: Thermocycling ────────────────────────────────────────────
    protocol.pause("Seal PCR plate, then resume.")
    tc.close_lid()
    tc.set_lid_temperature(105)
    tc.execute_profile(
        steps=[{"temperature": 98, "hold_time_seconds": 300}],
        repetitions=1, block_max_volume=REACTION_VOLUME,
    )
    tc.execute_profile(
        steps=PCR_CYCLES,
        repetitions=PCR_CYCLE_COUNT, block_max_volume=REACTION_VOLUME,
    )
    tc.execute_profile(
        steps=[{"temperature": 72, "hold_time_seconds": 300}],
        repetitions=1, block_max_volume=REACTION_VOLUME,
    )
    tc.set_block_temperature(25)
    tc.open_lid()
    tc.deactivate()
