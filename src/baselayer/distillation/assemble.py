"""THE HANDOFF PACKAGE. The seam between distillation and the layer authors.

EXPERIMENTAL. Only the package stamp and the version-mix refusal are tested
(tests/test_artifact_stamps.py); the stratification itself is not. See
baselayer/distillation/__init__.py for the full status.

🎯 WHAT THIS IS FOR. Distillation produces trees. A layer author needs one input. The naive
move is to merge the trees into a single summary, and that is exactly wrong: merging N roots is
an (N+1)th summarisation hop with no audit, performed by the consensus operator this whole
architecture exists to constrain, and it throws away the only thing multiple runs bought.

So the package is a STRATIFICATION, not a merge. The author's job becomes WEIGHING EVIDENCE OF
DIFFERING STABILITY rather than summarising summaries, which is a better task and one only this
design can pose.

🚨 THE THRESHOLD IS A MAJORITY AND IT MUST NEVER BE UNANIMITY. Measured across 30
identical runs: the strictly-invariant singularity set decays to ZERO (2 at N=10, 0 at N=30)
while the >=half stratum is flat at 28-33 from three runs onward. Majority-of-3 gives 32 and
majority-of-30 gives 28, so THREE RUNS REACHES THE SAME STRATUM AS THIRTY. A single run's
singularity list is 57-62% run-specific; themes are stable at n=1.

⚠️ CONTRADICTIONS ARE NEVER THRESHOLDED. A contradiction found once is still a contradiction,
and the directed arms preserve them where the blind control merges them away. They also go to
COMPOSE, not only to the layer author: the three layer authors are blind to each other by
decision, so compose is the ONLY node that can see across all three, and as things stand it
receives three finished prose layers -- the form in which a tension has already been smoothed.
"""
import argparse
import json
import os
import sys
from collections import Counter, defaultdict

if not os.environ.get("BASELAYER_SRC") and not __package__:
    # Run as a plain script: pin THIS checkout's src/ so the stamp helper is the running code's.
    sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))
elif os.environ.get("BASELAYER_SRC"):
    sys.path.insert(0, os.environ["BASELAYER_SRC"])
from baselayer import turn_contract as _tc
from baselayer.turn_contract_fixtures import PLANTED_PREFIX as _PLANTED_PREFIX


def load(paths):
    out = []
    for p in paths:
        t = json.load(open(p, encoding="utf-8"))
        if "root" not in t:
            raise SystemExit("%s is not a distillation tree" % p)
        t["_path"] = p
        out.append(t)
    return out


