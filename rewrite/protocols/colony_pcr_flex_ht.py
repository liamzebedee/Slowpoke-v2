"""Colony PCR — Opentrons Flex (High-Throughput)

Multiple primer groups, large-volume transfers (>50 µL in chunks),
and per-colony template transfer with mixing.

Steps:
  1. Prepare master mix per primer group
  2. Mix and distribute to reaction wells (batched)
  3. Colony template transfer (fresh tip + mix per colony)
"""

from opentrons import protocol_api
from slowpoke.types import ColonyPcrInputs, ReagentVolumes, Reaction
from slowpoke.parsing import parse_colony_pcr_inputs, add_colony_pcr_parameters

metadata = {
    "protocolName": "Colony PCR (Flex HT)",
    "description": "High-throughput colony PCR with multi-group master mix support.",
}
requirements = {"robotType": "Flex", "apiLevel": "2.20"}

# ── Volumes (µL) ────────────────────────────────────────────────────────────

REACTION_VOLUME = 15
VOLUME_WATER = 2.5
VOLUME_MASTERMIX = 7.5
VOLUME_FWD_PRIMER = 1.5
VOLUME_REV_PRIMER = 1.5
VOLUME_COLONY = 2
MIX_PER_RXN = REACTION_VOLUME - VOLUME_COLONY
TEMP = 4   # °C
OVERAGE = 1.2  # 20% extra for pipetting error

REAGENT_VOLUMES = ReagentVolumes(
    water=VOLUME_WATER,
    mastermix=VOLUME_MASTERMIX,
    fwd_primer=VOLUME_FWD_PRIMER,
    rev_primer=VOLUME_REV_PRIMER,
)

# ── Opentrons runtime parameters ────────────────────────────────────────────

add_parameters = add_colony_pcr_parameters

# ── Helpers ─────────────────────────────────────────────────────────────────


def transfer_large_volume(p50, volume: float, source, dest):
    """Transfer a volume that may exceed 50 µL in multiple dispense cycles."""
    remaining = volume
    while remaining > 0:
        v = min(remaining, 50)
        p50.configure_for_volume(v)
        p50.transfer(
            v, source.bottom(z=1), dest.bottom(z=2),
            blow_out=True, blowout_location="destination well", new_tip="never",
        )
        remaining -= v


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
    trash = protocol.load_trash_bin("A3")
    p50 = protocol.load_instrument("flex_1channel_50", "right", tip_racks=[
        protocol.load_labware("opentrons_flex_96_tiprack_50ul", "C3"),
        protocol.load_labware("opentrons_flex_96_tiprack_50ul", "B3"),
        protocol.load_labware("opentrons_flex_96_tiprack_50ul", "A2"),
    ])

    rxn_mod = protocol.load_module("temperature module gen2", "A1")
    rxn_mod.set_temperature(TEMP)
    reaction_plate = rxn_mod.load_adapter(
        "opentrons_96_well_aluminum_block",
    ).load_labware("biorad_96_wellplate_200ul_pcr")
    overflow_plate = protocol.load_labware("biorad_96_wellplate_200ul_pcr", "D1")
    colony_plate = protocol.load_labware("biorad_96_wellplate_200ul_pcr", "B1")

    pcr_mod = protocol.load_module("temperature module gen2", "D3")
    pcr_mod.set_temperature(TEMP)
    reagent_rack = pcr_mod.load_labware(
        "opentrons_24_aluminumblock_nest_1.5ml_snapcap",
    )
    mix_rack = protocol.load_labware(
        "opentrons_24_tuberack_eppendorf_1.5ml_safelock_snapcap", "D2",
    )

    protocol.pause("Temperature modules ready!")

    def rxn_well(name: Reaction):
        i = rxn_index[name]
        return reaction_plate.wells()[i] if i < 96 else overflow_plate.wells()[i - 96]

    # ── Step 1: Prepare and distribute master mixes ──────────────────────
    for mix_idx, group in enumerate(inputs.primer_groups):
        n_samples = len(group.reaction_names) * OVERAGE

        # Transfer each reagent into the mix tube
        for reagent_name, vol in REAGENT_VOLUMES.pairs(group.reagents):
            source = reagent_rack.wells_by_name()[inputs.reagent_rack[reagent_name]]
            p50.pick_up_tip()
            transfer_large_volume(p50, n_samples * vol, source, mix_rack.wells()[mix_idx])
            p50.drop_tip()

        protocol.pause("Mix PCR master mixes manually if needed.")
        p50.pick_up_tip()
        mix_vol = min(50, MIX_PER_RXN * (n_samples - 1))
        p50.configure_for_volume(mix_vol)
        p50.mix(2, mix_vol, mix_rack.wells()[mix_idx].bottom(z=1))
        p50.drop_tip()

        # Distribute in batches sized to pipette capacity
        dest_wells = []
        for n in group.reaction_names:
            dest_wells.append(rxn_well(n))
        p50.configure_for_volume(MIX_PER_RXN)
        batch_size = max(1, 3 * (50 // MIX_PER_RXN))
        for start in range(0, len(dest_wells), batch_size):
            batch = dest_wells[start : start + batch_size]
            if batch:
                p50.distribute(
                    MIX_PER_RXN, mix_rack.wells()[mix_idx].bottom(z=1),
                    batch, disposal_volume=1, new_tip="once",
                )

    # ── Step 2: Colony templates (fresh tip + mix per colony) ────────────
    p50.configure_for_volume(VOLUME_COLONY)
    for rxn in inputs.reactions:
        source = colony_plate.wells_by_name()[inputs.colony_plate[rxn.colony]]
        dest = rxn_well(rxn.name)
        p50.pick_up_tip()
        p50.aspirate(VOLUME_COLONY, source.bottom(z=2))
        p50.dispense(VOLUME_COLONY, dest)
        p50.mix(3, min(REACTION_VOLUME * 0.75, 10), dest)
        p50.blow_out()
        p50.drop_tip()

    protocol.pause("Seal PCR plate.")
    pcr_mod.deactivate()
    rxn_mod.deactivate()
