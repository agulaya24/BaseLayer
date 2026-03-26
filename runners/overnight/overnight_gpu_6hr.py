#!/usr/bin/env python3
"""
6-Hour Comprehensive GPU Overnight Run

Combines ALL local model testing into one marathon session:

  Phase 1: PERCEPTA COMPUTATIONAL TESTS (~2hr)
    - 20 tasks x 10 models = 200 runs
    - Arithmetic, sudoku, sorting, matrix, algorithm, logic, counting

  Phase 2: EXTRACTION QUALITY — MULTI-SUBJECT (~1.5hr)
    - 10 models x 5 subjects x 2 chunks = 100 runs
    - Tests document-mode + conversation-mode extraction
    - Quality: fact count, predicate diversity, object specificity

  Phase 3: EXTRACTION PROMPT VARIATIONS (~1hr)
    - 5 models x 4 prompt variants x 3 subjects = 60 runs
    - Baseline, constrained, chain-of-thought, document-worldview

  Phase 4: TEMPERATURE SWEEP (~30min)
    - 3 models x 5 temperatures x 2 tasks = 30 runs
    - Temp: 0.0, 0.1, 0.3, 0.5, 0.8

  Phase 5: AUTHORING QUALITY (~45min)
    - 5 models x 3 layers x 2 subjects = 30 runs
    - Anchors, Core, Predictions from pre-extracted facts

  Phase 6: FULL PIPELINE END-TO-END (~15min)
    - Best extraction model >> best authoring model >> compose
    - 2 subjects (Franklin, Kevin Kelly)

Total: ~420 runs across 10 models, ~6 hours
Results: gpu_experiment_results/6hr_comprehensive/

Run: python overnight_gpu_6hr.py
"""

import json
import os
import re
import sqlite3
import time
import requests
from pathlib import Path
from datetime import datetime

OLLAMA_URL = "http://localhost:11434/api/generate"
RESULTS_DIR = Path("gpu_experiment_results/6hr_comprehensive")
RESULTS_DIR.mkdir(parents=True, exist_ok=True)

TIMESTAMP = datetime.now().strftime("%Y%m%d_%H%M%S")
SUBJECTS_DIR = Path("C:/Users/Aarik/Anthropic/subjects")

# All 10 models
ALL_MODELS = [
    "mistral:7b", "phi4:14b", "gemma2:9b", "qwen2.5:7b", "qwen2.5:14b",
    "deepseek-r1:14b", "phi4-mini:3.8b", "llama3.2:3b",
    "sam860/LFM2:2.6b", "sam860/LFM2:350m",
]

# Top 5 for expensive tests
TOP_MODELS = ["mistral:7b", "phi4:14b", "gemma2:9b", "qwen2.5:14b", "deepseek-r1:14b"]

# Top 3 for most expensive tests
TOP3_MODELS = ["mistral:7b", "phi4:14b", "qwen2.5:14b"]

# Test subjects (varied sizes and types)
TEST_SUBJECTS = {
    "franklin_memory": {"type": "conversation", "expected_facts": 247},
    "kevin_kelly_memory": {"type": "conversation", "expected_facts": 2824},
    "marks_memory": {"type": "conversation", "expected_facts": 784},
    "paul_graham": {"type": "conversation", "expected_facts": 295},
    "scott_alexander_memory": {"type": "conversation", "expected_facts": 1478},
}


# ============================================================
# UTILITIES
# ============================================================

def ollama_generate(model, prompt, system="", temperature=0.1, num_ctx=8192, timeout=300):
    """Call Ollama API."""
    payload = {
        "model": model, "prompt": prompt, "stream": False,
        "options": {"temperature": temperature, "num_ctx": num_ctx},
    }
    if system:
        payload["system"] = system
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
        return "ERROR: Timeout", time.time() - start, {"error": "timeout"}
    except Exception as e:
        return f"ERROR: {e}", time.time() - start, {"error": str(e)}


def get_conversations(db_path, limit=10):
    """Get conversations from a subject DB."""
    conn = sqlite3.connect(str(db_path))
    conn.row_factory = sqlite3.Row
    convs = conn.execute("SELECT id, title FROM conversations ORDER BY id LIMIT ?", (limit,)).fetchall()
    results = []
    for conv in convs:
        msgs = conn.execute(
            "SELECT role, content_text as content FROM messages WHERE conversation_id = ? ORDER BY sequence_order",
            (conv["id"],)
        ).fetchall()
        text = "\n".join(f"{m['content']}" for m in msgs if m["content"])
        results.append({"id": conv["id"], "title": conv["title"], "text": text})
    conn.close()
    return results


