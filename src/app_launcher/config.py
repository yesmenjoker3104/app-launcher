from pathlib import Path
import json

DEFAULT_EXCLUDED_DIRECTORIES = [
    "Windows",
    "Program Files",
    "Program Files (x86)",
    "ProgramData"
]

def load_excluded_directories(config: Path) -> set[str]:
    if not config.exists():
        return {
            name.casefold()
            for name in DEFAULT_EXCLUDED_DIRECTORIES
        }
    with config.open("r", encoding="utf-8") as f:
        data = json.load(f)

    names = data.get("excluded_directories", [])
    return {
        name.casefold() for name in names
    }