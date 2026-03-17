#!/usr/bin/env python3
"""Provenance-Traced Evaluation Framework — Phase 1: Brief Activation + Provenance Coverage.

Mechanical evaluation of whether a brief actually influenced model responses.
No LLM judge needed. Uses local MiniLM embeddings + cosine similarity.

Layer 1 (BA): Did the brief activate? Measures vector similarity between
  response segments and brief claims. C5c should be closer to brief than C1.

Layer 2 (PC): What fraction of response claims trace to the brief?
  Uses sentence-level chunking (no LLM needed for Phase 1).

Usage:
    python provenance_eval.py --subject marks --responses path/to/all_responses.json --brief path/to/c5c_brief.md
    python provenance_eval.py --subject marks  # uses default paths
"""

import argparse
import json
import os
import re
import sys
import statistics
from pathlib import Path

# Add scripts directory to path
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from api_client import embed_texts
from config import chromadb_dist_to_similarity


def chunk_into_sentences(text: str) -> list[str]:
    """Split text into sentence-level segments for embedding."""
    # Split on sentence boundaries
    raw = re.split(r'(?<=[.!?])\s+', text.strip())
    # Filter short fragments and merge very short sentences
    sentences = []
    buffer = ""
    for s in raw:
        s = s.strip()
        if not s:
            continue
        if len(s) < 40 and buffer:
            buffer += " " + s
        elif len(s) < 40:
            buffer = s
        else:
            if buffer:
                sentences.append(buffer)
                buffer = ""
            sentences.append(s)
    if buffer:
        sentences.append(buffer)
    return [s for s in sentences if len(s) > 20]


def chunk_brief(brief_text: str) -> list[str]:
    """Chunk brief into claim-level segments.

    Splits on sentence boundaries, keeping segments that contain
    substantive claims (not headers or metadata).
    """
    # Strip YAML front matter
    if brief_text.startswith("---"):
        end = brief_text.find("---", 3)
        if end > 0:
            brief_text = brief_text[end + 3:]

    # Remove markdown headers
    lines = brief_text.split("\n")
    content_lines = [l for l in lines if not l.startswith("#") and l.strip()]
    content = " ".join(content_lines)

    return chunk_into_sentences(content)


def cosine_similarity(vec_a, vec_b):
    """Compute cosine similarity between two vectors."""
    dot = sum(a * b for a, b in zip(vec_a, vec_b))
    norm_a = sum(a * a for a in vec_a) ** 0.5
    norm_b = sum(b * b for b in vec_b) ** 0.5
    if norm_a == 0 or norm_b == 0:
        return 0.0
    return dot / (norm_a * norm_b)


def compute_similarity_matrix(response_embeddings, brief_embeddings):
    """For each response segment, find the most similar brief claim."""
    results = []
    for i, resp_emb in enumerate(response_embeddings):
        best_sim = -1.0
        best_j = -1
        for j, brief_emb in enumerate(brief_embeddings):
            sim = cosine_similarity(resp_emb, brief_emb)
            if sim > best_sim:
                best_sim = sim
                best_j = j
        results.append({"segment_idx": i, "best_brief_idx": best_j, "similarity": best_sim})
    return results


