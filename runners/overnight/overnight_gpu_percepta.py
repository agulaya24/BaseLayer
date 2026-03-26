#!/usr/bin/env python3
"""
Overnight GPU Percepta Paper Test — Can local LLMs compute?

Tests the core claim from "Can LLMs Be Computers?" (Percepta, March 2026):
LLMs struggle on simple computational tasks even when they can solve hard math problems.

Tests all 10 local Ollama models across 6 task categories:
  1. ARITHMETIC — multi-digit multiplication, addition, subtraction
  2. SUDOKU — 4x4 and 9x9 puzzles
  3. SORTING — bubble sort traces on number sequences
  4. MATRIX OPS — small matrix multiplication (2x2, 3x3)
  5. ALGORITHM EXECUTION — step-by-step algorithm traces (GCD, binary search)
  6. LOGIC PUZZLES — multi-step deduction chains

Each task has a known correct answer for automated scoring.
Measures: correctness, response time, token count, reasoning quality.

Run: python overnight_gpu_percepta.py
Results: gpu_experiment_results/percepta/
"""

import json
import os
import re
import time
import requests
from pathlib import Path
from datetime import datetime

OLLAMA_URL = "http://localhost:11434/api/generate"
RESULTS_DIR = Path("gpu_experiment_results/percepta")
RESULTS_DIR.mkdir(parents=True, exist_ok=True)

TIMESTAMP = datetime.now().strftime("%Y%m%d_%H%M%S")

# All 10 available local models
ALL_MODELS = [
    "mistral:7b",
    "phi4:14b",
    "gemma2:9b",
    "qwen2.5:7b",
    "qwen2.5:14b",
    "deepseek-r1:14b",
    "phi4-mini:3.8b",
    "llama3.2:3b",
    "sam860/LFM2:2.6b",
    "sam860/LFM2:350m",
]

# ============================================================
# TASK DEFINITIONS — each has prompt, correct answer, verifier
# ============================================================

