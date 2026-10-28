"""Evaluate FinePrint's risk detection against hand-labelled gold data.

    python eval/run_eval.py                    # every method available (rules always; llm + hybrid if a key is set)
    python eval/run_eval.py --methods rules    # just the baseline
    python eval/run_eval.py --gold data/eval/real_gold.json --docs data/real   # your own annotated documents

Writes eval/results.md and eval/results.json.

Scoring: a predicted flag is a true positive when a gold label has the same category and its anchor text
is inside the flagged clause. Each gold label can be matched once. We report precision, recall and F1 per
category and overall (micro-averaged), separately for the dev split (seen while writing rules) and the
test split (not used for tuning). Also: accuracy of the pre-filled loan numbers, and readability of the
explanations at the Simple and Expert levels.
"""
from __future__ import annotations

import argparse
import json
import re
import sys
import time
from collections import defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "src"))

from fineprint.explain.explainer import explain  # noqa: E402
from fineprint.explain.readability import flesch  # noqa: E402
from fineprint.extract.context import extract_context  # noqa: E402
from fineprint.ingest.pii import mask_pii  # noqa: E402
from fineprint.ingest.segmenter import segment  # noqa: E402
from fineprint.llm.client import get_llm  # noqa: E402
from fineprint.risk.pipeline import detect  # noqa: E402
from fineprint.risk.taxonomy import CATEGORIES  # noqa: E402
from fineprint.schemas import LoanContext  # noqa: E402


def norm(s: str) -> str:
    return re.sub(r"\s+", " ", s).strip().lower()


def prf(tp: int, fp: int, fn: int) -> tuple[float, float, float]:
    p = tp / (tp + fp) if tp + fp else 0.0
    r = tp / (tp + fn) if tp + fn else 0.0
    f = 2 * p * r / (p + r) if p + r else 0.0
    return p, r, f


def score_document(doc: dict, clauses, flags) -> tuple[dict, list[str]]:
    """Return per-category counts {cat: [tp, fp, fn]} and readable error notes."""
    counts: dict[str, list[int]] = defaultdict(lambda: [0, 0, 0])
    notes: list[str] = []
    gold = []
    for label in doc["labels"]:
        owners = [c.id for c in clauses if norm(label["anchor"]) in norm(c.text)]
        if not owners:
            notes.append(f"GOLD ERROR {doc['id']}: anchor not found in any clause: {label['anchor']!r}")
            continue
        gold.append({"category": label["category"], "clauses": set(owners), "matched": False, "anchor": label["anchor"]})
    for f in flags:
        match = next((g for g in gold if not g["matched"] and g["category"] == f.category and f.clause_id in g["clauses"]), None)
        if match:
            match["matched"] = True
            counts[f.category][0] += 1
        else:
            counts[f.category][1] += 1
            text = next(c.text for c in clauses if c.id == f.clause_id)
            notes.append(f"FP  {doc['id']} {f.category:<20} {f.clause_id}: {text[:90]}")
    for g in gold:
        if not g["matched"]:
            counts[g["category"]][2] += 1
            notes.append(f"FN  {doc['id']} {g['category']:<20} {g['anchor'][:90]}")
    return counts, notes