def run_layer1(responses: dict, brief_claims: list[str], brief_embeddings: list) -> dict:
    """Layer 1: Brief Activation (BA).

    For each response, compute mean and max similarity to brief claims.
    Compare C5c vs C1 aggregate.
    """
    print("\n" + "=" * 60)
    print("Layer 1: Brief Activation (BA)")
    print("=" * 60)

    c1_results = {}
    c5c_results = {}

    for key, resp_data in sorted(responses.items()):
        condition = resp_data["condition"]
        prompt_id = resp_data["prompt_id"]
        response_text = resp_data["response"]

        # Chunk response into sentences
        segments = chunk_into_sentences(response_text)
        if not segments:
            print(f"  {key}: no segments extracted, skipping")
            continue

        # Embed response segments
        resp_embeddings = embed_texts(segments)
        if resp_embeddings is None:
            print(f"  {key}: embedding failed, skipping")
            continue

        # Compute similarity to brief
        sim_results = compute_similarity_matrix(resp_embeddings, brief_embeddings)
        similarities = [r["similarity"] for r in sim_results]

        mean_sim = statistics.mean(similarities)
        max_sim = max(similarities)
        median_sim = statistics.median(similarities)

        # Count segments above threshold
        above_60 = sum(1 for s in similarities if s >= 0.60)
        above_50 = sum(1 for s in similarities if s >= 0.50)

        result = {
            "prompt_id": prompt_id,
            "n_segments": len(segments),
            "ba_mean": round(mean_sim, 4),
            "ba_max": round(max_sim, 4),
            "ba_median": round(median_sim, 4),
            "segments_above_60": above_60,
            "segments_above_50": above_50,
            "top_matches": []
        }

        # Store top 3 matches for auditability
        sorted_results = sorted(sim_results, key=lambda x: x["similarity"], reverse=True)[:3]
        for sr in sorted_results:
            result["top_matches"].append({
                "response_segment": segments[sr["segment_idx"]],
                "brief_claim": brief_claims[sr["best_brief_idx"]],
                "similarity": round(sr["similarity"], 4)
            })

        if condition == "C1":
            c1_results[prompt_id] = result
        else:
            c5c_results[prompt_id] = result

        print(f"  {key}: mean={mean_sim:.4f}  max={max_sim:.4f}  segs={len(segments)}  >0.50={above_50}  >0.60={above_60}")

    # Compute aggregates
    c1_means = [r["ba_mean"] for r in c1_results.values()]
    c5c_means = [r["ba_mean"] for r in c5c_results.values()]
    c1_maxes = [r["ba_max"] for r in c1_results.values()]
    c5c_maxes = [r["ba_max"] for r in c5c_results.values()]

    c1_agg_mean = statistics.mean(c1_means) if c1_means else 0
    c5c_agg_mean = statistics.mean(c5c_means) if c5c_means else 0
    c1_agg_max = statistics.mean(c1_maxes) if c1_maxes else 0
    c5c_agg_max = statistics.mean(c5c_maxes) if c5c_maxes else 0

    ba_delta_mean = c5c_agg_mean - c1_agg_mean
    ba_delta_max = c5c_agg_max - c1_agg_max

    print(f"\n  --- Aggregate ---")
    print(f"  C1  mean-of-means: {c1_agg_mean:.4f}   mean-of-maxes: {c1_agg_max:.4f}")
    print(f"  C5c mean-of-means: {c5c_agg_mean:.4f}   mean-of-maxes: {c5c_agg_max:.4f}")
    print(f"  BA-delta (mean):   {ba_delta_mean:+.4f}  {'PASS' if ba_delta_mean > 0 else 'FAIL'}")
    print(f"  BA-delta (max):    {ba_delta_max:+.4f}  {'PASS' if ba_delta_max > 0 else 'FAIL'}")

    # Per-prompt comparison
    print(f"\n  --- Per-Prompt BA-delta ---")
    prompt_deltas = {}
    for pid in sorted(set(list(c1_results.keys()) + list(c5c_results.keys()))):
        if pid in c1_results and pid in c5c_results:
            delta = c5c_results[pid]["ba_mean"] - c1_results[pid]["ba_mean"]
            prompt_deltas[pid] = delta
            marker = "+" if delta > 0 else "-"
            print(f"  {pid}: C1={c1_results[pid]['ba_mean']:.4f}  C5c={c5c_results[pid]['ba_mean']:.4f}  delta={delta:+.4f} {marker}")

    positive_count = sum(1 for d in prompt_deltas.values() if d > 0)
    print(f"\n  Positive deltas: {positive_count}/{len(prompt_deltas)} prompts")

    return {
        "c1": c1_results,
        "c5c": c5c_results,
        "aggregate": {
            "c1_mean_of_means": round(c1_agg_mean, 4),
            "c5c_mean_of_means": round(c5c_agg_mean, 4),
            "c1_mean_of_maxes": round(c1_agg_max, 4),
            "c5c_mean_of_maxes": round(c5c_agg_max, 4),
            "ba_delta_mean": round(ba_delta_mean, 4),
            "ba_delta_max": round(ba_delta_max, 4),
            "positive_prompts": positive_count,
            "total_prompts": len(prompt_deltas),
            "pass": ba_delta_mean > 0
        }
    }


