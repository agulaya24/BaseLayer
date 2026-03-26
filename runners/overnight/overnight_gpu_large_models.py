#!/usr/bin/env python3
"""
Overnight GPU Test -- Large Models (27B-32B) on Percepta Computational Tasks

Tests whether scale resolves the computation gap found in the percepta test:
  - mistral:7b scored 5% (1/20)
  - phi4:14b scored ~55% (10-11/20)
  - Do 27B-32B models cross into reliability?

Models tested:
  - qwen2.5:32b (~20GB, CPU offload on 10GB GPU, ~2-3 tok/s)
  - gemma2:27b (~16GB, CPU offload, ~3-4 tok/s)
  - deepseek-r1:32b (~20GB, thinking model, CPU offload, ~1-2 tok/s)

Same 20 tasks as percepta test. Slower per task (~2-5 min each vs 3-30s).
Estimated runtime: ~3-6 hours for all 3 models.

Run: PYTHONIOENCODING=utf-8 python overnight_gpu_large_models.py
Results: gpu_experiment_results/large_models/
"""

import json
import re
import time
import requests
from pathlib import Path
from datetime import datetime

OLLAMA_URL = "http://localhost:11434/api/generate"
RESULTS_DIR = Path("gpu_experiment_results/large_models")
RESULTS_DIR.mkdir(parents=True, exist_ok=True)

TIMESTAMP = datetime.now().strftime("%Y%m%d_%H%M%S")

# Large models -- these will use CPU offload on 10GB GPU
LARGE_MODELS = [
    "qwen2.5:32b",
    "gemma2:27b",
    "deepseek-r1:32b",
]

