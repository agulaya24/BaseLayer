"""
SWE-Bench Axiom Benchmark Harness

Two phases:
  1. GENERATE — For each problem × condition, run an agent loop (Anthropic API + bash tools)
                inside a Docker container to produce a git diff patch.
  2. EVALUATE — Feed predictions JSONL to swebench's run_evaluation.

Usage (run from WSL):
  # Validate on 1 problem with Haiku:
  python scripts/swebench_harness.py generate --model haiku --problems 1 --conditions C0

  # Full T4 on Haiku:
  python scripts/swebench_harness.py generate --model haiku

  # Evaluate predictions:
  python scripts/swebench_harness.py evaluate --run-id haiku_full

  # Full pipeline (generate + evaluate):
  python scripts/swebench_harness.py run --model haiku
"""

import argparse
import json
import os
import sys
import time
import subprocess
import tempfile
import threading
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path
from datetime import datetime

import anthropic
import docker
from datasets import load_dataset

# ── Paths ──────────────────────────────────────────────────────────────────────
PROJECT_ROOT = Path(__file__).resolve().parent.parent
DATA_DIR = PROJECT_ROOT / "data" / "swebench"
CONDITIONS_DIR = DATA_DIR / "conditions"
RESULTS_DIR = DATA_DIR / "results"
SELECTED_PROBLEMS = DATA_DIR / "selected_problems.json"

# ── Model mapping ─────────────────────────────────────────────────────────────
MODEL_MAP = {
    "haiku": "claude-haiku-4-5-20251001",
    "sonnet": "claude-sonnet-4-6",
    "opus": "claude-opus-4-6",
}

# ── Condition files ────────────────────────────────────────────────────────────
CONDITION_IDS = ["C0", "C1", "C2", "C3", "C4", "C5", "C7"]

# ── Docker constants ──────────────────────────────────────────────────────────
DOCKER_WORKDIR = "/testbed"

# ── Agent constants ───────────────────────────────────────────────────────────
MAX_AGENT_TURNS = 25  # Max tool-use turns per problem
AGENT_TIMEOUT = 120   # Seconds per bash command


def load_conditions() -> dict[str, str]:
    """Load all condition system prompts from files."""
    conditions = {}
    for cid in CONDITION_IDS:
        fpath = CONDITIONS_DIR / f"{cid}_{'bare' if cid == 'C0' else '*'}"
        # Find the actual file
        matches = list(CONDITIONS_DIR.glob(f"{cid}_*.md"))
        if not matches:
            print(f"WARNING: No condition file found for {cid}")
            conditions[cid] = ""
            continue
        text = matches[0].read_text(encoding="utf-8")
        # Strip comment lines (# ...) at the top
        lines = text.strip().split("\n")
        content_lines = [l for l in lines if not l.startswith("#")]
        conditions[cid] = "\n".join(content_lines).strip()
    return conditions


def load_selected_problems() -> list[str]:
    """Load selected problem IDs."""
    with open(SELECTED_PROBLEMS, "r") as f:
        data = json.load(f)
    return data["selected_ids"]


def get_problem_data(instance_id: str) -> dict:
    """Fetch problem data from SWE-bench Verified dataset."""
    ds = load_dataset("princeton-nlp/SWE-bench_Verified", split="test")
    for row in ds:
        if row["instance_id"] == instance_id:
            return dict(row)
    raise ValueError(f"Problem {instance_id} not found in SWE-bench Verified")


def load_all_problems(instance_ids: list[str]) -> list[dict]:
    """Load all selected problems from dataset."""
    ds = load_dataset("princeton-nlp/SWE-bench_Verified", split="test")
    problems = {}
    for row in ds:
        if row["instance_id"] in instance_ids:
            problems[row["instance_id"]] = dict(row)
    # Preserve order
    result = []
    for iid in instance_ids:
        if iid in problems:
            result.append(problems[iid])
        else:
            print(f"WARNING: {iid} not found in dataset")
    return result