def run_layer2(responses: dict, brief_claims: list[str], brief_embeddings: list,
               threshold: float = 0.50) -> dict:
    """Layer 2: Provenance Coverage (PC).

    For each response, extract sentence-level claims, trace each to brief.
    A claim is 'covered' if its best brief match exceeds the threshold.
    """
    print("\n" + "=" * 60)
    print(f"Layer 2: Provenance Coverage (PC) — threshold={threshold}")
    print("=" * 60)

    c1_results = {}
    c5c_results = {}

    for key, resp_data in sorted(responses.items()):
        condition = resp_data["condition"]
        prompt_id = resp_data["prompt_id"]
        response_text = resp_data["response"]

        # Use sentences as claims (Phase 1 — no LLM extraction)
        claims = chunk_into_sentences(response_text)
        if not claims:
            continue

        claim_embeddings = embed_texts(claims)
        if claim_embeddings is None:
            continue

        # Trace each claim to nearest brief segment
        covered = 0
        uncovered = 0
        traces = []

        for i, (claim, claim_emb) in enumerate(zip(claims, claim_embeddings)):
            best_sim = -1.0
            best_j = -1
            for j, brief_emb in enumerate(brief_embeddings):
                sim = cosine_similarity(claim_emb, brief_emb)
                if sim > best_sim:
                    best_sim = sim
                    best_j = j

            is_covered = best_sim >= threshold
            if is_covered:
                covered += 1
            else:
                uncovered += 1

            traces.append({
                "claim": claim,
                "best_brief": brief_claims[best_j],
                "similarity": round(best_sim, 4),
                "covered": is_covered
            })

        total = covered + uncovered
        pc_ratio = covered / total if total > 0 else 0

        result = {
            "prompt_id": prompt_id,
            "total_claims": total,
            "covered": covered,
            "uncovered": uncovered,
            "pc_ratio": round(pc_ratio, 4),
            "traces": traces  # Full audit trail
        }

        if condition == "C1":
            c1_results[prompt_id] = result
        else:
            c5c_results[prompt_id] = result

        print(f"  {key}: {covered}/{total} covered ({pc_ratio:.1%})  uncovered={uncovered}")

    # Aggregates
    c1_ratios = [r["pc_ratio"] for r in c1_results.values()]
    c5c_ratios = [r["pc_ratio"] for r in c5c_results.values()]

    c1_agg = statistics.mean(c1_ratios) if c1_ratios else 0
    c5c_agg = statistics.mean(c5c_ratios) if c5c_ratios else 0
    pc_delta = c5c_agg - c1_agg

    print(f"\n  --- Aggregate ---")
    print(f"  C1  mean PC-ratio: {c1_agg:.4f}")
    print(f"  C5c mean PC-ratio: {c5c_agg:.4f}")
    print(f"  PC-delta:          {pc_delta:+.4f}  {'PASS' if pc_delta > 0 else 'FAIL'}")

    # Per-prompt
    print(f"\n  --- Per-Prompt PC-delta ---")
    prompt_deltas = {}
    for pid in sorted(set(list(c1_results.keys()) + list(c5c_results.keys()))):
        if pid in c1_results and pid in c5c_results:
            delta = c5c_results[pid]["pc_ratio"] - c1_results[pid]["pc_ratio"]
            prompt_deltas[pid] = delta
            print(f"  {pid}: C1={c1_results[pid]['pc_ratio']:.4f}  C5c={c5c_results[pid]['pc_ratio']:.4f}  delta={delta:+.4f}")

    positive_count = sum(1 for d in prompt_deltas.values() if d > 0)
    print(f"\n  Positive deltas: {positive_count}/{len(prompt_deltas)} prompts")

    # Threshold sensitivity
    print(f"\n  --- Threshold Sensitivity ---")
    thresholds = [0.40, 0.45, 0.50, 0.55, 0.60, 0.65, 0.70]
    for t in thresholds:
        c1_at_t = []
        c5c_at_t = []
        for pid in c1_results:
            c1_covered = sum(1 for tr in c1_results[pid]["traces"] if tr["similarity"] >= t)
            c1_total = len(c1_results[pid]["traces"])
            c1_at_t.append(c1_covered / c1_total if c1_total > 0 else 0)
        for pid in c5c_results:
            c5c_covered = sum(1 for tr in c5c_results[pid]["traces"] if tr["similarity"] >= t)
            c5c_total = len(c5c_results[pid]["traces"])
            c5c_at_t.append(c5c_covered / c5c_total if c5c_total > 0 else 0)

        c1_mean_t = statistics.mean(c1_at_t) if c1_at_t else 0
        c5c_mean_t = statistics.mean(c5c_at_t) if c5c_at_t else 0
        delta_t = c5c_mean_t - c1_mean_t
        print(f"  t={t:.2f}: C1={c1_mean_t:.4f}  C5c={c5c_mean_t:.4f}  delta={delta_t:+.4f}  {'PASS' if delta_t > 0 else 'FAIL'}")

    return {
        "c1": {k: {kk: vv for kk, vv in v.items() if kk != "traces"} for k, v in c1_results.items()},
        "c5c": {k: {kk: vv for kk, vv in v.items() if kk != "traces"} for k, v in c5c_results.items()},
        "aggregate": {
            "c1_mean_pc_ratio": round(c1_agg, 4),
            "c5c_mean_pc_ratio": round(c5c_agg, 4),
            "pc_delta": round(pc_delta, 4),
            "positive_prompts": positive_count,
            "total_prompts": len(prompt_deltas),
            "pass": pc_delta > 0
        }
    }