# Same tasks as percepta test
TASKS = {
    "arith_3digit": {
        "cat": "arithmetic", "diff": "medium",
        "prompt": "What is 347 x 892? Show work step by step, final answer on last line as just the number.",
        "answer": 309524,
        "verify": lambda r: _extract_number(r) == 309524,
    },
    "arith_4digit": {
        "cat": "arithmetic", "diff": "hard",
        "prompt": "What is 2847 x 6193? Show work, final answer on last line as just the number.",
        "answer": 17631471,
        "verify": lambda r: _extract_number(r) == 17631471,
    },
    "arith_5digit": {
        "cat": "arithmetic", "diff": "very_hard",
        "prompt": "What is 48271 x 93614? Show work, final answer on last line as just the number.",
        "answer": 4519289594,
        "verify": lambda r: _extract_number(r) == 4519289594,
    },
    "arith_addition": {
        "cat": "arithmetic", "diff": "medium",
        "prompt": "Calculate: 98765 + 87654 + 76543 + 65432 + 54321. Final answer on last line as just the number.",
        "answer": 382715,
        "verify": lambda r: _extract_number(r) == 382715,
    },
    "arith_chain": {
        "cat": "arithmetic", "diff": "hard",
        "prompt": "Calculate step by step: ((47 x 23) + 156) / 3 - 89. Final answer on last line.",
        "answer": 271.0,
        "verify": lambda r: abs((_extract_number(r) or -9999) - 271.0) < 0.01,
    },
    "arith_modular": {
        "cat": "arithmetic", "diff": "hard",
        "prompt": "What is 7^13 mod 11? Show work using repeated squaring. Final answer on last line.",
        "answer": 2,
        "verify": lambda r: _extract_number(r) == 2,
    },
    "arith_base_convert": {
        "cat": "arithmetic", "diff": "medium",
        "prompt": "Convert decimal 255 to binary. Show work. Binary number on last line.",
        "answer": "11111111",
        "verify": lambda r: "11111111" in r.replace(" ", ""),
    },
    "sudoku_4x4": {
        "cat": "sudoku", "diff": "easy",
        "prompt": "Solve 4x4 Sudoku (1-4 in rows/cols/2x2 boxes, 0=empty):\n1 0 0 4\n0 4 1 0\n0 1 4 0\n4 0 0 1\nOutput 4 rows of 4 numbers.",
        "answer": "1234/3412/2143/4321",
        "verify": lambda r: _verify_sudoku_4x4(r),
    },
    "sudoku_9x9": {
        "cat": "sudoku", "diff": "medium",
        "prompt": "Solve this 9x9 Sudoku. 0 means empty.\n5 3 0 0 7 0 0 0 0\n6 0 0 1 9 5 0 0 0\n0 9 8 0 0 0 0 6 0\n8 0 0 0 6 0 0 0 3\n4 0 0 8 0 3 0 0 1\n7 0 0 0 2 0 0 0 6\n0 6 0 0 0 0 2 8 0\n0 0 0 4 1 9 0 0 5\n0 0 0 0 8 0 0 7 9\nOutput the completed 9x9 grid, each row on its own line, numbers separated by spaces.",
        "answer": "solved",
        "verify": lambda r: _verify_sudoku_9x9(r),
    },
    "sort_10": {
        "cat": "sorting", "diff": "easy",
        "prompt": "Sort from smallest to largest: 42, 17, 93, 5, 68, 31, 84, 12, 56, 79. Final sorted list on last line.",
        "answer": [5,12,17,31,42,56,68,79,84,93],
        "verify": lambda r: _verify_sorted(r, [5,12,17,31,42,56,68,79,84,93]),
    },
    "sort_20": {
        "cat": "sorting", "diff": "medium",
        "prompt": "Sort smallest to largest: 73,14,88,3,45,92,27,61,38,56,81,19,7,66,34,50,95,22,11,77. Final sorted list on last line.",
        "answer": [3,7,11,14,19,22,27,34,38,45,50,56,61,66,73,77,81,88,92,95],
        "verify": lambda r: _verify_sorted(r, [3,7,11,14,19,22,27,34,38,45,50,56,61,66,73,77,81,88,92,95]),
    },
    "matrix_2x2": {
        "cat": "matrix", "diff": "easy",
        "prompt": "Multiply A=[[3,7],[2,5]] by B=[[6,4],[1,8]]. Show work. Result on last line as [[a,b],[c,d]].",
        "answer": [[25,68],[17,48]],
        "verify": lambda r: _verify_matrix(r, [[25,68],[17,48]]),
    },
    "matrix_3x3": {
        "cat": "matrix", "diff": "hard",
        "prompt": "Multiply A=[[1,2,3],[4,5,6],[7,8,9]] by B=[[9,8,7],[6,5,4],[3,2,1]]. Each result row on own line.",
        "answer": [[30,24,18],[84,69,54],[138,114,90]],
        "verify": lambda r: _verify_matrix(r, [[30,24,18],[84,69,54],[138,114,90]]),
    },
    "gcd": {
        "cat": "algorithm", "diff": "medium",
        "prompt": "Euclidean algorithm: GCD(1071, 462). Show each step. GCD on last line as just the number.",
        "answer": 21,
        "verify": lambda r: _extract_number(r) == 21,
    },
    "binary_search": {
        "cat": "algorithm", "diff": "medium",
        "prompt": "Binary search for 67 in [3,11,19,27,35,42,51,59,67,74,82,91]. Show each step. Index on last line.",
        "answer": 8,
        "verify": lambda r: _extract_number(r) == 8,
    },
    "fibonacci_15": {
        "cat": "algorithm", "diff": "easy",
        "prompt": "First 15 Fibonacci numbers starting F(1)=1, F(2)=1. Show steps. Sequence on last line, comma-separated.",
        "answer": [1,1,2,3,5,8,13,21,34,55,89,144,233,377,610],
        "verify": lambda r: _verify_sequence(r, [1,1,2,3,5,8,13,21,34,55,89,144,233,377,610]),
    },
    "collatz_27": {
        "cat": "algorithm", "diff": "hard",
        "prompt": "Collatz sequence from n=27 (even:n/2, odd:3n+1) until reaching 1. How many steps? Show first 20 values. Step count on last line.",
        "answer": 111,
        "verify": lambda r: _extract_number(r) == 111,
    },
    "count_letters": {
        "cat": "counting", "diff": "easy",
        "prompt": 'How many times does "e" appear in "nevertheless"? Count each one. Number on last line.',
        "answer": 3,
        "verify": lambda r: _extract_number(r) == 3,
    },
    "reverse_string": {
        "cat": "counting", "diff": "easy",
        "prompt": 'Reverse "computational" character by character. Reversed string on last line.',
        "answer": "lanoitatupmoc",
        "verify": lambda r: "lanoitatupmoc" in r.lower(),
    },
    "prime_check": {
        "cat": "algorithm", "diff": "medium",
        "prompt": "Is 997 prime? Test by dividing by all primes up to sqrt(997)~31.6. Show each division. Answer YES or NO on last line.",
        "answer": "YES",
        "verify": lambda r: "yes" in r.lower().split("\n")[-1].lower() or "prime" in r.lower().split("\n")[-1].lower(),
    },
}