def setup_container(problem: dict, docker_client) -> object:
    """Set up a Docker container with the repo at the right commit.

    Uses swebench's image building infrastructure.
    """
    from swebench.harness.test_spec.test_spec import make_test_spec
    from swebench.harness.docker_build import (
        build_container,
        build_env_images,
        build_base_images,
    )
    import logging

    instance_id = problem["instance_id"]
    logger = logging.getLogger(f"swebench.{instance_id}")

    # Create TestSpec
    test_spec = make_test_spec(problem)

    # Build images (cached if already built)
    print(f"  Building images for {instance_id}...")
    build_base_images(docker_client, [test_spec], force_rebuild=False)
    build_env_images(docker_client, [test_spec], force_rebuild=False)

    # Build container
    run_id = f"axiom_{int(time.time())}"
    container = build_container(test_spec, docker_client, run_id, logger, nocache=False)
    container.start()

    return container


def run_agent_loop(
    container,
    problem: dict,
    system_prompt: str,
    model: str,
    max_turns: int = MAX_AGENT_TURNS,
) -> str:
    """Run an agent loop: Anthropic API + bash tool inside Docker container.

    Returns the git diff (model_patch).
    """
    client = anthropic.Anthropic()
    instance_id = problem["instance_id"]
    problem_statement = problem["problem_statement"]
    hints = problem.get("hints_text", "")

    # Base instruction for the agent
    task_prompt = f"""You are solving a GitHub issue in the repository at /testbed.

## Issue: {instance_id}

{problem_statement}

{f"## Hints{chr(10)}{hints}" if hints else ""}

## Instructions
1. Explore the repository to understand the codebase structure and find relevant files.
2. Identify the root cause of the issue.
3. Make the minimal code changes needed to fix the issue.
4. Do NOT run tests — just produce the fix.
5. When done, say "DONE" and nothing else.

You have bash access to the repository at /testbed. Use it to explore, read files, and make edits."""

    # Tool definition for bash
    tools = [
        {
            "name": "bash",
            "description": "Execute a bash command in the repository environment. Working directory is /testbed.",
            "input_schema": {
                "type": "object",
                "properties": {
                    "command": {
                        "type": "string",
                        "description": "The bash command to execute",
                    }
                },
                "required": ["command"],
            },
        }
    ]

    # Build messages
    messages = [{"role": "user", "content": task_prompt}]

    # System prompt (condition-dependent)
    system = system_prompt if system_prompt else None

    total_input_tokens = 0
    total_output_tokens = 0

    for turn in range(max_turns):
        try:
            response = client.messages.create(
                model=model,
                max_tokens=4096,
                system=system or anthropic.NOT_GIVEN,
                messages=messages,
                tools=tools,
                temperature=0,
            )
        except Exception as e:
            print(f"    API error on turn {turn + 1}: {e}")
            break

        total_input_tokens += response.usage.input_tokens
        total_output_tokens += response.usage.output_tokens

        # Check if model is done (no tool use, or said DONE)
        has_tool_use = any(b.type == "tool_use" for b in response.content)
        text_content = " ".join(
            b.text for b in response.content if b.type == "text"
        )

        if text_content.strip():
            print(f"    [{turn+1}] {text_content[:120]}")

        if not has_tool_use:
            print(f"    Agent finished after {turn + 1} turns "
                  f"({total_input_tokens} in / {total_output_tokens} out)")
            break

        # Process tool calls
        assistant_content = response.content
        tool_results = []

        for block in assistant_content:
            if block.type == "tool_use":
                cmd = block.input.get("command", "")
                cmd_preview = cmd[:100].replace('\n', ' ')
                print(f"    [{turn+1}] $ {cmd_preview}")
                # Execute in container — use cd to ensure workdir
                wrapped_cmd = f"cd {DOCKER_WORKDIR} && {cmd}"
                try:
                    exec_result = container.exec_run(
                        ["bash", "-c", wrapped_cmd],
                    )
                    output = exec_result.output.decode("utf-8", errors="replace")
                    # Truncate very long outputs
                    if len(output) > 10000:
                        output = output[:5000] + "\n\n... [truncated] ...\n\n" + output[-5000:]
                    if exec_result.exit_code != 0:
                        output = f"[exit code: {exec_result.exit_code}]\n{output}"
                except Exception as e:
                    output = f"Error executing command: {e}"

                tool_results.append({
                    "type": "tool_result",
                    "tool_use_id": block.id,
                    "content": output,
                })

        # Add assistant message and tool results to conversation
        messages.append({"role": "assistant", "content": assistant_content})
        messages.append({"role": "user", "content": tool_results})

    # Extract git diff
    try:
        diff_result = container.exec_run(
            ["git", "-c", "core.fileMode=false", "diff"],
            workdir=DOCKER_WORKDIR,
        )
        patch = diff_result.output.decode("utf-8", errors="replace").strip()
    except Exception as e:
        print(f"    Error extracting diff: {e}")
        patch = ""

    print(f"    Patch: {len(patch)} chars, "
          f"cost: ~${total_input_tokens * 0.80 / 1_000_000 + total_output_tokens * 4.00 / 1_000_000:.4f} (Haiku)")

    return patch