def main():
    parser = argparse.ArgumentParser(description="Provenance-Traced Evaluation — Phase 1")
    parser.add_argument("--subject", default="marks", help="Subject name (marks, franklin)")
    parser.add_argument("--responses", help="Path to all_responses.json")
    parser.add_argument("--brief", help="Path to c5c_brief.md")
    parser.add_argument("--output", help="Path to save results JSON")
    parser.add_argument("--threshold", type=float, default=0.50, help="PC coverage threshold")
    parser.add_argument("--layer1-only", action="store_true", help="Run only Layer 1 (BA)")
    args = parser.parse_args()

    # Default paths based on subject
    _home = str(Path.home() / "Anthropic")
    subject_dirs = {
        "marks": os.path.join(_home, "marks_memory"),
        "franklin": os.path.join(_home, "subjects", "franklin"),
    }

    if args.responses:
        responses_path = args.responses
    else:
        base = subject_dirs.get(args.subject, ".")
        responses_path = os.path.join(base, "data", "eval", f"v4_eval_{args.subject}", "responses", "all_responses.json")

    if args.brief:
        brief_path = args.brief
    else:
        base = subject_dirs.get(args.subject, ".")
        brief_path = os.path.join(base, "data", "eval", f"v4_eval_{args.subject}", "c5c_brief.md")

    if args.output:
        output_path = args.output
    else:
        base = subject_dirs.get(args.subject, ".")
        output_path = os.path.join(base, "data", "eval", f"v4_eval_{args.subject}", "provenance_eval_results.json")

    # Load data
    print(f"Subject: {args.subject}")
    print(f"Responses: {responses_path}")
    print(f"Brief: {brief_path}")

    with open(responses_path, "r", encoding="utf-8") as f:
        responses = json.load(f)

    with open(brief_path, "r", encoding="utf-8") as f:
        brief_text = f.read()

    print(f"\nLoaded {len(responses)} responses")

    # Chunk and embed brief
    brief_claims = chunk_brief(brief_text)
    print(f"Brief chunked into {len(brief_claims)} claim segments")

    print("Embedding brief claims...")
    brief_embeddings = embed_texts(brief_claims)
    if brief_embeddings is None:
        print("ERROR: Failed to embed brief claims")
        sys.exit(1)
    print(f"Brief embedded: {len(brief_embeddings)} vectors × {len(brief_embeddings[0])} dims")

    # Run layers
    results = {"subject": args.subject, "brief_claims": len(brief_claims)}

    results["layer1_ba"] = run_layer1(responses, brief_claims, brief_embeddings)

    if not args.layer1_only:
        results["layer2_pc"] = run_layer2(responses, brief_claims, brief_embeddings, args.threshold)

    # Summary
    print("\n" + "=" * 60)
    print("PROVENANCE EVAL SUMMARY")
    print("=" * 60)

    ba = results["layer1_ba"]["aggregate"]
    print(f"\n  Layer 1 — Brief Activation (BA)")
    print(f"    BA-delta (mean): {ba['ba_delta_mean']:+.4f}  {'PASS' if ba['pass'] else 'FAIL'}")
    print(f"    BA-delta (max):  {ba['ba_delta_max']:+.4f}")
    print(f"    Positive prompts: {ba['positive_prompts']}/{ba['total_prompts']}")

    if "layer2_pc" in results:
        pc = results["layer2_pc"]["aggregate"]
        print(f"\n  Layer 2 — Provenance Coverage (PC)")
        print(f"    PC-delta:        {pc['pc_delta']:+.4f}  {'PASS' if pc['pass'] else 'FAIL'}")
        print(f"    C5c coverage:    {pc['c5c_mean_pc_ratio']:.1%}")
        print(f"    C1 coverage:     {pc['c1_mean_pc_ratio']:.1%}")
        print(f"    Positive prompts: {pc['positive_prompts']}/{pc['total_prompts']}")

    overall = ba["pass"] and (results.get("layer2_pc", {}).get("aggregate", {}).get("pass", True))
    print(f"\n  Overall: {'PASS' if overall else 'FAIL'}")

    # Save results (without full traces to keep file manageable)
    os.makedirs(os.path.dirname(output_path), exist_ok=True)
    with open(output_path, "w", encoding="utf-8") as f:
        json.dump(results, f, indent=2, default=str)
    print(f"\n  Results saved: {output_path}")


if __name__ == "__main__":
    main()
