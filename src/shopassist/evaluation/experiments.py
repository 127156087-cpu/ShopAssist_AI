import json
from pathlib import Path

from src.shopassist.config import RESULTS_PATH


def load_results(path: Path = RESULTS_PATH) -> dict:
    return json.loads(Path(path).read_text()) if Path(path).exists() else {}


def save_results(section: str, data, path: Path = RESULTS_PATH) -> None:
    """Store one section of results (so the web UI can show it later)."""
    results = load_results(path)
    results[section] = data
    Path(path).parent.mkdir(parents=True, exist_ok=True)
    Path(path).write_text(json.dumps(results, indent=2))