def _run_single_task(
    problem: dict,
    cid: str,
    system_prompt: str,
    model: str,
    predictions_path: Path,
    write_lock: threading.Lock,
    task_label: str,
) -> dict:
    """Run a single (problem, condition) pair. Thread-safe."""
    instance_id = problem["instance_id"]
    docker_client = docker.from_env()  # Each thread gets its own client

    print(f"  [{task_label}] {instance_id} × {cid}: starting...")

    try:
        container = setup_container(problem, docker_client)
    except Exception as e:
        print(f"  [{task_label}] {instance_id} × {cid}: container setup failed: {e}")
        pred = {
            "instance_id": instance_id,
            "model_name_or_path": model,
            "model_patch": "",
            "condition": cid,
            "error": str(e),
        }
        with write_lock:
            with open(predictions_path, "a") as f:
                f.write(json.dumps(pred) + "\n")
        return pred

    try:
        patch = run_agent_loop(container, problem, system_prompt, model)
        pred = {
            "instance_id": instance_id,
            "model_name_or_path": model,
            "model_patch": patch,
            "condition": cid,
        }
        with write_lock:
            with open(predictions_path, "a") as f:
                f.write(json.dumps(pred) + "\n")
        return pred

    except Exception as e:
        print(f"  [{task_label}] {instance_id} × {cid}: agent failed: {e}")
        pred = {
            "instance_id": instance_id,
            "model_name_or_path": model,
            "model_patch": "",
            "condition": cid,
            "error": str(e),
        }
        with write_lock:
            with open(predictions_path, "a") as f:
                f.write(json.dumps(pred) + "\n")
        return pred
    finally:
        try:
            container.stop(timeout=10)
            container.remove(force=True)
        except Exception:
            pass