def get_facts(db_path, limit=200):
    """Get existing facts from a subject DB."""
    conn = sqlite3.connect(str(db_path))
    conn.row_factory = sqlite3.Row
    rows = conn.execute(
        "SELECT fact_text, predicate, object_text, knowledge_tier, category, confidence "
        "FROM memory_facts WHERE predicate IS NOT NULL ORDER BY confidence DESC LIMIT ?", (limit,)
    ).fetchall()
    conn.close()
    return [dict(r) for r in rows]


def log(msg, f=None):
    ts = datetime.now().strftime("%H:%M:%S")
    line = f"[{ts}] {msg}"
    print(line, flush=True)
    if f:
        f.write(line + "\n")
        f.flush()


def save_results(results, path):
    """Save results, stripping full_response fields."""
    slim = json.loads(json.dumps(results, default=str))
    for phase in ["phase1", "phase2", "phase3", "phase4", "phase5", "phase6"]:
        for r in slim.get(phase, []):
            r.pop("full_response", None)
            r.pop("raw_response", None)
    with open(path, "w", encoding="utf-8") as f:
        json.dump(slim, f, indent=2, ensure_ascii=False)


# ============================================================
# PHASE 1: PERCEPTA COMPUTATIONAL TESTS
# ============================================================

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


COMPUTATIONAL_TASKS = {
    "arith_3digit": {
        "cat": "arithmetic", "diff": "medium",
        "prompt": "What is 347 × 892? Show work step by step, final answer on last line as just the number.",
        "answer": 309524,
        "verify": lambda r: _extract_number(r) == 309524,
    },
    "arith_4digit": {
        "cat": "arithmetic", "diff": "hard",
        "prompt": "What is 2847 × 6193? Show work, final answer on last line as just the number.",
        "answer": 17631471,
        "verify": lambda r: _extract_number(r) == 17631471,
    },
    "arith_5digit": {
        "cat": "arithmetic", "diff": "very_hard",
        "prompt": "What is 48271 × 93614? Show work, final answer on last line as just the number.",
        "answer": 4519289594,
        "verify": lambda r: _extract_number(r) == 4519289594,
    },
    "arith_chain": {
        "cat": "arithmetic", "diff": "hard",
        "prompt": "Calculate step by step: ((47 × 23) + 156) / 3 - 89. Final answer on last line.",
        "answer": 271.0,
        "verify": lambda r: abs((_extract_number(r) or -9999) - 271.0) < 0.01,
    },
    "arith_addition_long": {
        "cat": "arithmetic", "diff": "medium",
        "prompt": "Calculate: 98765 + 87654 + 76543 + 65432 + 54321. Final answer on last line as just the number.",
        "answer": 382715,
        "verify": lambda r: _extract_number(r) == 382715,
    },
    "sort_10": {
        "cat": "sorting", "diff": "easy",
        "prompt": "Sort from smallest to largest: 42, 17, 93, 5, 68, 31, 84, 12, 56, 79. Final sorted list on last line.",
        "answer": "5,12,17,31,42,56,68,79,84,93",
        "verify": lambda r: _verify_sorted(r, [5,12,17,31,42,56,68,79,84,93]),
    },
    "sort_20": {
        "cat": "sorting", "diff": "medium",
        "prompt": "Sort smallest to largest: 73,14,88,3,45,92,27,61,38,56,81,19,7,66,34,50,95,22,11,77. Final sorted list on last line.",
        "answer": "3,7,11,14,19,22,27,34,38,45,50,56,61,66,73,77,81,88,92,95",
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
        "answer": "1,1,2,3,5,8,13,21,34,55,89,144,233,377,610",
        "verify": lambda r: _verify_sequence(r, [1,1,2,3,5,8,13,21,34,55,89,144,233,377,610]),
    },
    "collatz_27": {
        "cat": "algorithm", "diff": "hard",
        "prompt": "Collatz sequence from n=27 (even:n/2, odd:3n+1) until reaching 1. How many steps? Show first 20 values. Step count on last line.",
        "answer": 111,
        "verify": lambda r: _extract_number(r) == 111,
    },
    "logic_seating": {
        "cat": "logic", "diff": "medium",
        "prompt": "5 people (Alice,Bob,Carol,Dave,Eve) in seats 1-5. Alice left of Bob. Carol in seat 3. Dave not next to Carol. Eve in seat 1 or 5. Bob in seat 4. Who sits where?",
        "answer": "Eve-1,Alice-2,Carol-3,Bob-4,Dave-5",
        "verify": lambda r: all(x in r.lower() for x in ["eve", "alice", "carol", "bob", "dave"]) and "eve" in r.lower().split("1")[0] if "1" in r else False,
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
    "sudoku_4x4": {
        "cat": "sudoku", "diff": "easy",
        "prompt": "Solve 4x4 Sudoku (1-4 in rows/cols/2x2 boxes, 0=empty):\n1 0 0 4\n0 4 1 0\n0 1 4 0\n4 0 0 1\nOutput 4 rows of 4 numbers.",
        "answer": "1234/3412/2143/4321",
        "verify": lambda r: _verify_sudoku_4x4(r),
    },
    "modular_arith": {
        "cat": "arithmetic", "diff": "hard",
        "prompt": "What is 7^13 mod 11? Show work using repeated squaring. Final answer on last line.",
        "answer": 2,
        "verify": lambda r: _extract_number(r) == 2,
    },
    "base_convert": {
        "cat": "arithmetic", "diff": "medium",
        "prompt": "Convert decimal 255 to binary. Show work. Binary number on last line.",
        "answer": "11111111",
        "verify": lambda r: "11111111" in r.replace(" ", ""),
    },
    "prime_check": {
        "cat": "algorithm", "diff": "medium",
        "prompt": "Is 997 prime? Test by dividing by all primes up to sqrt(997)≈31.6. Show each division. Answer YES or NO on last line.",
        "answer": "YES",
        "verify": lambda r: "yes" in r.lower().split("\n")[-1].lower() or "prime" in r.lower().split("\n")[-1].lower(),
    },
}


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


def run_phase1(all_results, logfile):
    """Phase 1: Percepta computational tests — all 10 models."""
    log(f"\n{'='*70}", logfile)
    log("PHASE 1: PERCEPTA COMPUTATIONAL TESTS (20 tasks × 10 models = 200 runs)", logfile)
    log(f"{'='*70}", logfile)

    for model in ALL_MODELS:
        log(f"\n--- {model} ---", logfile)
        for tid, task in COMPUTATIONAL_TASKS.items():
            log(f"  {tid:25s} ({task['diff']})", logfile)
            response, elapsed, meta = ollama_generate(model, task["prompt"], temperature=0.1, num_ctx=8192)
            correct = False
            try:
                correct = task["verify"](response)
            except Exception:
                pass
            result = {
                "model": model, "task_id": tid, "category": task["cat"],
                "difficulty": task["diff"], "correct": correct,
                "expected": str(task["answer"]),
                "elapsed": round(elapsed, 2),
                "tokens": meta.get("eval_count", 0),
                "tok_s": meta.get("tokens_per_second", 0),
                "response_preview": response[:300],
            }
            all_results["phase1"].append(result)
            status = "OK" if correct else "FAIL"
            log(f"    >> {status} | {elapsed:.1f}s | {meta.get('eval_count',0)} tok", logfile)
            save_results(all_results, RESULTS_DIR / f"results_{TIMESTAMP}.json")


# ============================================================
# PHASE 2: EXTRACTION QUALITY — MULTI-SUBJECT
# ============================================================

EXTRACT_PROMPTS = {
    "baseline": """Extract behavioral facts from this text about a person.
For each fact, output a JSON object with: subject, predicate (one of: believes, values, practices, avoids, fears, enjoys, excels_at, struggles_with, prioritizes, identifies_as, prefers), object, confidence (0-1).
Output ONLY a JSON array.

TEXT:
{text}""",

    "constrained": """You are extracting behavioral identity facts from text.
RULES:
1. Predicate MUST be one of: believes, values, practices, avoids, fears, enjoys, excels_at, struggles_with, prioritizes, identifies_as, experienced, decided, builds, founded, aspires_to, prefers, follows, monitors, maintains, hates, dislikes, loves
2. Extract IMPLICIT worldview, not just stated opinions
3. Focus on behavioral patterns, not biographical events
4. Confidence: 0.9+ explicit, 0.6-0.8 strong inference, 0.3-0.5 weak inference
OUTPUT: JSON array only. Each: {{"subject":"...","predicate":"...","object":"...","confidence":0.0-1.0}}

TEXT:
{text}""",

    "chain_of_thought": """Read this text carefully. First identify the author's core beliefs, values, and behavioral patterns. Then extract each as a structured fact.
Step 1: What does this person believe deeply? Value? Avoid?
Step 2: Create facts with predicate from: [believes, values, practices, avoids, fears, enjoys, excels_at, struggles_with, prioritizes, identifies_as, aspires_to, prefers]
Output analysis, then JSON array between ```json and ``` markers.

TEXT:
{text}""",

    "document_worldview": """You are extracting the IMPLICIT WORLDVIEW of a document. Treat it as a person — what does it "believe"? "value"? How does it "think"?
Extract up to 30 facts as structured triples.
For each: {{"subject":"this document","predicate":"<one of: believes,values,practices,avoids,prioritizes,struggles_with,excels_at,builds,prefers>","object":"<specific claim>","confidence":0.0-1.0}}
Output ONLY a JSON array.

DOCUMENT:
{text}""",
}


def parse_facts(response):
    """Extract JSON facts from response."""
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
    return [f for f in facts if isinstance(f, dict) and "predicate" in f and "object" in f]


def run_phase2(all_results, logfile):
    """Phase 2: Extraction quality across models and subjects."""
    log(f"\n{'='*70}", logfile)
    log("PHASE 2: EXTRACTION QUALITY (10 models × 5 subjects × 2 chunks = 100 runs)", logfile)
    log(f"{'='*70}", logfile)

    for subj_name, subj_info in TEST_SUBJECTS.items():
        db_path = SUBJECTS_DIR / subj_name / "data" / "database" / "memory.db"
        if not db_path.exists():
            log(f"  SKIP {subj_name}: DB not found", logfile)
            continue

        convos = get_conversations(db_path, limit=5)
        if not convos:
            continue

        # Take 2 chunks from different conversations
        chunks = []
        for c in convos[:2]:
            chunks.append({"name": c["title"][:30], "text": c["text"][:4000]})

        for model in ALL_MODELS:
            log(f"\n  {model} >> {subj_name}", logfile)
            for chunk in chunks:
                prompt = EXTRACT_PROMPTS["constrained"].format(text=chunk["text"])
                response, elapsed, meta = ollama_generate(model, prompt, temperature=0.2, num_ctx=8192)
                valid = parse_facts(response)

                predicates = set(f.get("predicate", "") for f in valid)
                avg_len = sum(len(f.get("object", "")) for f in valid) / max(len(valid), 1)

                result = {
                    "model": model, "subject": subj_name,
                    "chunk": chunk["name"],
                    "facts": len(valid),
                    "predicates": len(predicates),
                    "predicate_list": list(predicates),
                    "avg_object_len": round(avg_len, 1),
                    "elapsed": round(elapsed, 2),
                    "tok_s": meta.get("tokens_per_second", 0),
                    "parse_ok": len(valid) > 0,
                    "sample": [{"p": f.get("predicate"), "o": f.get("object", "")[:80]} for f in valid[:3]],
                }
                all_results["phase2"].append(result)
                log(f"    {chunk['name']:30s} >> {len(valid):3d} facts, {len(predicates)} preds, {elapsed:.1f}s", logfile)
                save_results(all_results, RESULTS_DIR / f"results_{TIMESTAMP}.json")


# ============================================================
# PHASE 3: PROMPT VARIATIONS
# ============================================================

def run_phase3(all_results, logfile):
    """Phase 3: Extraction prompt variations on top 5 models."""
    log(f"\n{'='*70}", logfile)
    log("PHASE 3: PROMPT VARIATIONS (5 models × 4 prompts × 3 subjects = 60 runs)", logfile)
    log(f"{'='*70}", logfile)

    test_subjects = ["franklin_memory", "kevin_kelly_memory", "marks_memory"]

    for subj_name in test_subjects:
        db_path = SUBJECTS_DIR / subj_name / "data" / "database" / "memory.db"
        convos = get_conversations(db_path, limit=3)
        if not convos:
            continue
        text = convos[0]["text"][:4000]

        for model in TOP_MODELS:
            log(f"\n  {model} >> {subj_name}", logfile)
            for prompt_name, prompt_template in EXTRACT_PROMPTS.items():
                prompt = prompt_template.format(text=text)
                response, elapsed, meta = ollama_generate(model, prompt, temperature=0.2, num_ctx=8192)
                valid = parse_facts(response)

                result = {
                    "model": model, "subject": subj_name,
                    "prompt_variant": prompt_name,
                    "facts": len(valid),
                    "predicates": len(set(f.get("predicate", "") for f in valid)),
                    "elapsed": round(elapsed, 2),
                    "tok_s": meta.get("tokens_per_second", 0),
                    "parse_ok": len(valid) > 0,
                }
                all_results["phase3"].append(result)
                log(f"    {prompt_name:20s} >> {len(valid):3d} facts, {elapsed:.1f}s", logfile)
                save_results(all_results, RESULTS_DIR / f"results_{TIMESTAMP}.json")


# ============================================================
# PHASE 4: TEMPERATURE SWEEP
# ============================================================

def run_phase4(all_results, logfile):
    """Phase 4: Temperature sweep on extraction + computation."""
    log(f"\n{'='*70}", logfile)
    log("PHASE 4: TEMPERATURE SWEEP (3 models × 5 temps × 2 tasks = 30 runs)", logfile)
    log(f"{'='*70}", logfile)

    temperatures = [0.0, 0.1, 0.3, 0.5, 0.8]

    # Get a sample text for extraction
    db_path = SUBJECTS_DIR / "franklin_memory" / "data" / "database" / "memory.db"
    convos = get_conversations(db_path, limit=1)
    sample_text = convos[0]["text"][:4000] if convos else ""

    for model in TOP3_MODELS:
        log(f"\n  {model}", logfile)
        for temp in temperatures:
            # Task 1: Extraction
            prompt = EXTRACT_PROMPTS["constrained"].format(text=sample_text)
            response, elapsed, meta = ollama_generate(model, prompt, temperature=temp, num_ctx=8192)
            valid = parse_facts(response)
            result = {
                "model": model, "task": "extraction", "temperature": temp,
                "facts": len(valid), "elapsed": round(elapsed, 2),
                "tok_s": meta.get("tokens_per_second", 0),
            }
            all_results["phase4"].append(result)
            log(f"    temp={temp:.1f} extract >> {len(valid):3d} facts, {elapsed:.1f}s", logfile)

            # Task 2: Arithmetic (deterministic task)
            arith_prompt = "What is 347 × 892? Show work. Final answer on last line as just the number."
            response, elapsed, meta = ollama_generate(model, arith_prompt, temperature=temp, num_ctx=8192)
            correct = _extract_number(response) == 309524
            result = {
                "model": model, "task": "arithmetic", "temperature": temp,
                "correct": correct, "elapsed": round(elapsed, 2),
                "tok_s": meta.get("tokens_per_second", 0),
            }
            all_results["phase4"].append(result)
            status = "OK" if correct else "FAIL"
            log(f"    temp={temp:.1f} arith   >> {status}, {elapsed:.1f}s", logfile)

            save_results(all_results, RESULTS_DIR / f"results_{TIMESTAMP}.json")


# ============================================================
# PHASE 5: AUTHORING QUALITY
# ============================================================

ANCHORS_PROMPT = """You have behavioral facts about a person. Synthesize 5-8 foundational axioms — beliefs so deep they function as cognitive infrastructure.
Good axioms: explain MULTIPLE facts, are predictive, capture HOW they think, specific to THIS person.

Facts:
{facts}

Output as JSON array: [{{"id":"A1","name":"SHORT ALL-CAPS","description":"2-3 sentences","activeWhen":"trigger","provenance":[1,5]}}]"""

CORE_PROMPT = """Given these behavioral facts, identify 4-6 "context modes" — distinct operational states this person enters.

Facts:
{facts}

JSON array: [{{"id":"C1","name":"SHORT ALL-CAPS","description":"2-3 sentences","triggers":"what activates","behaviors":"observable","provenance":[3,7]}}]"""

PREDICTIONS_PROMPT = """Given these facts, generate 4-6 falsifiable behavioral predictions. Must be specific, grounded in 2+ facts, about behavior not opinions.

Facts:
{facts}

JSON array: [{{"id":"P1","name":"SHORT ALL-CAPS","scenario":"specific situation","prediction":"what they'd do","confidence":0.7,"provenance":[2,8]}}]"""

COMPOSE_PROMPT = """Compose a unified narrative brief (800-1200 words) from these identity layers. No references to analysis process. Third person. Specific language.

AXIOMS: {anchors}
CONTEXT MODES: {core}
PREDICTIONS: {predictions}

Write the brief now. No preamble, no headers."""


def run_phase5(all_results, logfile):
    """Phase 5: Authoring quality across models."""
    log(f"\n{'='*70}", logfile)
    log("PHASE 5: AUTHORING QUALITY (5 models × 3 layers × 2 subjects = 30 runs)", logfile)
    log(f"{'='*70}", logfile)

    for subj_name in ["franklin_memory", "kevin_kelly_memory"]:
        db_path = SUBJECTS_DIR / subj_name / "data" / "database" / "memory.db"
        facts = get_facts(db_path, limit=80)
        if not facts:
            continue

        facts_text = "\n".join(f"{i+1}. [{f['predicate']}] {f['fact_text']}" for i, f in enumerate(facts))

        for model in TOP_MODELS:
            log(f"\n  {model} >> {subj_name}", logfile)

            for layer_name, layer_prompt in [("anchors", ANCHORS_PROMPT), ("core", CORE_PROMPT), ("predictions", PREDICTIONS_PROMPT)]:
                prompt = layer_prompt.format(facts=facts_text)
                response, elapsed, meta = ollama_generate(model, prompt, temperature=0.4, num_ctx=16384, timeout=600)

                # Parse
                items = []
                try:
                    match = re.search(r'\[.*\]', response, re.DOTALL)
                    if match:
                        items = json.loads(match.group())
                    elif "```json" in response:
                        match = re.search(r'```json\s*(.*?)```', response, re.DOTALL)
                        if match:
                            items = json.loads(match.group(1))
                except json.JSONDecodeError:
                    pass
                valid = [x for x in items if isinstance(x, dict) and ("name" in x or "id" in x)]

                result = {
                    "model": model, "subject": subj_name, "layer": layer_name,
                    "items": len(valid), "parse_ok": len(valid) > 0,
                    "elapsed": round(elapsed, 2),
                    "tok_s": meta.get("tokens_per_second", 0),
                    "raw_length": len(response),
                    "response_preview": response[:500],
                }
                all_results["phase5"].append(result)
                status = "OK" if valid else "FAIL"
                log(f"    {layer_name:12s} >> {status} ({len(valid)} items), {elapsed:.1f}s", logfile)
                save_results(all_results, RESULTS_DIR / f"results_{TIMESTAMP}.json")


# ============================================================
# PHASE 6: FULL PIPELINE END-TO-END
# ============================================================

def run_phase6(all_results, logfile):
    """Phase 6: Full pipeline — best models, end-to-end."""
    log(f"\n{'='*70}", logfile)
    log("PHASE 6: FULL PIPELINE END-TO-END", logfile)
    log(f"{'='*70}", logfile)

    # Find best extraction model from Phase 2
    phase2 = all_results.get("phase2", [])
    if not phase2:
        log("  SKIP: No Phase 2 results to determine best model", logfile)
        return

    model_scores = {}
    for r in phase2:
        m = r["model"]
        model_scores.setdefault(m, []).append(r["facts"])
    best_extract = max(model_scores, key=lambda m: sum(model_scores[m]) / len(model_scores[m]))

    # Find best authoring model from Phase 5
    phase5 = all_results.get("phase5", [])
    author_scores = {}
    for r in phase5:
        if r["parse_ok"]:
            author_scores.setdefault(r["model"], []).append(r["items"])
    best_author = max(author_scores, key=lambda m: sum(author_scores[m])) if author_scores else "phi4:14b"

    log(f"  Best extractor: {best_extract}", logfile)
    log(f"  Best author: {best_author}", logfile)

    for subj_name in ["franklin_memory", "marks_memory"]:
        log(f"\n  --- {subj_name} ---", logfile)
        db_path = SUBJECTS_DIR / subj_name / "data" / "database" / "memory.db"
        convos = get_conversations(db_path, limit=5)

        # Extract
        all_facts = []
        for conv in convos:
            prompt = EXTRACT_PROMPTS["constrained"].format(text=conv["text"][:4000])
            response, elapsed, meta = ollama_generate(best_extract, prompt, temperature=0.2, num_ctx=8192)
            facts = parse_facts(response)
            all_facts.extend(facts)
            log(f"    Extract: {conv['title'][:30]} >> {len(facts)} facts", logfile)

        log(f"    Total extracted: {len(all_facts)} facts", logfile)

        if len(all_facts) < 10:
            log(f"    Too few facts to author. Skipping.", logfile)
            continue

        # Author
        facts_text = "\n".join(f"{i+1}. [{f.get('predicate','')}] {f.get('object','')}" for i, f in enumerate(all_facts[:80]))

        anchors_resp, ae, _ = ollama_generate(best_author, ANCHORS_PROMPT.format(facts=facts_text), temperature=0.4, num_ctx=16384, timeout=600)
        core_resp, ce, _ = ollama_generate(best_author, CORE_PROMPT.format(facts=facts_text), temperature=0.4, num_ctx=16384, timeout=600)
        preds_resp, pe, _ = ollama_generate(best_author, PREDICTIONS_PROMPT.format(facts=facts_text), temperature=0.4, num_ctx=16384, timeout=600)

        anchors = parse_json_items(anchors_resp)
        core = parse_json_items(core_resp)
        preds = parse_json_items(preds_resp)

        log(f"    Author: A={len(anchors)} C={len(core)} P={len(preds)}", logfile)

        # Compose
        if anchors and core and preds:
            compose_prompt = COMPOSE_PROMPT.format(
                anchors=json.dumps(anchors)[:3000],
                core=json.dumps(core)[:3000],
                predictions=json.dumps(preds)[:3000],
            )
            brief, be, _ = ollama_generate(best_author, compose_prompt, temperature=0.5, num_ctx=16384, timeout=600)
            word_count = len(brief.split())

            result = {
                "subject": subj_name,
                "extract_model": best_extract,
                "author_model": best_author,
                "facts_extracted": len(all_facts),
                "anchors": len(anchors),
                "core": len(core),
                "predictions": len(preds),
                "brief_words": word_count,
                "brief_usable": word_count >= 300 and not brief.startswith("ERROR"),
                "brief_preview": brief[:800],
                "total_time": round(ae + ce + pe + be, 1),
            }
            all_results["phase6"].append(result)
            log(f"    Compose: {word_count} words, usable={result['brief_usable']}", logfile)
        else:
            log(f"    Authoring failed — cannot compose.", logfile)

        save_results(all_results, RESULTS_DIR / f"results_{TIMESTAMP}.json")


def parse_json_items(response):
    """Parse JSON array items from response."""
    try:
        match = re.search(r'\[.*\]', response, re.DOTALL)
        if match:
            items = json.loads(match.group())
            return [x for x in items if isinstance(x, dict)]
        if "```json" in response:
            match = re.search(r'```json\s*(.*?)```', response, re.DOTALL)
            if match:
                items = json.loads(match.group(1))
                return [x for x in items if isinstance(x, dict)]
    except json.JSONDecodeError:
        pass
    return []


# ============================================================
# SUMMARY
# ============================================================

def print_summary(all_results, logfile):
    log(f"\n{'='*70}", logfile)
    log("FINAL SUMMARY", logfile)
    log(f"{'='*70}", logfile)

    # Phase 1: Computational accuracy
    p1 = all_results.get("phase1", [])
    if p1:
        log(f"\n  PHASE 1 — COMPUTATIONAL ACCURACY:", logfile)
        model_acc = {}
        for r in p1:
            m = r["model"]
            model_acc.setdefault(m, {"c": 0, "t": 0})
            model_acc[m]["t"] += 1
            if r["correct"]:
                model_acc[m]["c"] += 1
        log(f"  {'Model':25s} {'Correct':>8s} {'Total':>6s} {'Pct':>8s}", logfile)
        for m in ALL_MODELS:
            if m in model_acc:
                s = model_acc[m]
                log(f"  {m:25s} {s['c']:8d} {s['t']:6d} {s['c']/s['t']*100:7.1f}%", logfile)

        # By category
        cat_acc = {}
        for r in p1:
            cat_acc.setdefault(r["category"], {"c": 0, "t": 0})
            cat_acc[r["category"]]["t"] += 1
            if r["correct"]:
                cat_acc[r["category"]]["c"] += 1
        log(f"\n  By category:", logfile)
        for cat, s in sorted(cat_acc.items()):
            log(f"    {cat:15s} {s['c']}/{s['t']} ({s['c']/s['t']*100:.0f}%)", logfile)

    # Phase 2: Extraction quality
    p2 = all_results.get("phase2", [])
    if p2:
        log(f"\n  PHASE 2 — EXTRACTION QUALITY:", logfile)
        model_facts = {}
        for r in p2:
            model_facts.setdefault(r["model"], []).append(r["facts"])
        log(f"  {'Model':25s} {'Avg Facts':>10s} {'Max':>6s} {'Parse%':>8s}", logfile)
        for m in ALL_MODELS:
            if m in model_facts:
                fs = model_facts[m]
                parse_rate = sum(1 for f in fs if f > 0) / len(fs) * 100
                log(f"  {m:25s} {sum(fs)/len(fs):10.1f} {max(fs):6d} {parse_rate:7.0f}%", logfile)

    # Phase 3: Prompt comparison
    p3 = all_results.get("phase3", [])
    if p3:
        log(f"\n  PHASE 3 — PROMPT VARIANT COMPARISON:", logfile)
        prompt_facts = {}
        for r in p3:
            prompt_facts.setdefault(r["prompt_variant"], []).append(r["facts"])
        for pn, fs in sorted(prompt_facts.items()):
            log(f"    {pn:20s} avg={sum(fs)/len(fs):.1f} facts", logfile)

    # Phase 4: Temperature
    p4 = all_results.get("phase4", [])
    if p4:
        log(f"\n  PHASE 4 — TEMPERATURE SWEEP:", logfile)
        for task_type in ["extraction", "arithmetic"]:
            log(f"    {task_type}:", logfile)
            for temp in [0.0, 0.1, 0.3, 0.5, 0.8]:
                runs = [r for r in p4 if r["task"] == task_type and r["temperature"] == temp]
                if runs:
                    if task_type == "extraction":
                        avg = sum(r["facts"] for r in runs) / len(runs)
                        log(f"      temp={temp:.1f}: avg {avg:.1f} facts", logfile)
                    else:
                        correct = sum(1 for r in runs if r.get("correct"))
                        log(f"      temp={temp:.1f}: {correct}/{len(runs)} correct", logfile)

    # Phase 5: Authoring
    p5 = all_results.get("phase5", [])
    if p5:
        log(f"\n  PHASE 5 — AUTHORING:", logfile)
        for model in TOP_MODELS:
            mr = [r for r in p5 if r["model"] == model]
            if mr:
                ok = sum(1 for r in mr if r["parse_ok"])
                log(f"  {model:25s} {ok}/{len(mr)} layers parsed", logfile)

    # Phase 6: Pipeline
    p6 = all_results.get("phase6", [])
    if p6:
        log(f"\n  PHASE 6 — FULL PIPELINE:", logfile)
        for r in p6:
            log(f"    {r['subject']}: {r['facts_extracted']} facts >> A:{r['anchors']} C:{r['core']} P:{r['predictions']} >> {r['brief_words']} words (usable={r['brief_usable']})", logfile)


# ============================================================
# MAIN
# ============================================================

def main():
    logpath = RESULTS_DIR / f"overnight_6hr_{TIMESTAMP}.log"
    logfile = open(logpath, "w", encoding="utf-8")

    log("=" * 70, logfile)
    log("6-HOUR COMPREHENSIVE GPU OVERNIGHT RUN", logfile)
    log(f"Started: {datetime.now().isoformat()}", logfile)
    log(f"Models: {len(ALL_MODELS)}", logfile)
    log(f"Estimated runs: ~420", logfile)
    log("=" * 70, logfile)

    all_results = {
        "timestamp": TIMESTAMP,
        "started": datetime.now().isoformat(),
        "config": {"all_models": ALL_MODELS, "top_models": TOP_MODELS, "top3": TOP3_MODELS},
        "phase1": [], "phase2": [], "phase3": [],
        "phase4": [], "phase5": [], "phase6": [],
    }

    run_phase1(all_results, logfile)
    run_phase2(all_results, logfile)
    run_phase3(all_results, logfile)
    run_phase4(all_results, logfile)
    run_phase5(all_results, logfile)
    run_phase6(all_results, logfile)

    all_results["completed"] = datetime.now().isoformat()
    print_summary(all_results, logfile)
    save_results(all_results, RESULTS_DIR / f"results_{TIMESTAMP}.json")

    log(f"\nCompleted: {datetime.now().isoformat()}", logfile)
    log(f"Results: {RESULTS_DIR / f'results_{TIMESTAMP}.json'}", logfile)
    logfile.close()
    print(f"\nDone. Results at {RESULTS_DIR / f'results_{TIMESTAMP}.json'}")


if __name__ == "__main__":
    main()
