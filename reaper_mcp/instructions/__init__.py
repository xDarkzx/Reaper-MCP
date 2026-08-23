from pathlib import Path
from typing import Sequence

_INSTRUCTIONS_DIR = Path(__file__).parent

# Standard alias map for composable instruction packs
INSTRUCTION_PACKS: dict[str, str] = {
    "core": "00_critical_rules.md",
    "critical_rules": "00_critical_rules.md",
    "composition": "10_composition.md",
    "automation": "20_automation.md",
    "mixing": "30_mixing.md",
    "editing": "40_editing.md",
    "postproduction": "50_postproduction.md",
    "bbc_spitfire": "60_bbc_spitfire.md",
    "styles": "70_style_cheat_sheet.md",
    "style_cheat_sheet": "70_style_cheat_sheet.md",
}

# Order of packs when composing the full document
_DEFAULT_PACK_ORDER: list[str] = [
    "00_critical_rules.md",
    "10_composition.md",
    "20_automation.md",
    "30_mixing.md",
    "40_editing.md",
    "50_postproduction.md",
    "60_bbc_spitfire.md",
    "70_style_cheat_sheet.md",
]


def load_instructions(packs: Sequence[str] | None = None) -> str:
    """Load and compose instruction packs.

    If `packs` is None, loads all standard packs in default order.
    If `packs` is provided (e.g. `["core", "mixing", "automation"]`), only
    the specified packs are loaded and joined with double newlines.
    Always ensures critical rules are placed at the beginning if present.
    """
    if packs is None:
        selected_files = _DEFAULT_PACK_ORDER
    else:
        resolved_files: list[str] = []
        for p in packs:
            filename = INSTRUCTION_PACKS.get(p.lower().strip())
            if not filename:
                # Check if raw filename or stem was passed
                raw = p.strip()
                if not raw.endswith(".md"):
                    raw_md = f"{raw}.md"
                else:
                    raw_md = raw
                if (_INSTRUCTIONS_DIR / raw_md).is_file():
                    filename = raw_md
            if filename and filename not in resolved_files:
                resolved_files.append(filename)
        selected_files = resolved_files if resolved_files else _DEFAULT_PACK_ORDER

    sections: list[str] = []
    for fname in selected_files:
        path = _INSTRUCTIONS_DIR / fname
        if path.is_file():
            text = path.read_text(encoding="utf-8").strip()
            if text:
                sections.append(text)

    # Fallback to legacy single file if directory files are missing
    if not sections:
        legacy = _INSTRUCTIONS_DIR / "00_core.md"
        if legacy.is_file():
            return legacy.read_text(encoding="utf-8").strip()

    return "\n\n---\n\n".join(sections)