def generate_predictions(
    model_key: str,
    condition_ids: list[str],
    problem_ids: list[str] | None = None,
    max_problems: int | None = None,
    resume: bool = True,
    workers: int = 1,
):
    """Generate predictions for all problem × condition pairs."""
    model = MODEL_MAP[model_key]
    conditions = load_conditions()
    all_problem_ids = load_selected_problems()

    if problem_ids:
        all_problem_ids = [p for p in all_problem_ids if p in problem_ids]
    if max_problems:
        all_problem_ids = all_problem_ids[:max_problems]

    # Filter conditions
    conditions = {k: v for k, v in conditions.items() if k in condition_ids}

    total_runs = len(all_problem_ids) * len(conditions)
    print(f"Generating predictions: {len(all_problem_ids)} problems × {len(conditions)} conditions = {total_runs} runs")
    print(f"Model: {model} | Workers: {workers}")

    # Create results directory
    run_id = f"{model_key}_{'_'.join(condition_ids)}_{datetime.now().strftime('%Y%m%d_%H%M%S')}"
    run_dir = RESULTS_DIR / run_id
    run_dir.mkdir(parents=True, exist_ok=True)

    # Load all problems at once
    print("Loading SWE-bench Verified dataset...")
    problems = load_all_problems(all_problem_ids)
    print(f"Loaded {len(problems)} problems")

    # Predictions file
    predictions_path = run_dir / "predictions.jsonl"

    # Load existing predictions for resume
    existing = set()
    if resume and predictions_path.exists():
        with open(predictions_path, "r") as f:
            for line in f:
                if line.strip():
                    pred = json.loads(line)
                    key = f"{pred['instance_id']}_{pred.get('condition', 'C0')}"
                    existing.add(key)
        print(f"Resuming: {len(existing)} predictions already exist")

    # Build work queue (all problem × condition pairs not yet done)
    work_items = []
    for problem in problems:
        for cid, system_prompt in conditions.items():
            key = f"{problem['instance_id']}_{cid}"
            if key not in existing:
                work_items.append((problem, cid, system_prompt))

    if not work_items:
        print("All predictions already exist. Nothing to do.")
        return run_id, predictions_path

    print(f"Tasks remaining: {len(work_items)} / {total_runs}")

    # Pre-build Docker images sequentially (avoid parallel build races)
    print("\nPre-building Docker images...")
    docker_client = docker.from_env()
    seen_instances = set()
    for problem, _, _ in work_items:
        iid = problem["instance_id"]
        if iid not in seen_instances:
            seen_instances.add(iid)
            try:
                from swebench.harness.test_spec.test_spec import make_test_spec
                from swebench.harness.docker_build import build_base_images, build_env_images, build_instance_images
                test_spec = make_test_spec(problem)
                build_base_images(docker_client, [test_spec], force_rebuild=False)
                build_env_images(docker_client, [test_spec], force_rebuild=False)
                build_instance_images(docker_client, [test_spec], force_rebuild=False, nocache=False)
                print(f"  Image ready: {iid}")
            except Exception as e:
                print(f"  Image build failed for {iid}: {e}")

    # Run with thread pool
    write_lock = threading.Lock()
    completed = 0
    start_time = time.time()

    print(f"\nStarting {len(work_items)} tasks with {workers} workers...")

    with ThreadPoolExecutor(max_workers=workers) as executor:
        futures = {}
        for i, (problem, cid, system_prompt) in enumerate(work_items):
            label = f"{i+1}/{len(work_items)}"
            future = executor.submit(
                _run_single_task,
                problem, cid, system_prompt, model,
                predictions_path, write_lock, label,
            )
            futures[future] = (problem["instance_id"], cid)

        for future in as_completed(futures):
            instance_id, cid = futures[future]
            completed += 1
            elapsed = time.time() - start_time
            rate = completed / elapsed * 3600 if elapsed > 0 else 0
            remaining = len(work_items) - completed
            eta_hrs = remaining / rate if rate > 0 else 0
            try:
                result = future.result()
                has_patch = bool(result.get("model_patch", ""))
                status = "PATCH" if has_patch else "EMPTY"
            except Exception as e:
                status = f"ERROR: {e}"
            print(f"  Completed {completed}/{len(work_items)} | "
                  f"{instance_id}×{cid}: {status} | "
                  f"ETA: {eta_hrs:.1f}h | Rate: {rate:.0f}/hr")

    total_time = time.time() - start_time
    print(f"\n{'='*60}")
    print(f"Done! {len(work_items)} tasks in {total_time/3600:.1f}h")
    print(f"Predictions saved to: {predictions_path}")
    print(f"Run ID: {run_id}")
    return run_id, predictions_path


