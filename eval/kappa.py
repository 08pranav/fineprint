"""Inter-annotator agreement (Cohen's kappa) for your own gold labels.

Step 1. Make one labelling sheet per document, and give each teammate a copy:
    python eval/kappa.py sheet data/real/hdfc_card.txt > annotator_A.csv
Step 2. Each person fills the 'label' column alone, with a category id or 'none'.
Step 3. Compare:
    python eval/kappa.py score annotator_A.csv annotator_B.csv

Kappa corrects raw agreement for agreement expected by chance:
    kappa = (p_observed - p_expected) / (1 - p_expected)
Above 0.8 is very strong agreement, 0.6-0.8 substantial, 0.4-0.6 moderate.
Disagreements are printed so you can discuss them and settle the final gold label.
"""
from __future__ import annotations

import csv
import sys
from collections import Counter
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "src"))

from fineprint.ingest.pii import mask_pii  # noqa: E402
from fineprint.ingest.segmenter import segment  # noqa: E402
from fineprint.risk.taxonomy import CATEGORIES  # noqa: E402


def cohen_kappa(a: list[str], b: list[str]) -> float:
    if len(a) != len(b) or not a:
        raise ValueError("Both annotators must label the same, non-empty list of clauses.")
    n = len(a)
    observed = sum(x == y for x, y in zip(a, b)) / n
    ca, cb = Counter(a), Counter(b)
    expected = sum(ca[k] * cb[k] for k in set(a) | set(b)) / (n * n)
    return 1.0 if expected == 1 else (observed - expected) / (1 - expected)


def make_sheet(path: str) -> None:
    text, _ = mask_pii(Path(path).read_text(encoding="utf-8"))
    writer = csv.writer(sys.stdout)
    writer.writerow(["doc", "clause_id", "clause_text", "label"])
    for c in segment(text):
        writer.writerow([Path(path).stem, c.id, c.text, ""])
    print("# allowed labels: none, " + ", ".join(c.id for c in CATEGORIES), file=sys.stderr)


def read_labels(path: str) -> dict[tuple[str, str], str]:
    with open(path, encoding="utf-8") as fh:
        return {(r["doc"], r["clause_id"]): (r["label"].strip() or "none") for r in csv.DictReader(fh)}


def score(path_a: str, path_b: str) -> None:
    la, lb = read_labels(path_a), read_labels(path_b)
    keys = sorted(set(la) & set(lb))
    a = [la[k] for k in keys]
    b = [lb[k] for k in keys]
    k = cohen_kappa(a, b)
    agree = sum(x == y for x, y in zip(a, b))
    print(f"Clauses compared: {len(keys)}  Raw agreement: {agree}/{len(keys)} ({agree / len(keys):.0%})  Cohen's kappa: {k:.3f}")
    for key, x, y in zip(keys, a, b):
        if x != y:
            print(f"  disagree {key[0]} {key[1]}: A={x}  B={y}")


if __name__ == "__main__":
    if len(sys.argv) >= 3 and sys.argv[1] == "sheet":
        make_sheet(sys.argv[2])
    elif len(sys.argv) == 4 and sys.argv[1] == "score":
        score(sys.argv[2], sys.argv[3])
    else:
        print(__doc__)
