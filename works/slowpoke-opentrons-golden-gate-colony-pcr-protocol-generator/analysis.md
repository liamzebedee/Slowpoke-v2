# Slowpoke: Opentrons Protocol Generator for Golden Gate Cloning and Colony PCR

## Overview

Slowpoke is an open-source Python tool developed at Imperial College London (Fankang Meng, Koray Malci) and later adapted for the Opentrons Flex platform by Alicia Da Silva and Henri Galez at Institut Pasteur / Inria. It automates the generation of liquid-handling robot protocols for two core synthetic biology workflows: **Golden Gate (GG) assembly with transformation and plating**, and **colony PCR screening**. The tool targets the Opentrons ecosystem (OT-2 and Flex robots) and uses a code-generation architecture — a GUI-driven "generator" script reads CSV input files, then concatenates user-defined data with a workflow template to produce a ready-to-run Opentrons Python protocol.

## Repository Structure

```
Slowpoke/
├── README.md
├── LICENSE
├── Cloning/
│   ├── generator_OT2_for_cloning_protocol.py        # GUI generator for OT-2
│   ├── generator_Flex_for_cloning_protocol.py        # GUI generator for Flex
│   ├── generator_Flex_for_cloning_protocol_v2_for_HT.py  # High-throughput Flex generator
│   ├── cloning_workflow_OT2.py                       # OT-2 workflow template
│   ├── cloning_workflow_Flex.py                      # Flex workflow template
│   ├── cloning_workflow_Flex_v2_for_HT.py            # High-throughput Flex template
│   ├── fixed_toolkit_map.csv                         # 96-well plate map of fixed DNA parts
│   ├── custom_parts_map.csv                          # 96-well plate map of custom DNA parts
│   └── combination-to-make.csv                       # Desired plasmid assemblies
└── Colony_PCR/
    ├── generator_for_colony_PCR_protocol.py          # GUI generator for OT-2
    ├── generator_Flex_for_colony_PCR_protocol_v2_for_HT.py  # High-throughput Flex generator
    ├── colony_PCR_workflow_OT2.py                    # OT-2 PCR workflow template
    ├── colony_PCR_workflow_Flex.py                   # Flex PCR workflow template
    ├── colony_PCR_workflow_Flex_v2_for_HT.py         # High-throughput Flex PCR template
    ├── pcr_recipe_to_make.csv                        # PCR reactions to perform
    ├── colony_template_map.csv                       # Colony plate layout
    └── pcr_deck_map.csv                              # PCR reagent tube layout
```

## Architecture: Code Generation Pattern

The system follows a two-phase architecture:

### Phase 1: Generator (GUI-driven data preparation)
Each generator script (`generator_*.py`) uses `tkinter` file dialogs to:
1. Prompt the user to select CSV input files (plate maps, combinations/recipes)
2. Parse and validate the CSV data (handling BOM characters, enforcing max 96 combinations)
3. Generate an output agar plate map CSV
4. **Concatenate** the parsed data (as Python literals via `json.dumps()`) with the workflow template file into a single output `.py` protocol file

The output protocol file has this structure:
```python
dna_plate_map_dict = {...}      # JSON-serialized plate maps
combinations_to_make = [...]    # JSON-serialized assembly list
# ... then the entire workflow template is appended ...
```

This means the workflow templates reference `dna_plate_map_dict` and `combinations_to_make` (or `pcr_recipe_to_make`) as module-level globals, which are defined by the generator at the top of the output file.

### Phase 2: Workflow Template (robot execution)
The workflow templates (`*_workflow_*.py`) contain the actual Opentrons API calls. They define:
- Labware loading (tipracks, plates, modules)
- Pipetting sequences (DNA dispensing, enzyme addition, competent cell handling)
- Thermocycler or temperature module profiles
- Plating routines

## Cloning Workflow (Golden Gate Assembly)

### Inputs
- **fixed_toolkit_map.csv**: 8x12 grid mapping well positions to fixed genetic toolkit parts (e.g., promoters, terminators from YTK/STK/KTK kits)
- **custom_parts_map.csv**: 8x12 grid mapping well positions to user-specific DNA parts (e.g., genes of interest)
- **combination-to-make.csv**: Each row defines a target plasmid — first column is the name, subsequent columns are the parts to combine

### Protocol Steps (all versions)
1. **Reaction setup**: Dispense water + buffer mix into reaction plate wells (one per combination)
2. **DNA part distribution**: For each unique DNA part, aspirate from its source well and dispense into all combinations that use it (tip-reuse optimization in OT-2; fresh tips in Flex versions)
3. **Enzyme addition**: Add restriction enzyme (e.g., BsaI) to each reaction, mix
4. **Thermocycling (GG reaction)**: 25 cycles of 37°C/16°C, then 60°C inactivation (performed off-robot in Flex versions, on-robot via Thermocycler Module on OT-2)
5. **Competent cell addition**: Transfer 50 µL competent cells into each reaction
6. **Heat shock**: 4°C (10 min) → 42°C (90 s) → 4°C (2 min) → 37°C outgrowth (1 hr) (off-robot for Flex)
7. **Plating**: Distribute 2.5-4.5 µL spots in a spiral pattern (13 points) across 6-well agar plates, with automatic plate swapping prompts

### Platform Differences
- **OT-2 version** (API 2.8): Uses p10_single + p300_single, Thermocycler Module for on-robot cycling, Temperature Module for reagent cooling
- **Flex version** (API 2.21): Uses flex_1channel_50, Temperature Module Gen2 for reaction plate cooling, no on-robot thermocycler (manual steps via `protocol.pause`)
- **Flex HT (v2) version**: Adds dynamic tip rack calculation with 10% safety margin, multi-tube competent cell support (up to 5 tubes), automated setup messages showing quantities needed, date-stamped output files

