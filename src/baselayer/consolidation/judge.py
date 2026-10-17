"""Builder: the duplicate judge. Blind pairwise SAME / FACET / DISTINCT over candidate pairs.

Implements the `overlap.PairJudge` interface with a model backend. Ported from the
2026-09-28 prototype: the same head, the same
item format, the same batching.

    * Candidates are the pairs of the mechanical overlap stage (overlap.json), optionally
      filtered by a Jaccard floor, plus an optional pairs file from any other source.
    * Every pair is judged in BOTH presentation orders, and the two orders never share a
      call. Items are shuffled by `seed` and batched `batch` per call (default 8).
    * The judge sees only each claim's statement and Active_When: no id, layer, name or
      fact. The pair ids live in the task, not the prompt.
    * A reply is accepted only if it is a JSON list with one object per item, each with a
      label in SAME / FACET / DISTINCT. Otherwise the call is retried (bounded) and, if it
      still fails, its pairs are listed as unjudged. An unjudged pair is not a verdict.

Output (judgements.json, stamped): {"judgements": [{"a","b","pair","order","label",
"x_in_y","y_in_x","task"}], "pairs": [...], "unjudged_pairs", "summary"}. The dedupe stage
reads it with `--dedupe-basis judgements --judgements judgements.json`, and SAME in both
orders joins a group by default.
"""
from __future__ import annotations

from collections import Counter

from . import overlap as ov
from .backends import CallRunner, parse_json

TEMPLATE = "judge/1 (prototype 2026-09-28 head and item format)"
MAX_TOKENS = 16000


def candidate_pairs(overlap_doc: dict, min_jaccard: float = 0.0, extra: list | None = None,
                    known: set | None = None) -> list[tuple[str, str]]:
    seen, out = set(), []
    rows = [(p["a"], p["b"]) for p in overlap_doc["pairs"] if p["jaccard"] >= min_jaccard]
    rows += [tuple(p) if not isinstance(p, dict) else (p["a"], p["b"]) for p in (extra or [])]
    for a, b in rows:
        if a == b:
            continue
        if known is not None and (a not in known or b not in known):
            raise ValueError(f"candidate pair names an unknown claim: {a}|{b}")
        k = frozenset((a, b))
        if k not in seen:
            seen.add(k)
            out.append((a, b))
    return out


def _parser(n_items: int):
    def parse(text):
        p = parse_json(text)
        if not isinstance(p, list) or len(p) != n_items:
            return None
        for i, o in enumerate(p, 1):
            if not isinstance(o, dict) or o.get("label") not in ov.LABELS:
                return None
            if o.get("item") not in (None, i, str(i)):
                return None  # answers out of order would attach labels to the wrong pairs
        return p
    return parse


class ModelPairJudge:
    """overlap.PairJudge over a backend. judge() returns one row per (pair, order) judged."""

    def __init__(self, runner: CallRunner, *, batch: int = 8, seed: int = 20260928, key_prefix: str = ""):
        self.runner, self.batch, self.seed, self.key_prefix = runner, batch, seed, key_prefix
        self.tasks: list[dict] = []

    def judge(self, pairs, claims_by_id):
        tasks = ov.judge_tasks(list(pairs), claims_by_id, batch=self.batch, seed=self.seed)
        self.tasks = tasks
        b = self.runner.backend
        calls = [{"key": f"{self.key_prefix}judge|{TEMPLATE}|{b.name}|{b.model}|seed{self.seed}|{t['task']}",
                  "prompt": t["prompt"], "max_tokens": MAX_TOKENS, "parse": _parser(len(t["items"])), "task": t}
                 for t in tasks]
        res = self.runner.run(calls, meta={"builder": "judge"})
        rows = []
        for c in calls:
            got = res.get(c["key"])
            if got is None:
                continue
            for it, o in zip(c["task"]["items"], got["parsed"]):
                rows.append({"a": it["x"], "b": it["y"], "pair": it["pair"], "order": it["order"],
                             "label": o["label"], "x_in_y": o.get("x_in_y"), "y_in_x": o.get("y_in_x"),
                             "task": c["task"]["task"], "model": got["record"].get("model")})
        return rows


def build(claims_doc: dict, overlap_doc: dict, runner: CallRunner, *, min_jaccard: float = 0.0,
          extra_pairs: list | None = None, batch: int = 8, seed: int = 20260928, key_prefix: str = "") -> dict:
    cmap = {c["id"]: c for c in claims_doc["claims"]}
    pairs = candidate_pairs(overlap_doc, min_jaccard, extra_pairs, set(cmap))
    j = ModelPairJudge(runner, batch=batch, seed=seed, key_prefix=key_prefix)
    rows = j.judge(pairs, cmap) if pairs else []
    got = Counter(r["pair"] for r in rows)
    unjudged = [f"{a}|{b}" for a, b in pairs if got.get(f"{a}|{b}", 0) < 2]
    by_pair: dict[str, dict] = {}
    for r in rows:
        by_pair.setdefault(r["pair"], {})[r["order"]] = r["label"]
    both = [v for v in by_pair.values() if "ab" in v and "ba" in v]
    summary = {"candidate_pairs": len(pairs), "items": 2 * len(pairs), "calls": len(j.tasks),
               "judged_items": len(rows), "unjudged_pairs": len(unjudged),
               "labels": dict(Counter(r["label"] for r in rows)),
               "order_agreement": round(sum(v["ab"] == v["ba"] for v in both) / len(both), 4) if both else None,
               "same_both_orders": sum(v["ab"] == v["ba"] == "SAME" for v in both)}
    return {"method": "blind pairwise judge, both presentation orders in separate calls; statement and "
                      "Active_When only", "template": TEMPLATE, "head": ov.JUDGE_HEAD,
            "params": {"min_jaccard": min_jaccard, "batch": batch, "seed": seed,
                       "extra_pairs": len(extra_pairs or [])},
            "pairs": [f"{a}|{b}" for a, b in pairs], "judgements": rows, "unjudged_pairs": unjudged,
            "summary": summary}