TASKS = {
    # ── ARITHMETIC ──
    "arith_multiply_3digit": {
        "category": "arithmetic",
        "difficulty": "medium",
        "prompt": "What is 347 × 892? Show your work step by step, then give the final answer on the last line as just the number.",
        "answer": 309524,
        "verify": lambda resp: _extract_number(resp) == 309524,
    },
    "arith_multiply_4digit": {
        "category": "arithmetic",
        "difficulty": "hard",
        "prompt": "What is 2,847 × 6,193? Show your work step by step, then give the final answer on the last line as just the number.",
        "answer": 17631471,
        "verify": lambda resp: _extract_number(resp) == 17631471,
    },
    "arith_multiply_5digit": {
        "category": "arithmetic",
        "difficulty": "very_hard",
        "prompt": "What is 48,271 × 93,614? Show your work step by step, then give the final answer on the last line as just the number.",
        "answer": 4519289594,
        "verify": lambda resp: _extract_number(resp) == 4519289594,
    },
    "arith_addition_long": {
        "category": "arithmetic",
        "difficulty": "medium",
        "prompt": "Calculate: 98,765 + 87,654 + 76,543 + 65,432 + 54,321. Show your work, then give the final answer on the last line as just the number.",
        "answer": 382715,
        "verify": lambda resp: _extract_number(resp) == 382715,
    },
    "arith_chain": {
        "category": "arithmetic",
        "difficulty": "hard",
        "prompt": "Calculate step by step: ((47 × 23) + 156) / 3 - 89. Give the final answer on the last line as just the number.",
        "answer": 271.0,
        "verify": lambda resp: abs(_extract_float(resp) - 271.0) < 0.01,
    },

    # ── SUDOKU ──
    "sudoku_4x4": {
        "category": "sudoku",
        "difficulty": "easy",
        "prompt": """Solve this 4×4 Sudoku. Each row, column, and 2×2 box must contain 1-4.
0 means empty. Give the completed grid.

1 0 0 4
0 4 1 0
0 1 4 0
4 0 0 1

Output the solution as 4 rows of 4 numbers separated by spaces.""",
        "answer": "1 2 3 4\n3 4 1 2\n2 1 4 3\n4 3 2 1",
        "verify": lambda resp: _verify_sudoku_4x4(resp),
    },
    "sudoku_9x9_easy": {
        "category": "sudoku",
        "difficulty": "medium",
        "prompt": """Solve this 9×9 Sudoku. 0 means empty.

5 3 0 0 7 0 0 0 0
6 0 0 1 9 5 0 0 0
0 9 8 0 0 0 0 6 0
8 0 0 0 6 0 0 0 3
4 0 0 8 0 3 0 0 1
7 0 0 0 2 0 0 0 6
0 6 0 0 0 0 2 8 0
0 0 0 4 1 9 0 0 5
0 0 0 0 8 0 0 7 9

Output the completed 9×9 grid, each row on its own line, numbers separated by spaces.""",
        "answer": "5 3 4 6 7 8 9 1 2\n6 7 2 1 9 5 3 4 8\n1 9 8 3 4 2 5 6 7\n8 5 9 7 6 1 4 2 3\n4 2 6 8 5 3 7 9 1\n7 1 3 9 2 4 8 5 6\n9 6 1 5 3 7 2 8 4\n2 8 7 4 1 9 6 3 5\n3 4 5 2 8 6 1 7 9",
        "verify": lambda resp: _verify_sudoku_9x9(resp),
    },

    # ── SORTING ──
    "sort_10_numbers": {
        "category": "sorting",
        "difficulty": "easy",
        "prompt": "Sort these numbers from smallest to largest: 42, 17, 93, 5, 68, 31, 84, 12, 56, 79. Show each comparison/swap step, then give the final sorted list on the last line.",
        "answer": [5, 12, 17, 31, 42, 56, 68, 79, 84, 93],
        "verify": lambda resp: _extract_sorted_list(resp) == [5, 12, 17, 31, 42, 56, 68, 79, 84, 93],
    },
    "sort_20_numbers": {
        "category": "sorting",
        "difficulty": "medium",
        "prompt": "Sort these numbers from smallest to largest: 73, 14, 88, 3, 45, 92, 27, 61, 38, 56, 81, 19, 7, 66, 34, 50, 95, 22, 11, 77. Give the final sorted list on the last line, comma-separated.",
        "answer": [3, 7, 11, 14, 19, 22, 27, 34, 38, 45, 50, 56, 61, 66, 73, 77, 81, 88, 92, 95],
        "verify": lambda resp: _extract_sorted_list(resp) == [3, 7, 11, 14, 19, 22, 27, 34, 38, 45, 50, 56, 61, 66, 73, 77, 81, 88, 92, 95],
    },

    # ── MATRIX OPS ──
    "matrix_2x2_multiply": {
        "category": "matrix",
        "difficulty": "easy",
        "prompt": """Multiply these two 2×2 matrices. Show your work.

A = [[3, 7],
     [2, 5]]

B = [[6, 4],
     [1, 8]]

Give the result matrix on the last line as [[a,b],[c,d]].""",
        "answer": [[25, 68], [17, 48]],
        "verify": lambda resp: _verify_matrix(resp, [[25, 68], [17, 48]]),
    },
    "matrix_3x3_multiply": {
        "category": "matrix",
        "difficulty": "hard",
        "prompt": """Multiply these two 3×3 matrices. Show your work.

A = [[1, 2, 3],
     [4, 5, 6],
     [7, 8, 9]]

B = [[9, 8, 7],
     [6, 5, 4],
     [3, 2, 1]]

Give the result matrix, each row on its own line.""",
        "answer": [[30, 24, 18], [84, 69, 54], [138, 114, 90]],
        "verify": lambda resp: _verify_matrix(resp, [[30, 24, 18], [84, 69, 54], [138, 114, 90]]),
    },

    # ── ALGORITHM EXECUTION ──
    "gcd_euclidean": {
        "category": "algorithm",
        "difficulty": "medium",
        "prompt": "Use the Euclidean algorithm to find GCD(1071, 462). Show each step (division, remainder). Give the final GCD on the last line as just the number.",
        "answer": 21,
        "verify": lambda resp: _extract_number(resp) == 21,
    },
    "binary_search_trace": {
        "category": "algorithm",
        "difficulty": "medium",
        "prompt": """Trace a binary search for the value 67 in this sorted array:
[3, 11, 19, 27, 35, 42, 51, 59, 67, 74, 82, 91]

Show each step: the current range [low, high], the midpoint index, the value at midpoint, and which half you search next. How many comparisons does it take? Give the index of 67 on the last line.""",
        "answer": 8,
        "verify": lambda resp: _extract_number(resp) == 8,
    },
    "fibonacci_sequence": {
        "category": "algorithm",
        "difficulty": "easy",
        "prompt": "Calculate the first 15 Fibonacci numbers starting from F(1)=1, F(2)=1. Show each step. Give the final sequence on the last line as comma-separated numbers.",
        "answer": [1, 1, 2, 3, 5, 8, 13, 21, 34, 55, 89, 144, 233, 377, 610],
        "verify": lambda resp: _extract_sorted_list(resp, require_sorted=False) == [1, 1, 2, 3, 5, 8, 13, 21, 34, 55, 89, 144, 233, 377, 610],
    },
    "collatz_steps": {
        "category": "algorithm",
        "difficulty": "hard",
        "prompt": "Starting from n=27, apply the Collatz conjecture (if even: n/2, if odd: 3n+1) until you reach 1. How many steps does it take? Show the first 20 values in the sequence, then give the total step count on the last line as just the number.",
        "answer": 111,
        "verify": lambda resp: _extract_number(resp) == 111,
    },

    # ── LOGIC PUZZLES ──
    "logic_deduction": {
        "category": "logic",
        "difficulty": "medium",
        "prompt": """Five people (Alice, Bob, Carol, Dave, Eve) sit in a row of 5 seats (1-5, left to right).
- Alice sits to the left of Bob.
- Carol sits in seat 3.
- Dave does not sit next to Carol.
- Eve sits in seat 1 or seat 5.
- Bob sits in seat 4.

What seat does each person sit in? Give the answer as: Seat 1: X, Seat 2: X, Seat 3: X, Seat 4: X, Seat 5: X""",
        "answer": {"1": "Eve", "2": "Alice", "3": "Carol", "4": "Bob", "5": "Dave"},
        "verify": lambda resp: _verify_seating(resp, {"1": "Eve", "2": "Alice", "3": "Carol", "4": "Bob", "5": "Dave"}),
    },
    "logic_knights_knaves": {
        "category": "logic",
        "difficulty": "hard",
        "prompt": """On an island, knights always tell the truth and knaves always lie.
You meet three people: A, B, and C.
A says: "B is a knave."
B says: "A and C are the same type (both knights or both knaves)."
C says: "A is a knight."

Determine who is a knight and who is a knave. Show your reasoning step by step. On the last line, state: A=knight/knave, B=knight/knave, C=knight/knave""",
        "answer": {"A": "knight", "B": "knave", "C": "knight"},
        "verify": lambda resp: _verify_knights(resp, {"A": "knight", "B": "knave", "C": "knight"}),
    },

    # ── COUNTING / TRACKING (Percepta's key failure mode) ──
    "count_letters": {
        "category": "counting",
        "difficulty": "easy",
        "prompt": 'How many times does the letter "e" appear in the word "nevertheless"? Count each occurrence. Give the number on the last line.',
        "answer": 3,
        "verify": lambda resp: _extract_number(resp) == 3,
    },
    "count_words": {
        "category": "counting",
        "difficulty": "medium",
        "prompt": 'Count the number of words in this sentence: "The quick brown fox jumps over the lazy dog and then the fox runs around the big red barn while the dog sleeps peacefully under the old oak tree." Give the count on the last line as just the number.',
        "answer": 30,
        "verify": lambda resp: _extract_number(resp) == 30,
    },
    "reverse_string": {
        "category": "counting",
        "difficulty": "easy",
        "prompt": 'Reverse the string "computational" character by character. Show each step. Give the reversed string on the last line.',
        "answer": "lanoitatupmoc",
        "verify": lambda resp: "lanoitatupmoc" in resp.lower(),
    },
}