def evaluate_predictions(predictions_path: str, run_id: str = "eval"):
    """Evaluate predictions using swebench harness."""
    from swebench.harness.run_evaluation import main as run_eval

    predictions_path = Path(predictions_path)
    if not predictions_path.exists():
        print(f"ERROR: {predictions_path} not found")
        return

    # swebench expects one prediction per instance_id, so we need to split
    # by condition and evaluate each separately
    with open(predictions_path, "r") as f:
        all_preds = [json.loads(line) for line in f if line.strip()]

    # Group by condition
    by_condition = {}
    for pred in all_preds:
        cid = pred.get("condition", "C0")
        by_condition.setdefault(cid, []).append(pred)

    results_dir = predictions_path.parent
    summary = {}

    for cid, preds in sorted(by_condition.items()):
        print(f"\n{'='*60}")
        print(f"Evaluating condition {cid} ({len(preds)} predictions)")

        # Write condition-specific predictions file
        cond_pred_path = results_dir / f"predictions_{cid}.jsonl"
        instance_ids = []
        with open(cond_pred_path, "w") as f:
            for pred in preds:
                # swebench needs clean predictions without extra fields
                clean = {
                    "instance_id": pred["instance_id"],
                    "model_name_or_path": pred["model_name_or_path"],
                    "model_patch": pred["model_patch"],
                }
                f.write(json.dumps(clean) + "\n")
                instance_ids.append(pred["instance_id"])

        # Run evaluation
        try:
            run_eval(
                dataset_name="princeton-nlp/SWE-bench_Verified",
                split="test",
                instance_ids=instance_ids,
                predictions_path=str(cond_pred_path),
                max_workers=4,
                force_rebuild=False,
                cache_level="instance",
                clean=False,
                open_file_limit=4096,
                run_id=f"{run_id}_{cid}",
                timeout=1800,
                namespace=None,
                rewrite_reports=False,
                modal=False,
                report_dir=str(results_dir),
            )
        except Exception as e:
            print(f"  Evaluation error: {e}")
            summary[cid] = {"error": str(e)}
            continue

        # Parse results
        report_path = results_dir / f"{run_id}_{cid}" / "results.json"
        if report_path.exists():
            with open(report_path, "r") as f:
                report = json.load(f)
            resolved = sum(1 for v in report.values() if v.get("resolved", False))
            total = len(report)
            summary[cid] = {
                "resolved": resolved,
                "total": total,
                "pass_rate": resolved / total if total > 0 else 0,
            }
            print(f"  {cid}: {resolved}/{total} resolved ({summary[cid]['pass_rate']:.1%})")
        else:
            # Try to find report in default location
            print(f"  Report not found at {report_path}, checking alternatives...")
            summary[cid] = {"error": "report not found"}

    # Write summary
    summary_path = results_dir / "summary.json"
    with open(summary_path, "w") as f:
        json.dump(summary, f, indent=2)

    print(f"\n{'='*60}")
    print("SUMMARY")
    print(f"{'='*60}")
    for cid, result in sorted(summary.items()):
        if "error" in result:
            print(f"  {cid}: ERROR — {result['error']}")
        else:
            print(f"  {cid}: {result['resolved']}/{result['total']} ({result['pass_rate']:.1%})")
    print(f"\nSaved to: {summary_path}")


def main():
    parser = argparse.ArgumentParser(description="SWE-Bench Axiom Benchmark Harness")
    subparsers = parser.add_subparsers(dest="command")

    # Generate subcommand
    gen = subparsers.add_parser("generate", help="Generate patches via agent loop")
    gen.add_argument("--model", choices=["haiku", "sonnet", "opus"], default="haiku")
    gen.add_argument("--problems", type=int, default=None, help="Limit number of problems (for validation)")
    gen.add_argument("--conditions", nargs="+", default=CONDITION_IDS, help="Condition IDs to run (e.g., C0 C2)")
    gen.add_argument("--problem-ids", nargs="+", default=None, help="Specific problem IDs")
    gen.add_argument("--no-resume", action="store_true", help="Don't resume from existing predictions")
    gen.add_argument("--workers", type=int, default=1, help="Parallel workers (default 1, recommended 10)")

    # Evaluate subcommand
    ev = subparsers.add_parser("evaluate", help="Evaluate predictions with swebench")
    ev.add_argument("--predictions", required=True, help="Path to predictions.jsonl")
    ev.add_argument("--run-id", default="eval", help="Run ID for results")

    # Run subcommand (generate + evaluate)
    run = subparsers.add_parser("run", help="Generate + evaluate")
    run.add_argument("--model", choices=["haiku", "sonnet", "opus"], default="haiku")
    run.add_argument("--problems", type=int, default=None)
    run.add_argument("--conditions", nargs="+", default=CONDITION_IDS)
    run.add_argument("--workers", type=int, default=1)

    args = parser.parse_args()

    if args.command == "generate":
        generate_predictions(
            model_key=args.model,
            condition_ids=args.conditions,
            problem_ids=args.problem_ids,
            max_problems=args.problems,
            resume=not args.no_resume,
            workers=args.workers,
        )
    elif args.command == "evaluate":
        evaluate_predictions(args.predictions, args.run_id)
    elif args.command == "run":
        run_id, pred_path = generate_predictions(
            model_key=args.model,
            condition_ids=args.conditions,
            max_problems=args.problems,
            workers=args.workers,
        )
        evaluate_predictions(str(pred_path), run_id)
    else:
        parser.print_help()


if __name__ == "__main__":
    main()
