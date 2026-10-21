"""Workflow evaluation: runs the scenarios in data/evaluation/scenarios.json through the real graph.

It uses a throw-away database, so it never touches your tickets. The keyword classifier needs no API key.

Examples:
    python run_evaluation.py                          # keyword classifier
    python run_evaluation.py --classifiers keyword llm   # also try the LLM classifier (needs GROQ_API_KEY)
"""
import argparse
import os
import tempfile

# Point the app at a temporary database BEFORE importing it (see config.py)
_folder = tempfile.mkdtemp(prefix="shopassist_eval_")
os.environ["SHOPASSIST_DB"] = os.path.join(_folder, "eval.db")
os.environ["SHOPASSIST_CHECKPOINTS"] = ":memory:"

from src.shopassist import database  # noqa: E402
from src.shopassist.evaluation.dataset import load_dataset  # noqa: E402
from src.shopassist.evaluation.experiments import load_results, save_results  # noqa: E402
from src.shopassist.evaluation.runner import CLASSIFIERS, evaluate_workflow  # noqa: E402
from src.shopassist.pipeline import create_workflow  # noqa: E402


def show(value, as_percent=True):
    if value is None:
        return "n/a"
    return f"{value:.0%}" if as_percent else f"{value:.2f}"


def merge_with_previous(new_results):
    """Keep earlier results for classifiers we didn't re-run."""
    previous = load_results().get("workflow_evaluation", {}).get("results", [])
    new_names = {r["classifier"] for r in new_results}
    kept = [r for r in previous if r["classifier"] not in new_names]
    return sorted(kept + new_results, key=lambda r: CLASSIFIERS.index(r["classifier"]))


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--classifiers", nargs="+", default=["keyword"], choices=CLASSIFIERS)
    args = parser.parse_args()

    dataset = load_dataset()
    new_results = []
    for classifier in args.classifiers:
        print(f"Evaluating the {classifier} classifier ({len(dataset)} scenarios)...")
        database.reset_db()                                  # same starting data for every classifier
        workflow = create_workflow(":memory:")
        new_results.append(evaluate_workflow(workflow, dataset, classifier))

    results = merge_with_previous(new_results)

    print(f"\n{'classifier':<12}{'intent':<9}{'outcome':<9}{'safety':<9}{'pass':<7}{'latency':<9}{'errors'}")
    print("-" * 60)
    for r in results:
        print(f"{r['classifier']:<12}{show(r['intent_accuracy']):<9}{show(r['outcome_accuracy']):<9}{show(r['safety']):<9}"
              f"{show(r['pass_rate']):<7}{show(r['avg_latency_s'], False) + 's':<9}{r['errors']}")

    for r in new_results:
        if r["errors"]:
            print(f"\nWARNING: {r['classifier']} skipped {r['errors']} scenarios, so its numbers are incomplete.")
        print(f"\nPass rate by category ({r['classifier']}):")
        for name, value in r["by_category"].items():
            print(f"  {name:<18}{show(value)}")
        for failure in r["failures"]:
            print(f"\n[{r['classifier']}] FAILED {failure['id']} ({failure['category']}): {failure['question']}")
            print(f"   expected: {failure['expected']}")
            print(f"   got:      {failure['got']}")

    save_results("workflow_evaluation", {"scenarios": len(dataset), "results": results})
    print("\nSaved to experiments/results.json")


if __name__ == "__main__":
    main()