def _extract_number(resp):
    lines = [l.strip() for l in resp.strip().split("\n") if l.strip()]
    for line in reversed(lines[-5:]):
        cleaned = line.replace(",", "")
        matches = re.findall(r'-?\d+\.?\d*', cleaned)
        if matches:
            val = matches[-1]
            return float(val) if "." in val else int(val)
    all_nums = re.findall(r'-?\d[\d,]*\.?\d*', resp.replace(",", ""))
    if all_nums:
        val = all_nums[-1]
        return float(val) if "." in val else int(val)
    return None


def _verify_sorted(resp, expected):
    lines = [l.strip() for l in resp.strip().split("\n") if l.strip()]
    for line in reversed(lines[-5:]):
        nums = [int(n) for n in re.findall(r'\d+', line)]
        if nums == expected:
            return True
    return False


def _verify_sequence(resp, expected):
    lines = [l.strip() for l in resp.strip().split("\n") if l.strip()]
    for line in reversed(lines[-5:]):
        nums = [int(n) for n in re.findall(r'\d+', line)]
        if len(nums) >= len(expected) and nums[:len(expected)] == expected:
            return True
    return False


def _verify_matrix(resp, expected):
    lines = [l.strip() for l in resp.strip().split("\n") if l.strip()]
    found = []
    for line in lines:
        nums = [int(n) for n in re.findall(r'-?\d+', line)]
        if len(nums) == len(expected[0]):
            found.append(nums)
    if len(found) >= len(expected):
        return found[-len(expected):] == expected
    return False


def _verify_sudoku_4x4(resp):
    lines = [l.strip() for l in resp.strip().split("\n") if l.strip()]
    grid = []
    for line in lines:
        nums = [int(n) for n in re.findall(r'[1-4]', line)]
        if len(nums) == 4:
            grid.append(nums)
    if len(grid) < 4:
        return False
    grid = grid[-4:]
    for row in grid:
        if sorted(row) != [1,2,3,4]:
            return False
    for c in range(4):
        if sorted(grid[r][c] for r in range(4)) != [1,2,3,4]:
            return False
    return True


def _verify_sudoku_9x9(resp):
    lines = [l.strip() for l in resp.strip().split("\n") if l.strip()]
    grid = []
    for line in lines:
        nums = [int(n) for n in re.findall(r'[1-9]', line)]
        if len(nums) == 9:
            grid.append(nums)
    if len(grid) < 9:
        return False
    grid = grid[-9:]
    target = list(range(1, 10))
    for row in grid:
        if sorted(row) != target:
            return False
    for c in range(9):
        if sorted(grid[r][c] for r in range(9)) != target:
            return False
    for br in range(3):
        for bc in range(3):
            box = [grid[br*3+r][bc*3+c] for r in range(3) for c in range(3)]
            if sorted(box) != target:
                return False
    return True


def ollama_generate(model, prompt, temperature=0.1, num_ctx=8192, timeout=600):
    payload = {
        "model": model, "prompt": prompt, "stream": False,
        "options": {"temperature": temperature, "num_ctx": num_ctx},
    }
    start = time.time()
    try:
        resp = requests.post(OLLAMA_URL, json=payload, timeout=timeout)
        resp.raise_for_status()
        data = resp.json()
        elapsed = time.time() - start
        meta = {
            "eval_count": data.get("eval_count", 0),
            "eval_duration": data.get("eval_duration", 0),
            "tokens_per_second": round(data.get("eval_count", 0) / max(data.get("eval_duration", 1) / 1e9, 0.001), 1),
        }
        return data.get("response", ""), elapsed, meta
    except requests.exceptions.Timeout:
        return "ERROR: Timeout", time.time() - start, {"error": "timeout", "tokens_per_second": 0, "eval_count": 0}
    except Exception as e:
        return f"ERROR: {e}", time.time() - start, {"error": str(e), "tokens_per_second": 0, "eval_count": 0}


def log(msg, f=None):
    ts = datetime.now().strftime("%H:%M:%S")
    line = f"[{ts}] {msg}"
    print(line, flush=True)
    if f:
        f.write(line + "\n")
        f.flush()


