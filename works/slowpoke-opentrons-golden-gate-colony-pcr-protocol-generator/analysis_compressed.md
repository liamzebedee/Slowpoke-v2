# Slowpoke - Compressed Analysis

## What It Is
- Protocol generator for Opentrons liquid-handling robots (OT-2 and Flex)
- Automates two synthetic biology workflows: Golden Gate cloning and colony PCR screening
- Developed at Imperial College London, adapted for Flex at Institut Pasteur

## Architecture
- Two-phase code generation: GUI generator reads CSVs, concatenates data + workflow template into a single runnable .py protocol
- Generators use tkinter file dialogs for user input
- Workflow templates contain Opentrons API calls referencing globals injected by the generator
- CSV-driven: plate maps and reaction lists defined in spreadsheets

## Cloning Workflow (Golden Gate Assembly)
- Combines multiple DNA parts into target plasmids using Type IIS restriction enzymes
- Steps: buffer/water dispensing → DNA part distribution → enzyme addition → thermocycling (37/16°C x25) → competent cell addition → heat shock → spiral plating on 6-well agar plates
- Supports up to 96 parallel assemblies
- OT-2 version does thermocycling on-robot; Flex versions require manual off-robot cycling

## Colony PCR Workflow
- Screens picked colonies by PCR amplification to verify successful cloning
- Groups reactions by primer pair to prepare shared master mixes
- Steps: master mix prep → distribution → colony template transfer → thermocycling (30 cycles)
- Supports up to 96+ reactions (overflow to second plate)

## Platform Variants (x3 each workflow)
- **OT-2**: Thermocycler Module on-robot, p10+p300 pipettes, API 2.8
- **Flex**: Temperature Module Gen2 only, flex_1channel_50 pipette, API 2.21, manual thermocycling
- **Flex HT (v2)**: Dynamic tip rack calculation, multi-tube reagent support, configurable volumes, automated setup messages

## Key Files
- 5 generator scripts (GUI + CSV parsing + protocol file output)
- 6 workflow templates (robot execution logic)
- 6 CSV example files (plate maps, combinations, recipes)

## Notable Bugs
- `elif j == 2 or 3:` always True (should be `elif j in (2, 3):`) — affects PCR volume calculation
- `find_dna()` has unreachable `raise ValueError` after `return None`
- `check_number_of_combinations()` in colony PCR generators is a no-op
- `messagebox.showinfo("Completed", ...)` outside `__main__` guard — executes on import
- Inconsistent branding: some files say "Auto-GG", others "Slowpoke"

## Technical Debt
- Near-identical code duplicated across 5 generator scripts with no shared module
- Mixed tab/space indentation
- Flex versions use semicolon CSV delimiter (European locale) vs comma on OT-2
- OT-2 uses numeric well indexing, Flex uses alphanumeric — different `find_dna()` implementations