### Key Design Decisions
- **Well addressing differs between OT-2 and Flex**: OT-2 uses numeric index (`wells()[n]`), Flex uses alphanumeric (`wells_by_name()['A1']`)
- **Plate name matching**: Flex versions use `in` operator for plate name matching (`'fixed_toolkit_map' in plate_name`), OT-2 uses exact equality
- **Flex versions use semicolon CSV delimiter** (`;`) vs comma delimiter on OT-2 — likely reflecting European locale conventions at Institut Pasteur

## Colony PCR Workflow

### Inputs
- **pcr_deck_map.csv**: 4x6 grid mapping tube rack positions to PCR reagents (water, Taq polymerase, primers)
- **colony_template_map.csv**: 8x12 grid mapping well positions to picked colony names
- **pcr_recipe_to_make.csv**: Each row defines a PCR reaction — name, water source, polymerase, forward primer, reverse primer, colony template

### Protocol Steps
1. **Master mix preparation**: For each unique primer-pair combination, calculate and combine water, polymerase, and primers into a master mix tube
2. **Master mix distribution**: Distribute the mixed reagents into reaction plate wells
3. **Colony template transfer**: Aspirate 1-2 µL from colony wells and add to the corresponding reaction wells
4. **Thermocycling**: Pre-denaturation (98°C, 5 min) → 30 cycles of denaturation/annealing/extension → Final extension (72°C, 5 min) (on-robot for OT-2, off-robot for Flex)

### Platform Differences
- **OT-2 version**: Uses Thermocycler Module for on-robot PCR cycling, p10_single for colony transfer, p300_single for master mix handling
- **Flex version (v1)**: Uses Temperature Module Gen2 at 8°C for reagent cooling, manual thermocycling step, p50_single only. French-language comments indicating Institut Pasteur origin
- **Flex HT (v2) version**: More configurable reaction volumes (15 µL reactions with explicit volume variables), multiple tip racks (3x), improved distribute logic with batch processing, temperature modules at 4°C, individual colony transfers with mixing

### Reagent Volume Calculation
The code groups reactions by primer pair, then calculates total reagent volumes. Volume allocation per reaction:
- OT-2: water = reaction_vol/2 - 3, polymerase = reaction_vol/2, primers = 1 µL each
- Flex HT: water = 2.5 µL, enzyme/buffer = 7.5 µL, primers = 1.5 µL each, colony DNA = 2 µL

## Code Quality Observations

### Strengths
- Clean separation between data preparation (generators) and robot logic (workflows)
- CSV-driven configuration makes the tool accessible to non-programmers
- GUI (tkinter) lowers the barrier to use
- Handles BOM characters from Excel-exported CSVs
- Supports up to 96 parallel reactions
- Spiral plating pattern distributes culture evenly across 6-well plates

### Issues and Technical Debt
1. **Unreachable code**: In `find_dna()`, `raise ValueError` appears after `return None` — the exception is never raised
2. **Missing validation in colony PCR generator**: `check_number_of_combinations()` is a no-op (calculates count but does nothing with it)
3. **Bug in Flex cloning workflow**: `cloning_workflow_Flex.py` loads labware with positional slot argument AND module assignment simultaneously (line 50: `reaction_plate = temp_mod_reaction.load_labware('biorad_96_wellplate_200ul_pcr', 'A1')` — the slot string may be redundant/conflicting)
4. **Code outside `__main__` guard**: All generator files have `messagebox.showinfo("Completed", ...)` at module level (line 182/183), which executes on import
5. **Inconsistent naming**: Project was renamed from "Auto-GG" to "Slowpoke" but some HT generators still reference "Auto-GG" in their welcome messages
6. **Duplicated logic**: CSV parsing, plate map generation, and GUI prompting code is nearly identical across all 5 generator files with no shared module
7. **Operator precedence bug**: In colony PCR OT-2 workflow, line 106: `elif j == 2 or 3:` always evaluates as True due to Python truthiness of `3`. Should be `elif j in (2, 3):`
8. **Same bug in Flex HT colony PCR**: Line 123: `elif j == 2 or 3:` — same issue
9. **Mixed indentation**: Tabs and spaces are mixed throughout, which could cause issues in Python 3

## Technology Stack
- **Language**: Python 3
- **Robot API**: Opentrons Protocol API v2.8 (OT-2) and v2.21 (Flex)
- **GUI**: tkinter (file dialogs and message boxes)
- **Data format**: CSV (comma and semicolon delimited)
- **Hardware**: Opentrons OT-2 and Flex liquid handling robots, Thermocycler Module, Temperature Module Gen2
- **Labware**: Bio-Rad 96-well PCR plates, Corning 6-well plates (agar), Eppendorf 1.5mL tube racks, Opentrons aluminum blocks

## Biological Context
- **Golden Gate assembly** is a one-pot, one-step cloning method using Type IIS restriction enzymes (BsaI) to assemble multiple DNA fragments directionally into a plasmid. The YTK (Yeast Toolkit), STK, and KTK are standardized genetic part kits compatible with this approach.
- **Colony PCR** is a screening method where bacterial colonies are picked directly into PCR reactions to verify successful cloning by amplifying the expected insert.
- Together, these workflows form the complete cycle: build constructs (GG) → transform bacteria → plate → pick colonies → screen (colony PCR).
