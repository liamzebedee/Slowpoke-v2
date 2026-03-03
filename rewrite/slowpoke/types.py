"""Domain types for Slowpoke.

Two workflows run on Opentrons OT-2 and Flex liquid-handling robots:

  1. Golden Gate Cloning
     Assemble DNA parts into plasmids, transform E. coli, plate on agar.

  2. Colony PCR
     Screen colonies by PCR to verify correct assembly.

Three user-provided CSV files define each run:

  Cloning:
    - fixed_parts   — 96-well plate grid of standardized toolkit DNA parts
    - custom_parts  — tube rack grid of user-designed DNA parts
    - assemblies    — rows of: plasmid_name, part1, part2, ...

  Colony PCR:
    - reagent_rack  — tube rack grid of water, mastermix, and primer tubes
    - colony_plate  — 96-well plate grid of colony template positions
    - reactions     — rows of: rxn_name, water, mastermix, fwd, rev, colony
"""

from dataclasses import dataclass
from typing import NewType


# ── Scalar types ────────────────────────────────────────────────────────────

# A position on labware: "A1", "B3", "H12"
Well = NewType("Well", str)

# A DNA part in the toolkit or custom set: "pTDH3", "sfGFP", "pWS064"
Part = NewType("Part", str)

# A plasmid being assembled: "pTDH3-sfGFP-tTDH1"
Plasmid = NewType("Plasmid", str)

# A reagent tube on the PCR rack: "Water", "Green_Taq", "primer_1"
Reagent = NewType("Reagent", str)

# A colony template on the colony plate: "colony_1", "colony_42"
Colony = NewType("Colony", str)

# A PCR reaction identifier: "rxn_1", "rxn_42"
Reaction = NewType("Reaction", str)


# ── Physical layout ─────────────────────────────────────────────────────────


@dataclass
class LabwareLayout:
    """Maps item names to well positions on a plate or tube rack.

    Built from a CSV grid where cell position determines the well address:
        row 0 col 0 → A1,  row 0 col 1 → A2,  ...
        row 1 col 0 → B1,  row 1 col 1 → B2,  ...

    Example CSV (24-tube rack, 4 rows × 6 cols):
        Water,    primer_1, primer_5
        Green_Taq,primer_2, primer_6
        Phire,    primer_3, primer_7
        buffer,   primer_4, primer_8

    Produces: {"Water": "A1", "primer_1": "A2", "Green_Taq": "B1", ...}
    """

    positions: dict[str, Well]

    def __getitem__(self, name: str) -> Well:
        return self.positions[name]

    def __contains__(self, name: str) -> bool:
        return name in self.positions


# ── Golden Gate Cloning ─────────────────────────────────────────────────────


@dataclass
class Assembly:
    """One Golden Gate assembly: combine DNA parts into a named plasmid.

    CSV row:  pTDH3-sfGFP, pTDH3, sfGFP, tTDH1, pWS064
    Produces: Assembly(name="pTDH3-sfGFP", parts=["pTDH3", "sfGFP", "tTDH1", "pWS064"])

    Part count is variable (3-part, 5-part, 6-part assemblies are common).
    Each part name must appear in either the fixed_parts or custom_parts layout.
    """

    # "pTDH3-sfGFP-tTDH1"
    name: Plasmid
    # ["pTDH3", "sfGFP", "tTDH1", "pWS064"]
    parts: list[Part]


@dataclass
class CloningInputs:
    """Everything the user provides for a Golden Gate cloning run.

    fixed_parts  — standardized genetic toolkit (e.g., MoClo YTK 96-well plate)
    custom_parts — user-designed DNA parts (tube rack or second plate)
    assemblies   — which parts to combine into which plasmids
    """

    fixed_parts: LabwareLayout
    custom_parts: LabwareLayout
    assemblies: list[Assembly]

    def parts_to_assemblies(self) -> dict[Part, list[Plasmid]]:
        """Invert index: for each DNA part, which assemblies use it.

        Used to batch transfers — one tip per part, dispensing into all
        assemblies that need it.
        """
        index: dict[Part, list[Plasmid]] = {}
        for asm in self.assemblies:
            for part in asm.parts:
                index.setdefault(part, []).append(asm.name)
        return index


# ── Colony PCR ──────────────────────────────────────────────────────────────


@dataclass(frozen=True)
class ReagentSet:
    """The four reagent tubes needed for one PCR reaction.

    Each field is the NAME of a tube on the reagent rack.
    The name maps to a physical well position via the LabwareLayout.

    Example: ReagentSet(water="Water", mastermix="Green_Taq",
                        fwd_primer="primer_1", rev_primer="primer_2")
    """

    # "Water"
    water: Reagent
    # "Green_Taq"
    mastermix: Reagent
    # "primer_1"
    fwd_primer: Reagent
    # "primer_2"
    rev_primer: Reagent

    def as_list(self) -> list[Reagent]:
        """Ordered list for iteration: [water, mastermix, fwd, rev]."""
        return [self.water, self.mastermix, self.fwd_primer, self.rev_primer]


@dataclass(frozen=True)
class ReagentVolumes:
    """µL of each reagent per reaction, parallel to ReagentSet fields.

    Example: ReagentVolumes(water=2.5, mastermix=7.5, fwd_primer=1.5, rev_primer=1.5)
    """

    water: float
    mastermix: float
    fwd_primer: float
    rev_primer: float

    def pairs(self, reagents: ReagentSet) -> list[tuple[Reagent, float]]:
        """Zip reagent names with their volumes for iteration.

        Returns: [("Water", 2.5), ("Green_Taq", 7.5), ("primer_1", 1.5), ("primer_2", 1.5)]
        """
        return [
            (reagents.water, self.water),
            (reagents.mastermix, self.mastermix),
            (reagents.fwd_primer, self.fwd_primer),
            (reagents.rev_primer, self.rev_primer),
        ]


@dataclass
class PcrReaction:
    """One colony PCR reaction: reagent tubes + colony template.

    CSV row:  rxn_1, Water, Green_Taq, primer_1, primer_2, colony_1
    Produces: PcrReaction(name="rxn_1",
                          reagents=ReagentSet(water="Water", mastermix="Green_Taq",
                                             fwd_primer="primer_1", rev_primer="primer_2"),
                          colony="colony_1")
    """

    # "rxn_1"
    name: Reaction
    reagents: ReagentSet
    # "colony_1"
    colony: Colony


@dataclass
class PrimerGroup:
    """PCR reactions grouped by shared reagent set (differ only by colony).

    One master mix tube is prepared per group, then distributed to all
    reaction wells in the group. Only the colony template varies.
    """

    reagents: ReagentSet
    # ["rxn_1", "rxn_2", "rxn_3"]
    reaction_names: list[Reaction]


@dataclass
class ColonyPcrInputs:
    """Everything the user provides for a colony PCR run.

    reagent_rack   — tube positions for water, mastermix, and primers
    colony_plate   — colony template positions on the 96-well plate
    reactions      — individual PCR reactions to set up
    primer_groups  — reactions grouped by shared primers (for master mix prep)
    """

    reagent_rack: LabwareLayout
    colony_plate: LabwareLayout
    reactions: list[PcrReaction]
    primer_groups: list[PrimerGroup]

    def colonies_to_reactions(self) -> dict[Colony, list[Reaction]]:
        """Invert index: for each colony, which reactions use it.

        Used on OT-2 to share a tip across reactions from the same colony.
        """
        index: dict[Colony, list[Reaction]] = {}
        for rxn in self.reactions:
            index.setdefault(rxn.colony, []).append(rxn.name)
        return index