# ============================================================
# VERIFICATION HELPERS
# ============================================================

def _extract_number(resp: str) -> int | float | None:
    """Extract the last number from a response."""
    # Look for numbers in the last few lines
    lines = [l.strip() for l in resp.strip().split("\n") if l.strip()]
    for line in reversed(lines[-5:]):
        # Remove commas from numbers
        cleaned = line.replace(",", "").replace(" ", "")
        # Try to find a number
        matches = re.findall(r'-?\d+\.?\d*', cleaned)
        if matches:
            val = matches[-1]
            return float(val) if "." in val else int(val)
    # Fallback: search entire response for the last number
    all_nums = re.findall(r'-?\d[\d,]*\.?\d*', resp.replace(",", ""))
    if all_nums:
        val = all_nums[-1]
        return float(val) if "." in val else int(val)
    return None


def _extract_float(resp: str) -> float:
    """Extract a float from response."""
    num = _extract_number(resp)
    return float(num) if num is not None else -99999


def _extract_sorted_list(resp: str, require_sorted: bool = True) -> list[int] | None:
    """Extract a list of numbers from the last line."""
    lines = [l.strip() for l in resp.strip().split("\n") if l.strip()]
    for line in reversed(lines[-5:]):
        nums = re.findall(r'\d+', line)
        if len(nums) >= 5:
            result = [int(n) for n in nums]
            return result
    return None