def main():
    logpath = RESULTS_DIR / f"overnight_large_{TIMESTAMP}.log"
    logfile = open(logpath, "w", encoding="utf-8")

    log("=" * 70, logfile)
    log("OVERNIGHT GPU TEST -- LARGE MODELS (27B-32B)", logfile)
    log(f"Started: {datetime.now().isoformat()}", logfile)
    log(f"Models: {LARGE_MODELS}", logfile)
    log(f"Tasks: {len(TASKS)}", logfile)
    log(f"Total runs: {len(LARGE_MODELS) * len(TASKS)}", logfile)
    log(f"Note: CPU offload on 10GB GPU. Expect 1-5 tok/s.", logfile)
    log("=" * 70, logfile)

    # Reference scores from percepta test
    log("\nReference scores:", logfile)
    log("  mistral:7b    1/20  (5%)   125 tok/s", logfile)
    log("  phi4:14b     ~11/20 (55%)  8.5 tok/s", logfile)
    log("  Question: does 27B-32B cross into reliability?\n", logfile)

    all_results = {
        "timestamp": TIMESTAMP,
        "models": LARGE_MODELS,
        "results": [],
        "summary": {},
    }

    for model in LARGE_MODELS:
        log(f"\n{'='*50}", logfile)
        log(f"MODEL: {model}", logfile)
        log(f"{'='*50}", logfile)

        model_correct = 0
        model_total = 0

        for tid, task in TASKS.items():
            log(f"  {tid:25s} ({task['diff']})", logfile)
            response, elapsed, meta = ollama_generate(
                model, task["prompt"],
                temperature=0.1,
                num_ctx=8192,
                timeout=600,
            )

            correct = False
            try:
                correct = task["verify"](response)
            except Exception:
                pass

            model_total += 1
            if correct:
                model_correct += 1

            result = {
                "model": model, "task_id": tid, "category": task["cat"],
                "difficulty": task["diff"], "correct": correct,
                "expected": str(task["answer"]),
                "elapsed": round(elapsed, 2),
                "tokens": meta.get("eval_count", 0),
                "tok_s": meta.get("tokens_per_second", 0),
                "response_preview": response[:500],
            }
            all_results["results"].append(result)

            status = "OK" if correct else "FAIL"
            log(f"    >> {status:7s} | {elapsed:6.1f}s | {meta.get('eval_count',0):5d} tok | {meta.get('tokens_per_second',0):5.1f} tok/s", logfile)

            # Save incrementally
            _save_results(all_results, RESULTS_DIR / f"results_{TIMESTAMP}.json")

        pct = model_correct / max(model_total, 1) * 100
        log(f"\n  {model} TOTAL: {model_correct}/{model_total} ({pct:.0f}%)", logfile)
        all_results["summary"][model] = {
            "correct": model_correct, "total": model_total, "pct": round(pct, 1)
        }

    # Final summary
    log(f"\n{'='*70}", logfile)
    log("FINAL COMPARISON", logfile)
    log(f"{'='*70}", logfile)
    log(f"\n  {'Model':25s} {'Correct':>8s} {'Total':>6s} {'Pct':>8s} {'Avg tok/s':>10s}", logfile)
    log(f"  {'-'*60}", logfile)
    log(f"  {'mistral:7b (ref)':25s} {'1':>8s} {'20':>6s} {'5.0%':>8s} {'125.0':>10s}", logfile)
    log(f"  {'phi4:14b (ref)':25s} {'~11':>8s} {'20':>6s} {'~55%':>8s} {'8.5':>10s}", logfile)

    for model in LARGE_MODELS:
        mr = [r for r in all_results["results"] if r["model"] == model]
        if mr:
            correct = sum(1 for r in mr if r["correct"])
            total = len(mr)
            avg_tps = sum(r["tok_s"] for r in mr) / len(mr)
            pct = f"{correct/total*100:.0f}%"
            log(f"  {model:25s} {correct:8d} {total:6d} {pct:>8s} {avg_tps:10.1f}", logfile)

    # Category breakdown
    categories = sorted(set(t["cat"] for t in TASKS.values()))
    log(f"\n  By category:", logfile)
    for cat in categories:
        log(f"    {cat}:", logfile)
        for model in LARGE_MODELS:
            cat_results = [r for r in all_results["results"] if r["model"] == model and r["category"] == cat]
            if cat_results:
                correct = sum(1 for r in cat_results if r["correct"])
                total = len(cat_results)
                log(f"      {model:25s} {correct}/{total}", logfile)

    _save_results(all_results, RESULTS_DIR / f"results_{TIMESTAMP}.json")
    log(f"\nCompleted: {datetime.now().isoformat()}", logfile)
    log(f"Results: {RESULTS_DIR / f'results_{TIMESTAMP}.json'}", logfile)
    logfile.close()
    print(f"\nDone. Results at {RESULTS_DIR / f'results_{TIMESTAMP}.json'}")


def _save_results(results, path):
    slim = json.loads(json.dumps(results, default=str))
    for r in slim.get("results", []):
        r.pop("full_response", None)
    with open(path, "w", encoding="utf-8") as f:
        json.dump(slim, f, indent=2, ensure_ascii=False)


if __name__ == "__main__":
    main()
