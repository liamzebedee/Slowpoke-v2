#!/usr/bin/env python3
"""Bundle a Slowpoke protocol into a single file for Opentrons App upload.

Opentrons App requires self-contained .py files. This script inlines the
slowpoke package imports so protocols can be uploaded directly.

Usage:
    python bundle.py protocols/cloning_ot2.py > cloning_ot2_bundled.py
"""

import re
import sys
from pathlib import Path

SLOWPOKE_DIR = Path(__file__).parent / "slowpoke"


def bundle(protocol_path: Path) -> str:
    protocol = protocol_path.read_text()

    # Find slowpoke module imports in order
    import_pattern = re.compile(r"^from slowpoke\.(\w+) import .+$", re.MULTILINE)
    modules_needed = list(dict.fromkeys(import_pattern.findall(protocol)))

    # Read and inline each module
    inlined: list[str] = []
    for mod_name in modules_needed:
        source = (SLOWPOKE_DIR / f"{mod_name}.py").read_text()
        # Strip relative imports — single-line and multi-line (parenthesized)
        source = re.sub(
            r"^from \.\w+ import \(.*?\)\n", "", source,
            flags=re.MULTILINE | re.DOTALL,
        )
        source = re.sub(r"^from \.\w+ import[^\n]+\n", "", source, flags=re.MULTILINE)
        inlined.append(source)

    # Remove slowpoke imports from protocol
    protocol = import_pattern.sub("", protocol)
    # Clean up blank lines left by removed imports
    protocol = re.sub(r"\n{3,}", "\n\n", protocol)

    return "\n".join(inlined) + "\n" + protocol


if __name__ == "__main__":
    if len(sys.argv) != 2:
        print(f"Usage: {sys.argv[0]} <protocol.py>", file=sys.stderr)
        sys.exit(1)
    print(bundle(Path(sys.argv[1])))