def _verify_sudoku_4x4(resp: str) -> bool:
    """Verify a 4x4 sudoku solution."""
    lines = [l.strip() for l in resp.strip().split("\n") if l.strip()]
    grid = []
    for line in lines:
        nums = re.findall(r'[1-4]', line)
        if len(nums) == 4:
            grid.append([int(n) for n in nums])
    if len(grid) < 4:
        return False
    grid = grid[-4:]  # Take last 4 rows
    # Check rows
    for row in grid:
        if sorted(row) != [1, 2, 3, 4]:
            return False
    # Check columns
    for c in range(4):
        col = [grid[r][c] for r in range(4)]
        if sorted(col) != [1, 2, 3, 4]:
            return False
    return True


def _verify_sudoku_9x9(resp: str) -> bool:
    """Verify a 9x9 sudoku solution."""
    lines = [l.strip() for l in resp.strip().split("\n") if l.strip()]
    grid = []
    for line in lines:
        nums = re.findall(r'[1-9]', line)
        if len(nums) == 9:
            grid.append([int(n) for n in nums])
    if len(grid) < 9:
        return False
    grid = grid[-9:]
    target = list(range(1, 10))
    # Check rows
    for row in grid:
        if sorted(row) != target:
            return False
    # Check columns
    for c in range(9):
        col = [grid[r][c] for r in range(9)]
        if sorted(col) != target:
            return False
    # Check 3x3 boxes
    for br in range(3):
        for bc in range(3):
            box = []
            for r in range(br*3, br*3+3):
                for c in range(bc*3, bc*3+3):
                    box.append(grid[r][c])
            if sorted(box) != target:
                return False
    return True


def _verify_matrix(resp: str, expected: list[list[int]]) -> bool:
    """Verify matrix multiplication result."""
    # Try to extract numbers from last few lines
    lines = [l.strip() for l in resp.strip().split("\n") if l.strip()]
    found_rows = []
    for line in lines:
        nums = re.findall(r'-?\d+', line)
        if len(nums) == len(expected[0]):
            found_rows.append([int(n) for n in nums])
    if len(found_rows) >= len(expected):
        result = found_rows[-len(expected):]
        return result == expected
    return False


def _verify_seating(resp: str, expected: dict) -> bool:
    """Verify seating arrangement."""
    resp_lower = resp.lower()
    for seat, person in expected.items():
        # Look for "seat N: Person" or "N: Person" patterns
        patterns = [
            f"seat {seat}: {person.lower()}",
            f"seat {seat} - {person.lower()}",
            f"{seat}: {person.lower()}",
            f"seat {seat}.*{person.lower()}",
        ]
        found = any(re.search(p, resp_lower) for p in patterns)
        if not found:
            return False
    return True


def _verify_knights(resp: str, expected: dict) -> bool:
    """Verify knights and knaves answer."""
    resp_lower = resp.lower()
    for person, role in expected.items():
        pattern = f"{person.lower()}.*{role}"
        if not re.search(pattern, resp_lower):
            # Also check reverse: "knight...A"
            pattern2 = f"{role}.*{person.lower()}"
            if not re.search(pattern2, resp_lower):
                return False
    return True


# ============================================================
# RUNNER
# ============================================================

