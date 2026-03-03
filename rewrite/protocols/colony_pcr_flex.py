"""Colony PCR — Opentrons Flex

Temperature modules for cooling, manual thermocycling off-robot.
Assumes a single primer group (all reactions use the same reagents).

Steps:
  1. Prepare master mix (single tube)
  2. Distribute to reaction wells
  3. Colony template transfer (fresh tip per colony)
"""

from opentrons import protocol_api
from slowpoke.types import ColonyPcrInputs, ReagentVolumes, Reaction
from slowpoke.parsing import parse_colony_pcr_inputs, add_colony_pcr_parameters

metadata = {
    "protocolName": "Colony PCR (Flex)",
    "description": "Colony PCR with temperature modules, manual thermocycling.",
}
requirements = {"robotType": "Flex", "apiLevel": "2.20"}

# ── Volumes (µL) ────────────────────────────────────────────────────────────

REACTION_VOLUME = 10
VOLUME_WATER = 4.5
VOLUME_MASTERMIX = 2.5
VOLUME_FWD_PRIMER = 1
VOLUME_REV_PRIMER = 1
VOLUME_COLONY = 1
TEMP = 8  # °C

REAGENT_VOLUMES = ReagentVolumes(
    water=VOLUME_WATER,
    mastermix=VOLUME_MASTERMIX,
    fwd_primer=VOLUME_FWD_PRIMER,
    rev_primer=VOLUME_REV_PRIMER,
)

# ── Opentrons runtime parameters ────────────────────────────────────────────

add_parameters = add_colony_pcr_parameters

# ── Protocol ────────────────────────────────────────────────────────────────


def run(protocol: protocol_api.ProtocolContext):
    inputs = parse_colony_pcr_inputs(
        protocol.params.pcr_deck_map.parse_as_csv(),
        protocol.params.colony_template_map.parse_as_csv(),
        protocol.params.pcr_recipe.parse_as_csv(),
    )
    num_rxns = len(inputs.reactions)

    # Reaction name → sequential well index
    rxn_index: dict[Reaction, int] = {
        rxn.name: i for i, rxn in enumerate(inputs.reactions)
    }

    # ── Labware ──────────────────────────────────────────────────────────
    trash = protocol.load_trash_bin("A3")
    p50 = protocol.load_instrument(
        "flex_1channel_50", "right",
        tip_racks=[protocol.load_labware("opentrons_flex_96_tiprack_50ul", "C3")],
    )

    reaction_plate = protocol.load_labware(
        "biorad_96_wellplate_200ul_pcr", "C1", "Reactions",
    )
    overflow_plate = protocol.load_labware("corning_96_wellplate_360ul_flat", "D1")
    colony_plate = protocol.load_labware(
        "biorad_96_wellplate_200ul_pcr", "D2", "Colony Templates",
    )

    pcr_mod = protocol.load_module("temperature module gen2", "D3")
    reagent_rack = pcr_mod.load_labware(
        "opentrons_24_aluminumblock_nest_1.5ml_snapcap", "D3",
    )
    mix_mod = protocol.load_module("temperature module gen2", "A1")
    mix_rack = mix_mod.load_labware(
        "opentrons_24_aluminumblock_nest_1.5ml_snapcap", "A1",
    )

    pcr_mod.set_temperature(TEMP)
    mix_mod.set_temperature(TEMP)
    pcr_mod.await_temperature(TEMP)
    mix_mod.await_temperature(TEMP)

    def rxn_well(name: Reaction):
        i = rxn_index[name]
        return reaction_plate.wells()[i] if i < 96 else overflow_plate.wells()[i - 96]

    # ── Step 1: Prepare master mix (single primer group) ─────────────────
    # All reactions share the same reagents; use the first group.
    group = inputs.primer_groups[0]

    for reagent_name, vol in REAGENT_VOLUMES.pairs(group.reagents):
        source = reagent_rack.wells_by_name()[inputs.reagent_rack[reagent_name]]
        p50.pick_up_tip()
        p50.transfer(
            num_rxns * vol + 2, source.bottom(z=2),
            mix_rack.wells()[0].bottom(z=3),
            blow_out=True, blowout_location="destination well", new_tip="never",
        )
        p50.drop_tip()

    p50.pick_up_tip()
    p50.mix(3, 40, mix_rack.wells()[0].bottom(z=1))
    p50.drop_tip()

    # ── Step 2: Distribute to reaction wells ─────────────────────────────
    p50.pick_up_tip()
    p50.distribute(
        REACTION_VOLUME - VOLUME_COLONY,
        mix_rack.wells()[0].bottom(z=1),
        [rxn_well(rxn.name) for rxn in inputs.reactions],
        disposal_volume=2, new_tip="never",
    )
    p50.drop_tip()

    # ── Step 3: Colony templates (fresh tip per colony) ──────────────────
    for rxn in inputs.reactions:
        source = colony_plate.wells_by_name()[inputs.colony_plate[rxn.colony]]
        dest = rxn_well(rxn.name)
        p50.pick_up_tip()
        p50.transfer(
            VOLUME_COLONY, source.bottom(z=1), dest.bottom(z=1),
            blow_out=True, blowout_location="destination well", new_tip="never",
        )
        p50.drop_tip()

    pcr_mod.deactivate()
    mix_mod.deactivate()
    protocol.pause("Seal PCR plate. Run thermocycling off-robot.")
