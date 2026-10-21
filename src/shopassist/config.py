import os
from pathlib import Path

from dotenv import load_dotenv

load_dotenv()

ROOT_DIR = Path(__file__).resolve().parents[2]

# Paths (the environment variables let the evaluation use a throw-away database)
DB_PATH = os.getenv("SHOPASSIST_DB", str(ROOT_DIR / "data" / "db" / "shopassist.db"))
CHECKPOINT_PATH = os.getenv("SHOPASSIST_CHECKPOINTS", str(ROOT_DIR / "data" / "db" / "checkpoints.db"))
EVAL_DATASET_PATH = ROOT_DIR / "data" / "evaluation" / "scenarios.json"
RESULTS_PATH = ROOT_DIR / "experiments" / "results.json"

# Models
LLM_MODEL = "openai/gpt-oss-120b"

# Workflow
MAX_ATTEMPTS = 3          # how many times a failed action is tried before the ticket is marked FAILED
SUPPORT_ROLE = "support"  # demo authorisation: value of the X-Role header needed to approve or reject
