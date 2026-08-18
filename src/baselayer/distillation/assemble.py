"""THE HANDOFF PACKAGE. The seam between distillation and the layer authors.

EXPERIMENTAL AND UNTESTED. No test exercises this module; see
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
from collections import Counter, defaultdict


def load(paths):
    out = []
    for p in paths:
        t = json.load(open(p, encoding="utf-8"))
        if "root" not in t:
            raise SystemExit("%s is not a distillation tree" % p)
        t["_path"] = p
        out.append(t)
    return out


def assemble(trees, min_runs=None):
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
                                    "run_id": t.get("stamp", {}).get("run_id")})

    # SINGULARITIES: verbatim, thresholded at a majority. Single-run ones are KEPT but in a
    # separate stratum marked unverified, because 57-62% of them are resampling noise and the
    # author must know which pile it is reading from.
    sing_runs = defaultdict(set)
    sing_text = {}
    for i, t in enumerate(trees):
        for sg in (t["root"].get("singularities") or []):
            fid = sg.get("fact_id")
            if not fid:
                continue
            sing_runs[fid].add(i)
            sing_text.setdefault(fid, sg.get("verbatim", ""))

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

    verified = sorted((f for f, r in sing_runs.items() if len(r) >= min_runs),
                      key=lambda f: -len(sing_runs[f]))
    unverified = sorted(f for f, r in sing_runs.items() if len(r) < min_runs)
    # The KEY NAME stays `singularities_verified` on purpose: seven call sites in
    # author_from_package.py read it, and renaming a key to fix a claim trades a misleading
    # label for a KeyError. What changes is the CLAIM -- `verified_meaningful` says whether
    # the label means anything, and every renderer consults it before writing "VERIFIED".
    return {
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
            {"fact_id": f, "verbatim": sing_text[f], "runs": len(sing_runs[f])}
            for f in verified],
        "singularities_unverified": [
            {"fact_id": f, "verbatim": sing_text[f], "runs": len(sing_runs[f]),
             "warning": "appeared in fewer than %d of %d runs; 57-62%% of single-run "
                        "singularities are resampling noise" % (min_runs, n)}
            for f in unverified],
        "contradictions": contradictions,
        "dismissed_by_all_runs": sorted(f for f, c in dismissed.items() if c == n),
        "dismissed_CONTESTED": sorted(
            ({"fact_id": f, "dismissed_by": c, "of": n} for f, c in dismissed.items()
             if 0 < c < n), key=lambda d: -d["dismissed_by"])[:200],
        "facts_dispositioned": len(seen_ids),
    }


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("trees", nargs="+")
    ap.add_argument("--out", required=True)
    ap.add_argument("--min-runs", type=int, default=None)
    a = ap.parse_args()
    pkg = assemble(load(a.trees), a.min_runs)
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
          % len(pkg["dismissed_CONTESTED"]))
    print("  facts dispositioned     : %d" % pkg["facts_dispositioned"])
    print("wrote %s (%.1f KB)" % (a.out, os.path.getsize(a.out) / 1024))


if __name__ == "__main__":
    main()
