"""Parse CSV files into domain types.

Each parser takes raw CSV rows (list[list[str]] from Opentrons' parse_as_csv())
and returns typed domain objects.
"""

from .types import (
    Well,
    Part,
    Plasmid,
    Reagent,
    Colony,
    Reaction,
    LabwareLayout,
    Assembly,
    CloningInputs,
    ReagentSet,
    ReagentVolumes,
    PcrReaction,
    PrimerGroup,
    ColonyPcrInputs,
)

# Row letters for converting grid position → well address
ROWS = "ABCDEFGH"

# Raw CSV row type (what Opentrons' parse_as_csv() returns)
CsvRow = list[str]
CsvGrid = list[CsvRow]


def parse_layout(csv: CsvGrid) -> LabwareLayout:
    """Parse a CSV grid into a LabwareLayout.

    Each non-empty cell becomes: cell_value → well_address.
    Position (row=0, col=0) → "A1", (row=2, col=5) → "C6", etc.
    """
    positions: dict[str, Well] = {}
    for i, row in enumerate(csv):
        for j, cell in enumerate(row):
            name = cell.strip()
            if name:
                positions[name] = Well(f"{ROWS[i]}{j + 1}")
    return LabwareLayout(positions)


def parse_assemblies(csv: CsvGrid) -> list[Assembly]:
    """Parse combination CSV: each row is plasmid_name, part1, part2, ...

    Example row: pTDH3-sfGFP, pTDH3, sfGFP, tTDH1, pWS064
    """
    return [
        Assembly(
            name=Plasmid(row[0].strip()),
            parts=[Part(c.strip()) for c in row[1:] if c.strip()],
        )
        for row in csv
        if row and row[0].strip()
    ]


def parse_pcr_reactions(csv: CsvGrid) -> list[PcrReaction]:
    """Parse PCR recipe CSV: each row is name, water, mastermix, fwd, rev, colony.

    Example row: rxn_1, Water, Green_Taq, primer_1, primer_2, colony_1
    """
    reactions: list[PcrReaction] = []
    for row in csv:
        if not row or not row[0].strip():
            continue
        cells = [c.strip() for c in row]
        reactions.append(
            PcrReaction(
                name=Reaction(cells[0]),
                reagents=ReagentSet(
                    water=Reagent(cells[1]),
                    mastermix=Reagent(cells[2]),
                    fwd_primer=Reagent(cells[3]),
                    rev_primer=Reagent(cells[4]),
                ),
                colony=Colony(cells[5]),
            )
        )
    return reactions


def group_by_reagents(reactions: list[PcrReaction]) -> list[PrimerGroup]:
    """Group reactions that share the same reagent set.

    Reactions in a group differ only by colony template.
    One master mix tube is prepared per group.
    """
    groups: dict[ReagentSet, list[Reaction]] = {}
    for rxn in reactions:
        groups.setdefault(rxn.reagents, []).append(rxn.name)
    return [
        PrimerGroup(reagents=reagents, reaction_names=names)
        for reagents, names in groups.items()
    ]


# ── Composite parsers ───────────────────────────────────────────────────────


def parse_cloning_inputs(
    fixed_csv: CsvGrid,
    custom_csv: CsvGrid,
    combinations_csv: CsvGrid,
) -> CloningInputs:
    """Parse all three cloning CSVs into a single typed input."""
    return CloningInputs(
        fixed_parts=parse_layout(fixed_csv),
        custom_parts=parse_layout(custom_csv),
        assemblies=parse_assemblies(combinations_csv),
    )


def parse_colony_pcr_inputs(
    reagent_csv: CsvGrid,
    colony_csv: CsvGrid,
    recipe_csv: CsvGrid,
) -> ColonyPcrInputs:
    """Parse all three colony PCR CSVs into a single typed input."""
    reactions = parse_pcr_reactions(recipe_csv)
    return ColonyPcrInputs(
        reagent_rack=parse_layout(reagent_csv),
        colony_plate=parse_layout(colony_csv),
        reactions=reactions,
        primer_groups=group_by_reagents(reactions),
    )


# ── Opentrons runtime parameter registration ────────────────────────────────


def add_cloning_parameters(parameters) -> None:
    """Register CSV upload fields for Golden Gate cloning protocols."""
    parameters.add_csv_file(
        variable_name="fixed_plate_map",
        display_name="Fixed toolkit map",
        description="Grid of fixed DNA part names matching 96-well plate layout",
    )
    parameters.add_csv_file(
        variable_name="custom_plate_map",
        display_name="Custom parts map",
        description="Grid of custom DNA part names matching tube rack layout",
    )
    parameters.add_csv_file(
        variable_name="combinations",
        display_name="Combinations to make",
        description="Rows of: plasmid_name, part1, part2, ...",
    )


def add_colony_pcr_parameters(parameters) -> None:
    """Register CSV upload fields for colony PCR protocols."""
    parameters.add_csv_file(
        variable_name="pcr_deck_map",
        display_name="PCR deck map",
        description="Grid of reagent names matching tube rack layout",
    )
    parameters.add_csv_file(
        variable_name="colony_template_map",
        display_name="Colony template map",
        description="Grid of colony names matching 96-well plate layout",
    )
    parameters.add_csv_file(
        variable_name="pcr_recipe",
        display_name="PCR recipe",
        description="Rows of: rxn_name, water, mastermix, fwd, rev, colony",
    )