def ollama_generate(model: str, prompt: str, temperature: float = 0.1,
                    num_ctx: int = 8192, timeout: int = 300) -> tuple[str, float, dict]:
    """Call Ollama API. Returns (response, elapsed, metadata)."""
    payload = {
        "model": model,
        "prompt": prompt,
        "stream": False,
        "options": {"temperature": temperature, "num_ctx": num_ctx},
    }

    start = time.time()
    try:
        resp = requests.post(OLLAMA_URL, json=payload, timeout=timeout)
        resp.raise_for_status()
        data = resp.json()
        elapsed = time.time() - start

        meta = {
            "total_duration": data.get("total_duration", 0),
            "eval_count": data.get("eval_count", 0),
            "eval_duration": data.get("eval_duration", 0),
            "prompt_eval_count": data.get("prompt_eval_count", 0),
        }
        # Calculate tok/s
        if meta["eval_duration"] > 0:
            meta["tokens_per_second"] = round(
                meta["eval_count"] / (meta["eval_duration"] / 1e9), 1
            )
        else:
            meta["tokens_per_second"] = 0

        return data.get("response", ""), elapsed, meta
    except requests.exceptions.Timeout:
        return "ERROR: Timeout", time.time() - start, {"error": "timeout"}
    except Exception as e:
        return f"ERROR: {e}", time.time() - start, {"error": str(e)}


def log(msg: str, f=None):
    ts = datetime.now().strftime("%H:%M:%S")
    line = f"[{ts}] {msg}"
    print(line, flush=True)
    if f:
        f.write(line + "\n")
        f.flush()


def run_task(model: str, task_id: str, task: dict, logfile) -> dict:
    """Run a single task on a single model."""
    log(f"  {model:25s} | {task_id:30s} | {task['difficulty']:10s}", logfile)

    response, elapsed, meta = ollama_generate(
        model, task["prompt"],
        temperature=0.1,
        num_ctx=8192,
        timeout=300,
    )

    correct = False
    try:
        correct = task["verify"](response)
    except Exception:
        pass

    result = {
        "model": model,
        "task_id": task_id,
        "category": task["category"],
        "difficulty": task["difficulty"],
        "correct": correct,
        "expected_answer": str(task["answer"]),
        "elapsed_seconds": round(elapsed, 2),
        "tokens_generated": meta.get("eval_count", 0),
        "tokens_per_second": meta.get("tokens_per_second", 0),
        "response_length": len(response),
        "response_preview": response[:500],
        "full_response": response,
    }

    status = "CORRECT" if correct else "WRONG"
    log(f"    >> {status:7s} | {elapsed:6.1f}s | {meta.get('eval_count', 0):5d} tok | {meta.get('tokens_per_second', 0):5.1f} tok/s", logfile)

    return result


# ============================================================
# EXTRACTION QUALITY TEST (bonus: test document extraction across models)
# ============================================================

DOCUMENT_EXTRACT_PROMPT = """You are extracting the IMPLICIT WORLDVIEW of a document. Treat this document as if it were a person — what does it "believe"? What does it "value"? How does it "think"?

<document_content>
{text}
</document_content>

Extract up to 30 facts about this document's worldview as structured triples.

For each fact, provide a JSON object with:
- subject: "this document"
- predicate: one of [believes, values, practices, avoids, prioritizes, struggles_with, excels_at, builds, prefers]
- object: the specific claim (be concrete)
- confidence: 0.0-1.0

Output ONLY a JSON array. No explanation."""


def run_extraction_quality_test(model: str, text: str, doc_name: str, logfile) -> dict:
    """Test extraction quality on a document chunk."""
    log(f"  Extraction: {model:25s} | {doc_name}", logfile)

    prompt = DOCUMENT_EXTRACT_PROMPT.format(text=text[:6000])
    response, elapsed, meta = ollama_generate(model, prompt, temperature=0.2, num_ctx=8192, timeout=300)

    facts = []
    try:
        match = re.search(r'\[.*\]', response, re.DOTALL)
        if match:
            facts = json.loads(match.group())
        elif "```json" in response:
            match = re.search(r'```json\s*(.*?)```', response, re.DOTALL)
            if match:
                facts = json.loads(match.group(1))
    except json.JSONDecodeError:
        pass

    valid = [f for f in facts if isinstance(f, dict) and "predicate" in f and "object" in f]

    # Quality metrics
    predicates_used = set(f.get("predicate", "") for f in valid)
    avg_obj_len = sum(len(f.get("object", "")) for f in valid) / max(len(valid), 1)

    result = {
        "model": model,
        "doc_name": doc_name,
        "facts_extracted": len(valid),
        "unique_predicates": len(predicates_used),
        "predicates": list(predicates_used),
        "avg_object_length": round(avg_obj_len, 1),
        "elapsed_seconds": round(elapsed, 2),
        "tokens_per_second": meta.get("tokens_per_second", 0),
        "sample_facts": [{"predicate": f.get("predicate"), "object": f.get("object", "")[:100]} for f in valid[:5]],
        "parse_success": len(valid) > 0,
    }

    log(f"    >> {len(valid):3d} facts | {len(predicates_used)} predicates | {elapsed:5.1f}s | {meta.get('tokens_per_second', 0):5.1f} tok/s", logfile)
    return result


