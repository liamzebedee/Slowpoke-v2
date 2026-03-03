# Analysis: Slowpoke — An Automated Golden Gate Cloning Workflow for Opentrons OT-2 and Flex

**Citation:** Malcı, K.\*; Meng, F.\*; Galez, H.; Franja Da Silva, A.; Caro-Astorga, J.; Batt, G.; Ellis, T. *ACS Synth. Biol.* 2026, 15, 511–521. DOI: 10.1021/acssynbio.5c00629

---

## 1. Problem Statement

DNA assembly is a routine but labor-intensive process in synthetic biology. Increasing demands for standardization, high-throughput capacity, and error-free execution are driving the need for accessible, automated solutions. Existing automation tools either require expensive biofoundry-level infrastructure, depend on non-standard cloning methods (e.g., BASIC), or lack user-friendly interfaces. Many synthetic biology labs now own low-cost Opentrons OT-2 or Flex liquid-handling robots but lack software to automate Golden Gate Assembly workflows on them.

## 2. What is Slowpoke?

Slowpoke is an open-source, user-friendly software tool that automates Golden Gate Assembly-based cloning on Opentrons OT-2 and Flex platforms. It provides:

- **Two complementary workflows:**
  1. **Golden Gate Cloning Workflow** — automates DNA assembly reaction setup, *E. coli* transformation, and plating
  2. **Colony PCR Workflow** — automates colony PCR screening of resulting transformants

