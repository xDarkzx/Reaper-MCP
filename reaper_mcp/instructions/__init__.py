from pathlib import Path


def load_instructions() -> str:
    """Load the core instruction file."""
    filepath = Path(__file__).parent / "00_core.md"
    return filepath.read_text(encoding="utf-8")
