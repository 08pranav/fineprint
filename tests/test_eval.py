import json
import subprocess
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "eval"))

from kappa import cohen_kappa  # noqa: E402


def test_kappa_known_values():
    assert cohen_kappa(["a", "b", "a", "b"], ["a", "b", "a", "b"]) == 1.0
    assert cohen_kappa(["a", "a", "b", "b"], ["a", "b", "a", "b"]) == pytest.approx(0.0)


def test_gold_anchors_exist_in_their_documents():
    gold = json.loads((ROOT / "data/eval/gold.json").read_text(encoding="utf-8"))
    for doc in gold["documents"]:
        text = " ".join((ROOT / "data/samples" / doc["file"]).read_text(encoding="utf-8").split())
        for label in doc["labels"]:
            assert " ".join(label["anchor"].split()) in text, (doc["id"], label["anchor"])


def test_rules_baseline_does_not_regress(tmp_path):
    """A quality gate for CI: the rules baseline must stay above these scores."""
    out = subprocess.run([sys.executable, str(ROOT / "eval/run_eval.py"), "--methods", "rules", "--out", str(tmp_path)],
                         capture_output=True, text=True, timeout=120)
    assert out.returncode == 0, out.stderr
    results = json.loads((tmp_path / "results.json").read_text())
    rules = results["methods"]["rules"]
    assert rules["dev"]["f1"] >= 0.9
    assert rules["test"]["f1"] >= 0.75