def context_accuracy(doc: dict, clauses, masked: str) -> tuple[int, int, list[str]]:
    want = doc.get("context") or {}
    got = extract_context(clauses, masked)
    right = total = 0
    notes = []
    for key in ("principal", "annual_rate", "tenure_months"):
        if want.get(key) is None:
            continue
        total += 1
        value = getattr(got, key)
        if value is not None and abs(float(value) - float(want[key])) < 0.01:
            right += 1
        else:
            notes.append(f"CTX {doc['id']} {key}: expected {want[key]}, got {value}")
    return right, total, notes


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--gold", default=str(ROOT / "data/eval/gold.json"))
    ap.add_argument("--docs", default=str(ROOT / "data/samples"))
    ap.add_argument("--methods", default="auto", help="comma list of rules,llm,hybrid, or auto")
    ap.add_argument("--out", default=str(ROOT / "eval"))
    args = ap.parse_args()

    gold = json.loads(Path(args.gold).read_text(encoding="utf-8"))
    llm = get_llm()
    methods = ["rules", "llm", "hybrid"] if (args.methods == "auto" and llm) else ["rules"] if args.methods == "auto" else args.methods.split(",")
    if llm is None and any(m != "rules" for m in methods):
        print("No LLM configured (set LLM_API_KEY and LLM_MODEL); evaluating rules only.")
        methods = ["rules"]

    prepared = []
    ctx_right = ctx_total = 0
    ctx_notes: list[str] = []
    for doc in gold["documents"]:
        text = (Path(args.docs) / doc["file"]).read_text(encoding="utf-8")
        masked, _ = mask_pii(text)
        clauses = segment(masked)
        r, t, n = context_accuracy(doc, clauses, masked)
        ctx_right, ctx_total, ctx_notes = ctx_right + r, ctx_total + t, ctx_notes + n
        ctx = LoanContext(**{**extract_context(clauses, masked).model_dump(), **{k: v for k, v in (doc.get("context") or {}).items() if v is not None}})
        prepared.append((doc, clauses, ctx))

    results: dict = {"methods": {}, "context_accuracy": {"right": ctx_right, "total": ctx_total}, "documents": len(prepared),
                     "labels": sum(len(d["labels"]) for d in gold["documents"])}
    all_notes: dict[str, list[str]] = {}
    sample_flags = {}
    for method in methods:
        per_split: dict[str, dict[str, list[int]]] = {"dev": defaultdict(lambda: [0, 0, 0]), "test": defaultdict(lambda: [0, 0, 0])}
        notes: list[str] = []
        started = time.time()
        for doc, clauses, ctx in prepared:
            flags, _ = detect(clauses, ctx, method=method, llm=llm if method != "rules" else None)
            if method == methods[-1]:
                sample_flags[doc["id"]] = (flags, ctx)
            counts, n = score_document(doc, clauses, flags)
            notes += n
            for cat, (tp, fp, fn) in counts.items():
                bucket = per_split[doc.get("split", "dev")][cat]
                bucket[0] += tp
                bucket[1] += fp
                bucket[2] += fn
        out = {"seconds": round(time.time() - started, 1)}
        for split in ("dev", "test", "all"):
            cats = defaultdict(lambda: [0, 0, 0])
            for s in (("dev", "test") if split == "all" else (split,)):
                for cat, v in per_split[s].items():
                    for i in range(3):
                        cats[cat][i] += v[i]
            tp, fp, fn = (sum(v[i] for v in cats.values()) for i in range(3))
            p, r, f = prf(tp, fp, fn)
            out[split] = {"precision": round(p, 3), "recall": round(r, 3), "f1": round(f, 3), "tp": tp, "fp": fp, "fn": fn,
                          "per_category": {c: dict(zip(("tp", "fp", "fn"), v)) for c, v in sorted(cats.items())}}
        results["methods"][method] = out
        all_notes[method] = notes

    # Readability of explanations at two levels, on flags from the last method run.
    read = {}
    for level in ("simple", "expert"):
        texts = []
        for _doc_id, (flags, ctx) in sample_flags.items():
            explain(flags, ctx, level=level, language="en", llm=llm if methods[-1] != "rules" else None)
            texts += [f.explanation for f in flags]
        read[level] = flesch(" ".join(texts))
    results["readability"] = read

    Path(args.out).mkdir(parents=True, exist_ok=True)
    (Path(args.out) / "results.json").write_text(json.dumps(results, indent=2), encoding="utf-8")
    md = render_markdown(results, all_notes, ctx_notes, llm)
    (Path(args.out) / "results.md").write_text(md, encoding="utf-8")
    print(md)


def render_markdown(results: dict, notes: dict, ctx_notes: list[str], llm) -> str:
    lines = ["# FinePrint evaluation results", ""]
    lines.append(f"{results['documents']} documents, {results['labels']} gold risk labels. Model: {getattr(llm, 'name', 'none (rules only)')}.")
    lines.append("")
    lines.append("| Method | Split | Precision | Recall | F1 | TP | FP | FN |")
    lines.append("| --- | --- | --- | --- | --- | --- | --- | --- |")
    for method, out in results["methods"].items():
        for split in ("dev", "test", "all"):
            s = out[split]
            lines.append(f"| {method} | {split} | {s['precision']:.2f} | {s['recall']:.2f} | {s['f1']:.2f} | {s['tp']} | {s['fp']} | {s['fn']} |")
    lines += ["", "## Per category (all documents)", ""]
    methods = list(results["methods"])
    lines.append("| Category | " + " | ".join(f"{m} F1" for m in methods) + " |")
    lines.append("| --- | " + " | ".join("---" for _ in methods) + " |")
    for cat in [c.id for c in CATEGORIES]:
        row = []
        for m in methods:
            v = results["methods"][m]["all"]["per_category"].get(cat)
            row.append("—" if not v else f"{prf(v['tp'], v['fp'], v['fn'])[2]:.2f}")
        lines.append(f"| {cat} | " + " | ".join(row) + " |")
    ca = results["context_accuracy"]
    lines += ["", f"Pre-filled loan numbers correct: {ca['right']} of {ca['total']}."]
    rd = results["readability"]
    lines += ["", f"Flesch reading ease of explanations (higher is easier): Simple = {rd.get('simple')}, Expert = {rd.get('expert')}."]
    lines += ["", "## Errors (last method)", "", "```"]
    last = methods[-1]
    lines += notes[last] + ctx_notes or ["none"]
    lines += ["```", ""]
    return "\n".join(lines)


if __name__ == "__main__":
    main()