# ============================================================
# MAIN
# ============================================================

def main():
    logpath = RESULTS_DIR / f"overnight_percepta_{TIMESTAMP}.log"
    logfile = open(logpath, "w", encoding="utf-8")

    log("=" * 70, logfile)
    log("OVERNIGHT GPU TEST -- PERCEPTA PAPER: CAN LOCAL LLMs COMPUTE?", logfile)
    log(f"Started: {datetime.now().isoformat()}", logfile)
    log(f"Models: {len(ALL_MODELS)}", logfile)
    log(f"Tasks: {len(TASKS)}", logfile)
    log(f"Total runs: {len(ALL_MODELS) * len(TASKS)}", logfile)
    log("=" * 70, logfile)

    all_results = {
        "timestamp": TIMESTAMP,
        "config": {
            "models": ALL_MODELS,
            "tasks": list(TASKS.keys()),
            "total_runs": len(ALL_MODELS) * len(TASKS),
        },
        "computational_results": [],
        "extraction_results": [],
        "summary": {},
    }

    # ── Phase 1: Computational Tasks ──
    log(f"\n{'='*70}", logfile)
    log("PHASE 1: COMPUTATIONAL TASK EXECUTION", logfile)
    log(f"{'='*70}", logfile)

    for model in ALL_MODELS:
        log(f"\n--- {model} ---", logfile)
        for task_id, task in TASKS.items():
            result = run_task(model, task_id, task, logfile)
            all_results["computational_results"].append(result)

            # Save incrementally in case of crash
            _save_results(all_results, RESULTS_DIR / f"results_{TIMESTAMP}.json")

    # ── Phase 2: Document Extraction Quality (bonus test) ──
    log(f"\n{'='*70}", logfile)
    log("PHASE 2: DOCUMENT EXTRACTION QUALITY", logfile)
    log(f"{'='*70}", logfile)

    # Load a chunk of the agentic patterns textbook
    agentic_path = Path("C:/Users/Aarik/Anthropic/subjects/agentic_patterns/data/raw/agentic_design_patterns.txt")
    if agentic_path.exists():
        with open(agentic_path, "r", encoding="utf-8") as f:
            agentic_text = f.read()

        # Test 3 chunks from different parts of the book
        chunk_size = 6000
        chunks = [
            ("chapter_1_prompt_chaining", agentic_text[3000:3000+chunk_size]),
            ("chapter_8_memory_mgmt", agentic_text[len(agentic_text)//3:len(agentic_text)//3+chunk_size]),
            ("chapter_17_reasoning", agentic_text[2*len(agentic_text)//3:2*len(agentic_text)//3+chunk_size]),
        ]

        # Test top 5 models only (to save time)
        extraction_models = ["mistral:7b", "phi4:14b", "gemma2:9b", "qwen2.5:14b", "deepseek-r1:14b"]

        for model in extraction_models:
            for chunk_name, chunk_text in chunks:
                result = run_extraction_quality_test(model, chunk_text, chunk_name, logfile)
                all_results["extraction_results"].append(result)

                _save_results(all_results, RESULTS_DIR / f"results_{TIMESTAMP}.json")
    else:
        log("  SKIPPED: agentic_patterns source file not found", logfile)

    # ── Summary ──
    log(f"\n{'='*70}", logfile)
    log("SUMMARY", logfile)
    log(f"{'='*70}", logfile)

    # Compute per-model accuracy
    model_scores = {}
    for r in all_results["computational_results"]:
        m = r["model"]
        if m not in model_scores:
            model_scores[m] = {"correct": 0, "total": 0, "categories": {}}
        model_scores[m]["total"] += 1
        if r["correct"]:
            model_scores[m]["correct"] += 1
        cat = r["category"]
        if cat not in model_scores[m]["categories"]:
            model_scores[m]["categories"][cat] = {"correct": 0, "total": 0}
        model_scores[m]["categories"][cat]["total"] += 1
        if r["correct"]:
            model_scores[m]["categories"][cat]["correct"] += 1

    log("\n  OVERALL ACCURACY (by model):", logfile)
    log(f"  {'Model':25s} {'Correct':>8s} {'Total':>6s} {'Accuracy':>10s}", logfile)
    log(f"  {'-'*55}", logfile)
    for model in ALL_MODELS:
        if model in model_scores:
            s = model_scores[model]
            pct = f"{s['correct']/s['total']*100:.1f}%"
            log(f"  {model:25s} {s['correct']:8d} {s['total']:6d} {pct:>10s}", logfile)

    # Per-category breakdown
    categories = sorted(set(t["category"] for t in TASKS.values()))
    log(f"\n  ACCURACY BY CATEGORY:", logfile)
    header = f"  {'Model':25s}" + "".join(f" {c:>12s}" for c in categories)
    log(header, logfile)
    log(f"  {'-'*(25 + 13*len(categories))}", logfile)
    for model in ALL_MODELS:
        if model in model_scores:
            s = model_scores[model]
            row = f"  {model:25s}"
            for cat in categories:
                if cat in s["categories"]:
                    cs = s["categories"][cat]
                    row += f" {cs['correct']}/{cs['total']:>5s}" if isinstance(cs['total'], str) else f"  {cs['correct']}/{cs['total']:>9}"
                else:
                    row += f" {'n/a':>12s}"
            log(row, logfile)

    # Speed comparison
    log(f"\n  SPEED (avg tokens/sec by model):", logfile)
    for model in ALL_MODELS:
        model_results = [r for r in all_results["computational_results"] if r["model"] == model]
        if model_results:
            avg_tps = sum(r["tokens_per_second"] for r in model_results) / len(model_results)
            avg_time = sum(r["elapsed_seconds"] for r in model_results) / len(model_results)
            log(f"  {model:25s} {avg_tps:6.1f} tok/s  {avg_time:6.1f}s avg", logfile)

    # Difficulty analysis
    log(f"\n  ACCURACY BY DIFFICULTY (all models):", logfile)
    for diff in ["easy", "medium", "hard", "very_hard"]:
        diff_results = [r for r in all_results["computational_results"] if r["difficulty"] == diff]
        if diff_results:
            correct = sum(1 for r in diff_results if r["correct"])
            total = len(diff_results)
            log(f"  {diff:12s} {correct}/{total} ({correct/total*100:.1f}%)", logfile)

    # Extraction summary
    if all_results["extraction_results"]:
        log(f"\n  EXTRACTION QUALITY:", logfile)
        log(f"  {'Model':25s} {'Avg Facts':>10s} {'Avg Preds':>10s} {'Parse %':>8s}", logfile)
        for model in ["mistral:7b", "phi4:14b", "gemma2:9b", "qwen2.5:14b", "deepseek-r1:14b"]:
            mr = [r for r in all_results["extraction_results"] if r["model"] == model]
            if mr:
                avg_facts = sum(r["facts_extracted"] for r in mr) / len(mr)
                avg_preds = sum(r["unique_predicates"] for r in mr) / len(mr)
                parse_pct = sum(1 for r in mr if r["parse_success"]) / len(mr) * 100
                log(f"  {model:25s} {avg_facts:10.1f} {avg_preds:10.1f} {parse_pct:7.0f}%", logfile)

    all_results["summary"] = model_scores

    # Final save
    results_path = RESULTS_DIR / f"results_{TIMESTAMP}.json"
    _save_results(all_results, results_path)

    log(f"\nCompleted: {datetime.now().isoformat()}", logfile)
    log(f"Results: {results_path}", logfile)
    log(f"Log: {logpath}", logfile)
    logfile.close()

    print(f"\nDone. Results at {results_path}")
    print(f"Log at {logpath}")


def _save_results(results: dict, path: Path):
    """Save results JSON (exclude full_response to keep file size manageable)."""
    # Create a copy without full responses for the main results file
    slim = json.loads(json.dumps(results, default=str))
    for r in slim.get("computational_results", []):
        if "full_response" in r:
            del r["full_response"]
    with open(path, "w", encoding="utf-8") as f:
        json.dump(slim, f, indent=2, ensure_ascii=False)


if __name__ == "__main__":
    main()