def assemble(trees, min_runs=None, allow_planted=False):
    """Build the package. `min_runs` defaults to a strict majority of the trees given.

    AT n=1 THE MAJORITY RULE DEGENERATES AND THE "VERIFIED" LABEL BECOMES VACUOUS.
    (1 // 2) + 1 == 1, so every singularity clears the threshold, the unverified stratum is
    empty, and the author is handed "VERIFIED" over material this same file documents as
    57-62% run-specific. The label would then assert exactly the property a single run cannot
    establish. `dismissed_by_all_runs` degenerates the same way: "all runs" is one run.

    So a single tree does not get the CLAIM. The key name is unchanged (seven readers depend
    on it); `verified_meaningful` is False, `verified_note` states why, and every renderer
    consults that flag before printing the word VERIFIED.
    """
    n = len(trees)
    if min_runs is None:
        min_runs = (n // 2) + 1
    verified_meaningful = n > 1 and min_runs > 1
    if not verified_meaningful:
        print("NOTE: %d tree(s) supplied, so the verified/unverified split carries no "
              "corroboration: every singularity clears a threshold of %d. Reported as "
              "UNREPLICATED, not verified. Supply 3 trees to verify."
              % (n, min_runs))
    layers = {t.get("stamp", {}).get("layer") for t in trees}
    if len(layers) > 1:
        raise SystemExit("trees span multiple layers %s; assemble one layer at a time, because "
                         "a disposition is relative to its directive" % sorted(layers))
    # A tree distilled with --allow-planted carries facts from planted pilot sessions (synthetic
    # text stored as facts about the subject). Such a package must never reach an author unless
    # the caller says, again, that this is a pilot corpus. A tree from before this stamp field
    # existed counts as 0: it predates the planted fixtures.
    n_planted = sum(int(t.get("stamp", {}).get("planted_facts_included") or 0) for t in trees)
    if n_planted and not allow_planted:
        raise SystemExit(
            "REFUSED: %d facts in these trees come from planted pilot sessions ('%s'). A pilot "
            "corpus is not for distillation; pass allow_planted / --allow-planted only for a "
            "pilot's own checks." % (n_planted, _PLANTED_PREFIX))
    # One turn-contract version across every tree, or none (contract §7). A tree written before
    # stamps carried the version counts as unversioned, so it cannot be pooled with a gated one.
    try:
        contract_version = _tc.single_contract_version(
            (t.get("stamp", {}).get("turn_contract_version") for t in trees), "the input trees")
    except _tc.MixedContractVersions as e:
        raise SystemExit("MIXED CONTRACT VERSIONS: %s" % e)
    # The input hash covers each tree's full CONTENT, not its run id: a run id names the
    # parameters, and a cancelled run that kept going has already overwritten a tree on disk
    # under an unchanged name. What this package read is what gets hashed.
    tree_hashes = [_tc.json_input_hash({k: v for k, v in t.items() if k != "_path"})
                   for t in trees]
    stamp = _tc.artifact_stamp(
        "package", code_file=__file__, model=None, prompt_hash=None,
        input_hash=_tc.json_input_hash(sorted(tree_hashes)),
        turn_contract_version=contract_version,
        input_trees=[{"run_id": t.get("stamp", {}).get("run_id"),
                      "facts_input_hash": t.get("stamp", {}).get("input_hash"),
                      "tree_content_hash": h} for t, h in zip(trees, tree_hashes)],
        facts_input_hashes_agree=len({t.get("stamp", {}).get("input_hash")
                                      for t in trees}) == 1,
        planted_facts_included=n_planted)

    # THEMES: a FLAT UNION TAGGED BY SOURCE RUN. Deliberately NOT de-duplicated.
    #
    # 🚨 THE FIRST VERSION MATCHED THEMES BY LOWERCASED STRING PREFIX AND REPORTED 139 THEMES
    # WITH ZERO CORROBORATED. That is false, and it repeats in the assembler the same lesson
    # the rest of the pipeline keeps learning: the runs say the SAME THINGS IN DIFFERENT WORDS.
    # Read side by side, 7 of 9 themes map one-to-one across identical runs. Cosine at 0.85
    # scored that agreement at 24%; string prefix scores it at 0%. Both metrics measure
    # paraphrase distance, not agreement, and either would have told the author its three runs
    # disagreed completely.
    #
    # 🎯 SO DO NOT SCORE THEME EQUIVALENCE AT ALL. Themes are stable at n=1, which means the
    # union is not noisy, only redundant -- and judging which statements say the same thing is
    # a READING task, which is precisely what the layer author is for and what every automated
    # matcher tried here got wrong. Each theme carries its source run so the author can see
    # corroboration by reading, and nothing is silently collapsed by a rule that cannot tell
    # restatement from difference.
    themes_flat = []
    for i, t in enumerate(trees):
        for th in (t["root"].get("themes") or []):
            st = (th.get("statement") or "").strip()
            if st:
                themes_flat.append({"statement": st, "fact_ids": th.get("fact_ids") or [],
                                    "from_run": i,
                                    "run_id": t.get("stamp", {}).get("run_id"),
                                    # Carried, not yet rendered: see DISTILL_UNBLOCK notes.
                                    "seen_in_leaves": th.get("seen_in_leaves")})

    # SINGULARITIES: verbatim, thresholded at a majority. Single-run ones are KEPT but in a
    # separate stratum marked unverified, because 57-62% of them are resampling noise and the
    # author must know which pile it is reading from.
    sing_runs = defaultdict(set)
    sing_text = {}
    sing_words = {}     # T1 (--leaf-spans): a checked excerpt of the person's own words
    for i, t in enumerate(trees):
        for sg in (t["root"].get("singularities") or []):
            fid = sg.get("fact_id")
            if not fid:
                continue
            sing_runs[fid].add(i)
            sing_text.setdefault(fid, sg.get("verbatim", ""))
            if sg.get("own_words") and not sing_words.get(fid):
                sing_words[fid] = sg["own_words"]

    # DISMISSED: agreement counts. Dismissed-by-all is safely set aside; dismissed-by-some is
    # CONTESTED, and that disagreement is information the author should see rather than a
    # detail to resolve.
    dismissed = Counter()
    seen_ids = set()
    for t in trees:
        for d in (t.get("leaves") or []):
            for fid, verdict in (d.get("dispositions") or {}).items():
                seen_ids.add(fid)
                if verdict == "not_load_bearing":
                    dismissed[fid] += 1

    contradictions = [c for t in trees for c in (t["root"].get("contradictions") or [])]

    # FACTS NOT ABOUT THE PERSON, admitted only under distill's --include-other-subjects. The
    # subject travels as its own field so the author's render can label every place such a
    # fact appears; it is never spliced into a fact's text.
    other_subject_ids = {}
    for t in trees:
        other_subject_ids.update(t.get("stamp", {}).get("other_subject_ids") or {})

    verified = sorted((f for f, r in sing_runs.items() if len(r) >= min_runs),
                      key=lambda f: -len(sing_runs[f]))
    unverified = sorted(f for f, r in sing_runs.items() if len(r) < min_runs)
    # The KEY NAME stays `singularities_verified` on purpose: seven call sites in
    # author_from_package.py read it, and renaming a key to fix a claim trades a misleading
    # label for a KeyError. What changes is the CLAIM -- `verified_meaningful` says whether
    # the label means anything, and every renderer consults it before writing "VERIFIED".
    return {
        "stamp": stamp,
        "layer": (layers.pop() if layers else None),
        "trees": [t.get("stamp", {}).get("run_id") for t in trees],
        "n_runs": n,
        "min_runs_for_verified": min_runs,
        "verified_meaningful": verified_meaningful,
        "verified_note": (None if verified_meaningful else
                          "n=%d: the majority threshold is %d, which every singularity meets. "
                          "This is NOT corroboration. 57-62%% of single-run singularities are "
                          "resampling noise; 3 runs reach the same stratum as 30."
                          % (n, min_runs)),
        "themes": themes_flat,
        "themes_note": ("Flat union, tagged by source run, NOT de-duplicated. Runs restate the "
                        "same claim in different words: string and embedding matching both "
                        "score real 7-of-9 agreement at 0-24%. Judge equivalence by READING."),
        "singularities_verified": [
            dict({"fact_id": f, "verbatim": sing_text[f], "runs": len(sing_runs[f])},
                 **({"subject": other_subject_ids[f]} if f in other_subject_ids else {}),
                 **({"own_words": sing_words[f]} if sing_words.get(f) else {}))
            for f in verified],
        "singularities_unverified": [
            {"fact_id": f, "verbatim": sing_text[f], "runs": len(sing_runs[f]),
             **({"subject": other_subject_ids[f]} if f in other_subject_ids else {}),
             **({"own_words": sing_words[f]} if sing_words.get(f) else {}),
             "warning": "appeared in fewer than %d of %d runs; 57-62%% of single-run "
                        "singularities are resampling noise" % (min_runs, n)}
            for f in unverified],
        "contradictions": contradictions,
        "other_subject_ids": other_subject_ids,
        "dismissed_by_all_runs": sorted(f for f, c in dismissed.items() if c == n),
        # The list is capped for size; the COUNT is not. The render used to print the capped
        # list's length as the number contested.
        "dismissed_CONTESTED": sorted(
            ({"fact_id": f, "dismissed_by": c, "of": n} for f, c in dismissed.items()
             if 0 < c < n), key=lambda d: -d["dismissed_by"])[:200],
        "dismissed_CONTESTED_total": sum(1 for c in dismissed.values() if 0 < c < n),
        "facts_dispositioned": len(seen_ids),
    }


# ---------------------------------------------------------------------------------------------
# SHARDING. A package whose rendered evidence exceeds what one author request may carry is split
# into shards, each authored separately, instead of stopping the run or engaging the merge.
#
# The split is MECHANICAL and LOSSLESS: no model call, no summarising node, nothing dropped.
# Every theme, singularity and contradiction is assigned to the leaf it came from (by the lowest
# leaf index among its fact ids; a theme with no ids by the leaf whose statement it is) and the
# leaves are cut into CONTIGUOUS RANGES that fit the budget. Items are copied unchanged, so a
# theme's seen_in_leaves stays the whole-tree count. With the predicate partition, contiguous
# leaves are contiguous predicate ranges, so each shard is a coherent slice of the fact base.
# Facts every run dismissed are counted over the whole package and carried in every shard.
#
# Cross-shard collapse is NOT done here and not by a second authoring pass over the shard
# claims (that would be a merge tree under another name). It is left to compose, which reads
# all three layers.
# ---------------------------------------------------------------------------------------------
SHARD_CHARS_PER_TOKEN = 3.0     # conservative: package text measured at ~3.5 chars per token


def _rendered_tokens(pkg):
    from baselayer.distillation import author_from_package as _afp
    return len(_afp.render(pkg)) / SHARD_CHARS_PER_TOKEN


def shard(trees, pkg, budget_tokens):
    """[pkg] if it fits the budget, else shard packages along contiguous leaf ranges."""
    if _rendered_tokens(pkg) <= budget_tokens:
        return [pkg]
    sig = [(lf.get("_chunk"), tuple(lf.get("_ids") or [])) for lf in trees[0].get("leaves") or []]
    for t in trees[1:]:
        if [(lf.get("_chunk"), tuple(lf.get("_ids") or [])) for lf in t.get("leaves") or []] != sig:
            raise SystemExit("cannot shard: the trees' partitions do not align (different chunk "
                             "labels or fact ids per leaf). Shard trees built with the same "
                             "partition, chunk size and seed, or assemble fewer trees.")
    if not sig or not any(ids for _, ids in sig):
        raise SystemExit("cannot shard: the trees carry no per-leaf fact ids")
    leaf_of = {}
    for i, (_, ids) in enumerate(sig):
        for f in ids:
            leaf_of.setdefault(f, i)
    stmt_leaf = {}
    for ti, t in enumerate(trees):
        for i, lf in enumerate(t.get("leaves") or []):
            for th in lf.get("themes") or []:
                stmt_leaf.setdefault((ti, (th.get("statement") or "").strip().lower()), i)

    def _leaf(ids, fallback=0):
        li = [leaf_of[f] for f in ids if f in leaf_of]
        return min(li) if li else fallback

    th_leaf = [_leaf(t.get("fact_ids") or [],
                     stmt_leaf.get((t.get("from_run"), t["statement"].strip().lower()), 0))
               for t in pkg["themes"]]
    sv_leaf = [_leaf([s["fact_id"]]) for s in pkg["singularities_verified"]]
    su_leaf = [_leaf([s["fact_id"]]) for s in pkg["singularities_unverified"]]
    co_leaf = [_leaf((c.get("a_fact_ids") or []) + (c.get("b_fact_ids") or []))
               for c in pkg["contradictions"]]
    n = len(sig)

    def build(a, b):
        sub = dict(pkg)
        sub["themes"] = [t for t, i in zip(pkg["themes"], th_leaf) if a <= i < b]
        sub["singularities_verified"] = [s for s, i in zip(pkg["singularities_verified"], sv_leaf)
                                         if a <= i < b]
        sub["singularities_unverified"] = [s for s, i in
                                           zip(pkg["singularities_unverified"], su_leaf)
                                           if a <= i < b]
        sub["contradictions"] = [c for c, i in zip(pkg["contradictions"], co_leaf) if a <= i < b]
        sub["shard"] = {"index": None, "of": None, "leaf_range": [a, b],
                        "chunks": [sig[a][0], sig[b - 1][0]], "budget_tokens": budget_tokens,
                        "dismissed_scope": "whole package"}
        return sub

    # Greedy on an approximate per-leaf size, then every shard is re-measured by rendering it
    # and split further if the approximation was short. A single leaf over budget is refused.
    size = [0.0] * n
    for items, where in ((pkg["themes"], th_leaf), (pkg["singularities_verified"], sv_leaf),
                         (pkg["singularities_unverified"], su_leaf),
                         (pkg["contradictions"], co_leaf)):
        for it, i in zip(items, where):
            size[i] += (len(json.dumps(it)) + 40) / SHARD_CHARS_PER_TOKEN
    base = _rendered_tokens(build(0, 0)) if n else 0
    ranges, a, acc = [], 0, 0.0
    for i in range(n):
        if acc and base + acc + size[i] > budget_tokens:
            ranges.append((a, i))
            a, acc = i, 0.0
        acc += size[i]
    ranges.append((a, n))

    def fit(a, b):
        sub = build(a, b)
        if _rendered_tokens(sub) <= budget_tokens:
            return [sub]
        if b - a == 1:
            raise SystemExit("cannot shard: leaf %d (%s) alone renders to %.0f tokens, over the "
                             "%d budget" % (a, sig[a][0], _rendered_tokens(sub), budget_tokens))
        m = (a + b) // 2
        return fit(a, m) + fit(m, b)

    out = [s for a, b in ranges for s in fit(a, b)]
    for k, s in enumerate(out, 1):
        s["shard"]["index"], s["shard"]["of"] = k, len(out)
        s["stamp"] = dict(pkg["stamp"], shard=dict(s["shard"]))
    return out


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("trees", nargs="+")
    ap.add_argument("--out", required=True)
    ap.add_argument("--min-runs", type=int, default=None)
    ap.add_argument("--allow-planted", action="store_true",
                    help="PILOT CORPORA ONLY: accept trees distilled from planted sessions")
    ap.add_argument("--shard-token-budget", type=int,
                    default=int(os.environ.get("BASELAYER_LEAF_PAYLOAD_CEILING", "400000")),
                    help="tokens of rendered evidence one author request may carry (default "
                         "BASELAYER_LEAF_PAYLOAD_CEILING or 400000). Over it, the package is "
                         "split into shards along contiguous leaf ranges: --out becomes a "
                         "manifest naming the shard files written beside it.")
    a = ap.parse_args()
    trees = load(a.trees)
    pkg = assemble(trees, a.min_runs, allow_planted=a.allow_planted)
    shards = shard(trees, pkg, a.shard_token_budget)
    if len(shards) > 1:
        stem = os.path.splitext(a.out)[0]
        names = []
        for s in shards:
            path = "%s.shard%02dof%02d.json" % (stem, s["shard"]["index"], s["shard"]["of"])
            json.dump(s, open(path, "w", encoding="utf-8"), indent=1)
            names.append(os.path.basename(path))
        json.dump({"shard_manifest": True, "layer": pkg["layer"], "stamp": pkg["stamp"],
                   "shard_token_budget": a.shard_token_budget, "shards": names,
                   "note": "the package exceeded one author request; each shard is authored "
                           "separately and the claims concatenated"},
                  open(a.out, "w", encoding="utf-8"), indent=1)
        print("SHARDED: %d shards of <= %d tokens each (contiguous leaf ranges %s) -> %s"
              % (len(shards), a.shard_token_budget,
                 [tuple(s["shard"]["leaf_range"]) for s in shards], ", ".join(names)))
    else:
        json.dump(pkg, open(a.out, "w", encoding="utf-8"), indent=1)
    print("HANDOFF PACKAGE  layer=%s  from %d trees, verified threshold >=%d"
          % (pkg["layer"], pkg["n_runs"], pkg["min_runs_for_verified"]))
    print("  themes                  : %d across %d runs, flat union, NOT de-duplicated"
          % (len(pkg["themes"]), pkg["n_runs"]))
    print("     (equivalence is a reading task; every automated matcher tried scored real "
          "7-of-9 agreement at 0-24%)")
    _lbl = "VERIFIED   " if pkg.get("verified_meaningful") else "UNREPLICATED"
    print("  singularities %s: %d" % (_lbl, len(pkg["singularities_verified"])))
    if not pkg.get("verified_meaningful"):
        print("     ^ %s" % pkg["verified_note"])
    print("  singularities unverified: %d  <- separate stratum, marked" %
          len(pkg["singularities_unverified"]))
    print("  contradictions          : %d  (union, never thresholded)"
          % len(pkg["contradictions"]))
    print("  dismissed by ALL runs   : %d" % len(pkg["dismissed_by_all_runs"]))
    print("  dismissed CONTESTED     : %d  <- disagreement is information"
          % pkg["dismissed_CONTESTED_total"])
    print("  facts dispositioned     : %d" % pkg["facts_dispositioned"])
    print("wrote %s (%.1f KB)" % (a.out, os.path.getsize(a.out) / 1024))


if __name__ == "__main__":
    main()
