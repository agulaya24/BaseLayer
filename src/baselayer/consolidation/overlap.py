"""Stage `overlap`: pairwise claim overlap by shared evidence (mechanical), plus the
interface and prompt for the model-judged SAME / FACET / DISTINCT step. The stage itself
calls no model; the duplicate judge builder (`judge.py`) runs the prompt.

Output overlap.json = {"pairs": [{"a","b","shared","jaccard"}], "distribution": {...}}
listing every pair of claims that cite at least `min_shared` common fact ids.

Evidence overlap alone is a weak duplicate signal: on a measured specification under 1% of
claim pairs shared any fact and none reached the default Jaccard of 0.5, because authoring
shards see disjoint facts. Meaning-level duplicates need the judge, which is why the
judge sits behind an interface: its tasks are built here, the builder or any other
PairJudge writes the verdicts, they are read back from a file (`load_judgements`), and
the dedupe stage consumes them.
"""
from __future__ import annotations

import itertools
import json
import random
from collections import Counter
from typing import Protocol

LABELS = ("SAME", "FACET", "DISTINCT")


def build(claims_doc: dict, min_shared: int = 1) -> dict:
    claims = claims_doc["claims"]
    S = {c["id"]: set(c["fact_ids"]) for c in claims}
    ids = [c["id"] for c in claims]
    pairs = []
    n_pairs = 0
    for a, b in itertools.combinations(ids, 2):
        n_pairs += 1
        shared = S[a] & S[b]
        if len(shared) >= max(1, min_shared):
            union = S[a] | S[b]
            pairs.append({"a": a, "b": b, "shared": len(shared),
                          "jaccard": round(len(shared) / len(union), 6) if union else 0.0})
    pairs.sort(key=lambda p: (-p["jaccard"], -p["shared"], p["a"], p["b"]))
    per_fact = Counter(f for s in S.values() for f in s)
    return {
        "pairs": pairs,
        "distribution": {
            "claims": len(ids), "pairs_total": n_pairs, "pairs_sharing": len(pairs),
            "max_jaccard": max((p["jaccard"] for p in pairs), default=0.0),
            "facts_unique": len(per_fact), "facts_cited_by_2plus": sum(1 for v in per_fact.values() if v > 1),
            "max_claims_per_fact": max(per_fact.values(), default=0),
        },
    }


# ---------------------------------------------------------------- the judge interface and prompt
JUDGE_HEAD = (
    "You are comparing short descriptive claims. Every claim describes the same unnamed person. Each item "
    "below is an independent pair (X, Y); judge each pair on its own. Do not use any tool; answer directly "
    "from the text.\n\n"
    "Labels:\n"
    "- SAME: X and Y express one idea. One mostly restates the other (different wording, examples or emphasis "
    "is fine). Deleting either would lose little.\n"
    "- FACET: X and Y rest on the same underlying disposition or tendency, but each carries substantial content "
    "the other lacks, e.g. one gives the reason or value and the other the observable behaviour, or they cover "
    "different situations of the same tendency.\n"
    "- DISTINCT: different dispositions or ideas, even if they share a topic or words.\n\n"
    "Also estimate x_in_y: the percentage (0-100) of X's content already stated by Y, and y_in_x: the "
    "percentage of Y's content already stated by X.\n\n"
    "Return STRICT JSON only, a list with one object per item in order:\n"
    '[{"item": 1, "label": "SAME|FACET|DISTINCT", "x_in_y": 0, "y_in_x": 0}, ...]\n'
)


class PairJudge(Protocol):
    """Anything that labels pairs: `judge.ModelPairJudge` (a model through a backend), or
    a human review sheet. Returns one dict per pair:
    {"a", "b", "label" in LABELS, "x_in_y", "y_in_x"}."""

    def judge(self, pairs: list[tuple[str, str]], claims_by_id: dict) -> list[dict]: ...


def judge_tasks(pairs: list[tuple[str, str]], claims_by_id: dict, batch: int = 8, seed: int = 20260928) -> list[dict]:
    """Blind prompts for the judge, both orders of every pair, the two orders never in one
    call. The judge sees only statement and Active_When: no ids, layers or names. Builds
    text only; calls nothing."""
    items = []
    for a, b in pairs:
        items.append({"x": a, "y": b, "pair": f"{a}|{b}", "order": "ab"})
        items.append({"x": b, "y": a, "pair": f"{a}|{b}", "order": "ba"})
    random.Random(seed).shuffle(items)
    batches, cur, pending = [], [], items[:]
    while pending:
        placed = False
        for i, it in enumerate(pending):
            if all(o["pair"] != it["pair"] for o in cur):
                cur.append(pending.pop(i))
                placed = True
                break
        if not placed or len(cur) == batch:
            batches.append(cur)
            cur = []
    if cur:
        batches.append(cur)

    return [{"task": f"J{n:04d}", "items": b, "prompt": judge_prompt(b, claims_by_id)}
            for n, b in enumerate(batches, 1)]


def judge_prompt(items: list[dict], claims_by_id: dict) -> str:
    """The prototype's prompt, byte for byte (2026-09-28): the head, then `ITEM i` blocks of statement and Active_When, then a newline."""
    def fmt(c):
        return f'{c["statement"]}\n  Applies when: {c["active_when"]}'
    body = "\n\n".join(f"ITEM {i}\nX: {fmt(claims_by_id[it['x']])}\nY: {fmt(claims_by_id[it['y']])}"
                       for i, it in enumerate(items, 1))
    return JUDGE_HEAD + "\n" + body + "\n"


def load_judgements(path) -> list[dict]:
    """Read judgements written by any PairJudge: a JSON list, or JSONL, of
    {"a", "b", "label"}, or a stamped document holding them under "judgements"
    (the duplicate judge builder's output). Both orders of a pair may appear; dedupe decides how to combine."""
    from pathlib import Path
    text = Path(path).read_text(encoding="utf-8").strip()
    doc = None
    if text.startswith("{"):
        try:
            doc = json.loads(text)
        except json.JSONDecodeError:
            doc = None  # JSONL: one object per line
    if isinstance(doc, dict) and "judgements" in doc:
        rows = doc["judgements"]  # a stamped duplicate-judge output (consolidation.judge)
    else:
        rows = json.loads(text) if text.startswith("[") else [json.loads(ln) for ln in text.splitlines() if ln.strip()]
    for r in rows:
        if r.get("label") not in LABELS:
            raise ValueError(f"judgement {r} has a label outside {LABELS}")
        if not r.get("a") or not r.get("b"):
            raise ValueError(f"judgement {r} lacks a or b")
    return rows