- **Two interfaces:**
  1. **CLI / offline Python script** (`generator.py`) — runs entirely offline via command line
  2. **Web-based GUI** (Streamlit app at https://slowpoke.streamlit.app/) — no-code, browser-based protocol generation via drag-and-drop CSV file uploads

- **Code repository:** https://github.com/Tom-Ellis-Lab/Slowpoke

## 3. How It Works

### Input
Users provide three CSV files for the cloning workflow:
1. **Fixed toolkit map** — defines the standardized genetic toolkit (e.g., MoClo YTK or STK plate layouts, typically 96-well)
2. **Custom parts map** — user-designed parts compatible with the toolkit
3. **Combination file** — specifies which parts to assemble and how

For colony PCR, users provide colony template positions, PCR deck maps, and reaction recipes.

### Protocol Generation
- The Python script (`generator.py`) or GUI reads the CSVs, generates plate maps, and compiles an Opentrons-compatible protocol (`.py` file) using the Opentrons API (v2.0 for OT-2, v2.21 for Flex).
- Uses only standard Python libraries (tkinter, csv, json, os, sys) — no external packages required.
- The output protocol can be directly uploaded to the robot and executed without modification.

### Automated Steps
The robot executes:
1. **DNA & enzyme/buffer transfer** — dispenses DNA parts, restriction enzyme (BsaI-HF), T4 ligase, and buffer into reaction wells
2. **Golden Gate reaction** — thermocycling (25 cycles of 37°C/2min + 16°C/5min, then 60°C/5min denaturation) in the on-board thermocycler or benchtop PCR machines
3. **Transformation** — direct transformation of *E. coli* (heat shock at 42°C or chemical transformation)
4. **Plating** — dispensing transformation mix onto 6-well LB agar plates with antibiotics (calibrated drop height ~5mm, 13 unique x-y positions per well)
5. **Colony PCR** — master mix dispensing, colony template addition, thermocycling

### Manual Steps Still Required
- Colony picking (most labor-intensive remaining step)
- Sealing PCR plates in OT-2 thermocycler module
- Transferring PCR tubes to benchtop thermocycler (Flex)
- Incubation, strain storage, and plasmid purification

## 4. Experimental Validation

### 4.1 YTK Assemblies on OT-2 (3-part, Level 1 TUs)
- Assembled 19 different promoter-sfGFP-terminator transcription units using the MoClo Yeast Toolkit (YTK)
- Backbone: pWS064 (LEU2 marker, GFP dropout cassette for visual screening)
- **Result:** 17/17 positive colonies by colony PCR (after excluding 2 constructs with no white colonies). All 19 PCR products showed expected band sizes.
- Flow cytometry in *S. cerevisiae* confirmed expected expression patterns (strong promoters like pTDH3 and pCCW12 gave high fluorescence; weak promoters like pREV1 and pRAD27 gave low signals).

### 4.2 STK Assemblies on OT-2 (5-part, Level 1 TUs)
- Assembled 3 GFP-expressing constructs using SubtiToolKit (STK) for *Bacillus subtilis*
- 5-part assemblies: promoter + RBS + GFPmut3b + terminator into backbone STK202 (LacZ dropout, blue-white screening)
- **Result:** 8/13 colony PCR-screened colonies showed correct bands (~60% efficiency). Lower than YTK but comparable to manual methods.
- Reduced efficiency attributed to increased part number and *E. coli*-active parts from *B. subtilis*.
- GFP expression in *B. subtilis* confirmed expected promoter/RBS strength patterns.

### 4.3 YTK Assemblies on Flex (3-part)
- Adapted the OT-2 protocol for Opentrons Flex (larger deck, integrated plate handling, no thermocycler module — used benchtop PCR machines)
- Assembled 6 promoter-sfGFP TUs
- **Result:** 11/12 colony PCR-screened colonies showed expected amplicons. Expression patterns in *S. cerevisiae* consistent with OT-2 results.

### 4.4 High-Throughput Validation on Flex (6-part, 62 assemblies)
- Constructed 62 plasmids, each a 6-part YTK assembly encoding secreted recombinant proteins (endolysin, scFv) with various promoters, signal peptides, and tags
- >5000 robot-executed instructions
- **Results:**
  - 89% (55/62) produced white colonies on plates
  - 100% (55/55) correct bands on colony PCR
  - 100% (22/22) correct by Sanger sequencing (subset verified)
  - 7 failed assemblies all contained endolysin CDS (likely toxic)
  - **96% success rate (55/57) when excluding toxic assemblies**

### 4.5 Time and Cost Analysis (62-assembly workflow)
- **Total time:** <4 days (89 hours total; 18.6h user time, 72.9h machine time)
- **User time per assembly:** ~18 minutes
- **Reagent cost:** €803 total (€12.9 per construct)
- Major cost drivers: Golden Gate enzyme mix BsaI (50%), Opentrons tips (14%), purification kits (12%)

## 5. Comparison to Existing Tools

| Tool | Platform | Cloning Method | Workflow Coverage | Interface |
|------|----------|---------------|-------------------|-----------|
| **Slowpoke** | OT-2 & Flex | MoClo/Golden Gate | Assembly → transformation → plating → colony PCR | GUI + offline app |
| AssemblyTron | OT-2 | MoClo/GG + in vivo | Assembly only | Python package |
| DNA-BOT | OT-2 | BASIC | Assembly → transformation → plating | Offline app |
| DNAda | Advanced biofoundry | J5-directed | Design → worklist → construction → tracking | GUI + CLI |
| PlasmidMaker | Advanced biofoundry | PfAgo-based | Build → transformation → test → stock | GUI + CLI + code |
| RoboMoClo | Advanced biofoundry | MoClo/GG | Multilevel GG assembly | Hardware-integrated |

**Slowpoke's differentiators:**
- Only tool covering the full pipeline (assembly + transformation + plating + colony PCR) on low-cost platforms
- Compatible with multiple MoClo/Golden Gate toolkits (YTK, STK, and extensible to others)
- Works on both OT-2 and the newer Flex platform
- Offers both CLI and no-code GUI
- No external Python packages required

## 6. Extensibility and Future Directions

- Can be extended to other DNA assembly methods (Gibson Assembly, in vivo recombination) as long as the toolkit follows a standardized, interchangeable parts scheme
- Integrates with InSillyClo (a complementary web tool for designing large-scale cloning maps)
- Could be combined with open-source colony pickers (e.g., Marburg iGEM 2019 neural-network-based picker, Imperial College PiCam-based picker) to create fully automated end-to-end cloning pipelines
- The protocol can scale: demonstrated 288 colony PCR reactions (3 full 96-well plates) in parallel using 2 additional benchtop thermocyclers

## 7. Technical Details

### Opentrons API Compatibility
- OT-2: Opentrons API 2.0
- Flex: Opentrons API 2.21
- Scripts developed in Spyder 5.4

### Golden Gate Reaction Conditions
- **OT-2:** 10 µL reaction volume, 50 fmol entry-level plasmids, 0.5 µL BsaI (10 units), 0.5 µL T4 ligase (200 units) in 1× T4 ligase buffer
- **Flex:** 12 µL reaction volume, 25 fmol plasmids, 1.2 µL Golden Gate Enzyme Mix in 1× T4 ligase buffer

### Colony PCR
- Master mix: water + colony PCR primers + 2× PCR master mix (Phire Plant Direct or DreamTaq)
- 9 µL master mix + 1 µL colony template (OT-2) or 2 µL (Flex)

### Transformation
- *E. coli:* NEB Turbo Competent or NEB 5-α F'Iq cells, heat shock
- Plating: 4.5 µL droplets (OT-2) or 2.5 µL (Flex) on 6-well LB agar plates

### Yeast Transformation
- Lithium acetate (LiOAc) method for *S. cerevisiae* strain BY4741
- Selection on synthetic defined medium without leucine (LEU2 marker)

## 8. Limitations

- Colony picking remains manual (most labor-intensive step)
- Some manual intervention required (sealing PCR plates, transferring tubes)
- Assembly efficiency may decrease with increasing part complexity and when *E. coli*-active parts are involved
- Toxic gene products can cause assembly failures (7/62 in high-throughput test)
- Strain storage and plasmid purification still performed manually (accounts for ~half of user time)

## 9. Key Metrics Summary

| Metric | Value |
|--------|-------|
| YTK 3-part assembly efficiency (OT-2) | 17/17 (100% colony PCR) |
| STK 5-part assembly efficiency (OT-2) | 8/13 (~60% colony PCR) |
| YTK 3-part assembly efficiency (Flex) | 11/12 (~92% colony PCR) |
| High-throughput 6-part efficiency (Flex) | 55/57 (96%, excluding toxic) |
| Total workflow time (62 assemblies) | <4 days |
| User time per assembly | ~18 min |
| Cost per construct | €12.9 |
| Max simultaneous assemblies | 96 (Golden Gate) + 288 (colony PCR) |
