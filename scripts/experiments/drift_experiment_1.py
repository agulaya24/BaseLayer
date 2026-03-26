"""
Drift Experiment 1: Single-Fact Injection

Measures behavioral drift when a single fact is added to a coding agent's brief.
Supports both Anthropic API and local Ollama models.

Protocol:
  1. Run 5 mechanical coding probes with CodeBot brief → T0 baseline
  2. Inject one fact into the brief
  3. Re-run probes → T1 responses
  4. Extract axioms from both response sets
  5. Compute drift metrics (Axiom Delta, Behavioral Probe Delta, Specificity Ratio)

Usage:
  python drift_experiment_1.py --ollama phi4-mini:3.8b          # Local model (fast test)
  python drift_experiment_1.py --ollama qwen2.5:7b              # Local model
  python drift_experiment_1.py --model claude-haiku-4-5-20251001  # API (cheap)
  python drift_experiment_1.py --model claude-sonnet-4-20250514   # API (quality)
  python drift_experiment_1.py --baseline-only                  # Just T0
  python drift_experiment_1.py --fact-index 0                   # Single fact test
"""

import argparse
import json
import os
import sys
import time
import requests
from datetime import datetime
from pathlib import Path

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
from api_client import embed_texts

# ---------------------------------------------------------------------------
# CODEBOT AGENT BRIEF
# ---------------------------------------------------------------------------

BRIEFS = {
    # --- CONDITION 1: Full behavioral brief (prose + structured) ---
    "brief": """## Injectable Block

**BEHAVIORAL DIRECTIVES**

You are a coding agent. You write, review, debug, and architect software. Your responses should be code-first — show the solution, then explain if needed.

**CORE PATTERNS**

- Prefers functional patterns over class hierarchies
- Writes tests first, then implementation
- Favors readability over cleverness — "clear > smart"
- Avoids premature abstraction — three similar blocks before extracting
- Decomposes into small functions (< 20 lines each)
- TypeScript by default, Python when appropriate
- Names things precisely — long descriptive names over short cryptic ones

**ARCHITECTURE PREFERENCES**

- Start simple, add complexity only when load demands it
- Prefer libraries over custom implementations
- Flat file structures over deep nesting
- Configuration over convention when behavior is non-obvious
- Explicit error handling at boundaries, trust internals

**CODE REVIEW PRIORITIES**

1. Correctness — does it do what it claims?
2. Security — input validation, injection, auth
3. Readability — can someone else understand this in 6 months?
4. Performance — only if there's evidence of a bottleneck
5. Style — lowest priority, automate with linters

**DEBUGGING APPROACH**

- Reproduce first, hypothesize second
- Read the error message carefully before anything else
- Check the simplest explanation first
- Add logging before adding breakpoints
- Never "fix" something you can't explain

**TRADEOFF DEFAULTS**

- Ship > perfect (but never ship broken)
- Delete code > comment it out
- Boring technology > exciting technology for production
- Explicit > implicit
- Small PRs > large PRs
""",

    # --- CONDITION 2: Axiom list (compressed behavioral principles) ---
    "axioms": """You are a coding agent. Respond based on these behavioral axioms:

1. READABILITY IS A SOCIAL CONTRACT — Code is read 10x more than written. Optimize for the reader in 6 months, not the writer today.
2. COMPLEXITY MUST BE EARNED — Never add abstraction until three concrete cases prove the need. Resist architecture that outpaces actual load.
3. TESTS ARE PROOF, NOT CEREMONY — A code path without a test is a claim without evidence. No exceptions.
4. REPRODUCE BEFORE HYPOTHESIZING — Never theorize about a bug you haven't seen fail. The error message is the first witness.
5. SECURITY AT BOUNDARIES, TRUST INTERNALS — Validate everything that enters the system. Once inside, trust the contracts.
6. SHIP BORING TECHNOLOGY — Exciting tools are liabilities in production. Choose the well-understood option unless performance data forces otherwise.
7. EXPLICIT OVER IMPLICIT — If behavior isn't obvious from the code, make it obvious. Configuration over convention when stakes are high.
8. SMALL SURFACE AREA — Small functions, small PRs, small modules. Decompose until each piece does exactly one thing.
""",

    # --- CONDITION 3: Atomic preferences (flat fact list) ---
    "atomic": """You are a coding agent. Here are your preferences:

- Prefers TypeScript
- Prefers functional patterns
- Likes small functions
- Writes tests
- Values readability
- Uses libraries when possible
- Prefers simple architecture
- Cares about security
- Favors explicit code
- Prefers small PRs
- Uses logging for debugging
- Prefers boring technology
- Likes descriptive variable names
- Reviews code for correctness first
- Avoids premature optimization
""",
}

# Default brief for backwards compatibility
CODEBOT_BRIEF = BRIEFS["brief"]

# ---------------------------------------------------------------------------
# MECHANICAL CODING PROBES — 5 tasks testing different behavioral dimensions
# ---------------------------------------------------------------------------

PROBES = {
    "architecture": {
        "id": "architecture",
        "question": """We need a user notification system. Requirements:
- Send email, SMS, and push notifications
- Users can set preferences for which channels they want
- Templates for different notification types (welcome, password reset, order confirmation)
- Rate limiting to prevent spam

Design the system. Show the key interfaces/types and the main send function. Keep it practical — this is a startup with 10K users, not Google.""",
    },
    "debugging": {
        "id": "debugging",
        "question": """This endpoint intermittently returns 500 errors, about 5% of requests. The error log shows:

```
TypeError: Cannot read properties of undefined (reading 'email')
  at getUserProfile (/src/handlers/profile.ts:47)
  at processRequest (/src/middleware/auth.ts:23)
```

Here's the relevant code:

```typescript
// auth.ts
async function processRequest(req: Request) {
  const token = req.headers.authorization?.split(' ')[1];
  const session = await redis.get(`session:${token}`);
  const user = JSON.parse(session);
  return getUserProfile(user);
}

// profile.ts
function getUserProfile(user: User) {
  return {
    name: user.name,
    email: user.email,
    avatar: user.avatar || '/default.png'
  };
}
```

What's happening and how do you fix it?""",
    },
    "refactoring": {
        "id": "refactoring",
        "question": """Refactor this function. It works but it's a mess:

```typescript
async function handleOrder(order: any) {
  // check if order is valid
  if (!order.items || order.items.length === 0) {
    console.log('no items');
    return { error: 'no items' };
  }
  if (!order.userId) {
    console.log('no user');
    return { error: 'no user' };
  }
  // calculate total
  let total = 0;
  for (let i = 0; i < order.items.length; i++) {
    const item = order.items[i];
    const product = await db.query('SELECT * FROM products WHERE id = ?', [item.productId]);
    if (!product) {
      console.log('product not found: ' + item.productId);
      return { error: 'product not found' };
    }
    if (product.stock < item.quantity) {
      console.log('insufficient stock for ' + item.productId);
      return { error: 'insufficient stock' };
    }
    total += product.price * item.quantity;
    // apply discount if any
    if (order.coupon) {
      const coupon = await db.query('SELECT * FROM coupons WHERE code = ?', [order.coupon]);
      if (coupon && coupon.valid && new Date(coupon.expires) > new Date()) {
        if (coupon.type === 'percent') {
          total = total - (total * coupon.discount / 100);
        } else {
          total = total - coupon.discount;
        }
      }
    }
  }
  // charge
  const charge = await stripe.charges.create({ amount: Math.round(total * 100), currency: 'usd', customer: order.userId });
  if (!charge.id) {
    return { error: 'payment failed' };
  }
  // update stock
  for (let i = 0; i < order.items.length; i++) {
    await db.query('UPDATE products SET stock = stock - ? WHERE id = ?', [order.items[i].quantity, order.items[i].productId]);
  }
  // send email
  await sendEmail(order.userId, 'Order confirmed', 'Your order total: $' + total);
  return { success: true, chargeId: charge.id, total: total };
}
```

Show me the refactored version.""",
    },
    "tradeoff": {
        "id": "tradeoff",
        "question": """We're building a real-time collaborative document editor (like Google Docs). The team is debating two approaches:

**Option A: CRDTs (Conflict-free Replicated Data Types)**
- No central server needed for conflict resolution
- Works offline
- Complex to implement, especially for rich text
- Libraries exist (Yjs, Automerge) but are large dependencies

**Option B: Operational Transform (OT) with a central server**
- Well-understood algorithm (Google Docs uses it)
- Requires always-on server connection
- Simpler mental model
- We'd need to implement or find a good library

Context: 4-person startup, MVP needed in 6 weeks, expecting ~100 concurrent users initially. Team has experience with neither approach.

What do you recommend and why?""",
    },
    "security": {
        "id": "security",
        "question": """Review this API endpoint for security issues. List what you'd fix and show the corrected code:

```typescript
app.post('/api/users/update', async (req, res) => {
  const { userId, updates } = req.body;

  // Update user record
  const result = await db.query(
    `UPDATE users SET ${Object.keys(updates).map(k => `${k} = '${updates[k]}'`).join(', ')} WHERE id = '${userId}'`
  );

  // Log the change
  await db.query(
    `INSERT INTO audit_log (action, details) VALUES ('user_update', '${JSON.stringify(updates)}')`
  );

  // Return updated user
  const user = await db.query(`SELECT * FROM users WHERE id = '${userId}'`);
  res.json(user);
});
```""",
    },
}

# ---------------------------------------------------------------------------
# INJECTION FACTS — targeted at specific coding behavioral dimensions
# ---------------------------------------------------------------------------

INJECTION_FACTS = [
    {
        "id": "F-TEST",
        "fact": "This person's production system crashed due to an untested edge case in a clever optimization, costing 3 days of downtime. They now require explicit tests for every code path before merging, and reject any PR that doesn't include tests — no exceptions.",
        "target_dimension": "debugging",
        "expected_direction": "more test-obsessive, reject cleverness harder",
    },
    {
        "id": "F-SIMPLE",
        "fact": "This person's team spent 2 months building a microservice architecture that should have been a single module with 3 functions. They now viscerally resist architectural complexity and will argue against any abstraction that isn't proven necessary by current production load.",
        "target_dimension": "architecture",
        "expected_direction": "more aggressively simple, anti-abstraction",
    },
    {
        "id": "F-SECURITY",
        "fact": "This person shipped a feature without input validation that led to a SQL injection attack exposing 50,000 user records. They now treat security validation as the absolute first priority in any code review — before correctness, readability, or performance.",
        "target_dimension": "security",
        "expected_direction": "security-first in all contexts, not just security probes",
    },
]

# ---------------------------------------------------------------------------
# SYSTEM PROMPT
# ---------------------------------------------------------------------------

SYSTEM_PROMPT = """You are a coding agent. Respond to tasks based on the behavioral brief below. Stay in character — your coding style, preferences, and decision-making should reflect the brief. Be concise and practical.

--- BEHAVIORAL BRIEF ---
{brief}
--- END BRIEF ---"""

AXIOM_EXTRACTION_PROMPT = """Analyze these responses from a coding agent across multiple tasks. Extract the behavioral axioms — the underlying engineering beliefs, preferences, and reasoning patterns driving their decisions.

For each axiom:
- One sentence stating the principle
- Which task responses (by ID) provide evidence

Return ONLY a JSON array: [{{"axiom": "...", "evidence": ["task_id", ...]}}]

--- RESPONSES ---
{responses}
---

Valid JSON only. No markdown fencing. No explanation."""

# ---------------------------------------------------------------------------
# OLLAMA CLIENT
# ---------------------------------------------------------------------------

def call_ollama(model, messages, system=None, max_tokens=150, temperature=0.3):
    """Call a local Ollama model. Returns a dict matching the shape we need."""
    url = "http://localhost:11434/api/chat"

    ollama_messages = []
    if system:
        ollama_messages.append({"role": "system", "content": system})
    ollama_messages.extend(messages)

    payload = {
        "model": model,
        "messages": ollama_messages,
        "stream": False,
        "options": {
            "num_predict": max_tokens,
            "temperature": temperature,
        },
    }

    start = time.time()
    resp = requests.post(url, json=payload, timeout=300)
    elapsed = time.time() - start
    resp.raise_for_status()
    data = resp.json()

    text = data.get("message", {}).get("content", "")
    eval_count = data.get("eval_count", len(text.split()))
    prompt_count = data.get("prompt_eval_count", 0)

    return {
        "text": text,
        "tokens_in": prompt_count,
        "tokens_out": eval_count,
        "elapsed": round(elapsed, 1),
        "tok_per_sec": round(eval_count / elapsed, 1) if elapsed > 0 else 0,
    }


def call_model(model, messages, system=None, max_tokens=150, temperature=0.3, use_ollama=False):
    """Unified call interface for both API and Ollama."""
    if use_ollama:
        result = call_ollama(model, messages, system, max_tokens, temperature)
        return result
    else:
        from api_client import call_api
        response = call_api(
            model=model,
            messages=messages,
            system=system,
            max_tokens=max_tokens,
            temperature=temperature,
            caller="drift_exp1",
        )
        return {
            "text": response.content[0].text,
            "tokens_in": response.usage.input_tokens,
            "tokens_out": response.usage.output_tokens,
            "elapsed": 0,
            "tok_per_sec": 0,
        }


# ---------------------------------------------------------------------------
# RUNNER
# ---------------------------------------------------------------------------

def run_probes(brief, model, use_ollama, label="T0", max_tokens=150):
    """Run all probes. Returns dict of responses."""
    system = SYSTEM_PROMPT.format(brief=brief)
    results = {}
    total = len(PROBES)

    for i, (dim, probe) in enumerate(PROBES.items(), 1):
        pid = probe["id"]
        print(f"  [{label}] Probe {i}/{total}: {pid}", file=sys.stderr, end="", flush=True)

        result = call_model(
            model=model,
            messages=[{"role": "user", "content": probe["question"]}],
            system=system,
            max_tokens=max_tokens,
            temperature=0.3,
            use_ollama=use_ollama,
        )

        results[pid] = {
            "dimension": dim,
            "question": probe["question"],
            "response": result["text"],
            "tokens_in": result["tokens_in"],
            "tokens_out": result["tokens_out"],
            "elapsed": result["elapsed"],
            "tok_per_sec": result["tok_per_sec"],
        }

        if use_ollama:
            print(f" ({result['elapsed']}s, {result['tok_per_sec']} tok/s)", file=sys.stderr)
        else:
            print(f" ({result['tokens_out']} tokens)", file=sys.stderr)

    return results


def extract_axioms(responses, model, use_ollama):
    """Extract behavioral axioms from probe responses."""
    formatted = []
    for pid, data in sorted(responses.items()):
        formatted.append(f"[{pid}] Task: {data['question'][:100]}...\nResponse: {data['response']}\n")

    prompt = AXIOM_EXTRACTION_PROMPT.format(responses="\n".join(formatted))

    result = call_model(
        model=model,
        messages=[{"role": "user", "content": prompt}],
        max_tokens=2000,
        temperature=0,
        use_ollama=use_ollama,
    )

    text = result["text"].strip()
    # Strip markdown fencing
    if text.startswith("```"):
        lines = text.split("\n")
        text = "\n".join(lines[1:])
        if text.endswith("```"):
            text = text[:-3]
        text = text.strip()

    # Try to find JSON array in the response
    start_idx = text.find("[")
    end_idx = text.rfind("]")
    if start_idx != -1 and end_idx != -1:
        text = text[start_idx:end_idx + 1]

    try:
        axioms = json.loads(text)
        if not isinstance(axioms, list):
            axioms = [axioms]
    except json.JSONDecodeError:
        print(f"  WARNING: Failed to parse axiom JSON", file=sys.stderr)
        print(f"  Raw: {text[:200]}...", file=sys.stderr)
        axioms = [{"axiom": text, "evidence": [], "parse_error": True}]

    return axioms


def compute_probe_delta(t0_responses, t1_responses):
    """Embedding-based behavioral probe delta."""
    probe_ids = sorted(t0_responses.keys())
    t0_texts = [t0_responses[pid]["response"] for pid in probe_ids]
    t1_texts = [t1_responses[pid]["response"] for pid in probe_ids]

    t0_emb = embed_texts(t0_texts)
    t1_emb = embed_texts(t1_texts)

    if t0_emb is None or t1_emb is None:
        return None

    import numpy as np
    deltas = {}
    for i, pid in enumerate(probe_ids):
        v0, v1 = np.array(t0_emb[i]), np.array(t1_emb[i])
        cos_sim = np.dot(v0, v1) / (np.linalg.norm(v0) * np.linalg.norm(v1))
        deltas[pid] = round(float(1 - cos_sim), 4)
    return deltas


def compute_axiom_delta(t0_axioms, t1_axioms):
    """Compare axiom sets via embedding similarity."""
    t0_texts = [a.get("axiom", str(a)) for a in t0_axioms]
    t1_texts = [a.get("axiom", str(a)) for a in t1_axioms]

    if not t0_texts or not t1_texts:
        return {"error": "empty axiom set"}

    t0_emb = embed_texts(t0_texts)
    t1_emb = embed_texts(t1_texts)

    if t0_emb is None or t1_emb is None:
        return {"error": "embedding model unavailable"}

    import numpy as np
    t0_arr, t1_arr = np.array(t0_emb), np.array(t1_emb)

    matched, unmatched_t1 = [], []
    for j, t1_ax in enumerate(t1_axioms):
        sims = [float(np.dot(t0_arr[i], t1_arr[j]) / (np.linalg.norm(t0_arr[i]) * np.linalg.norm(t1_arr[j]))) for i in range(len(t0_arr))]
        best_i = int(np.argmax(sims))
        best_sim = sims[best_i]
        if best_sim >= 0.85:
            matched.append({"t0": t0_axioms[best_i].get("axiom", ""), "t1": t1_ax.get("axiom", ""), "sim": round(best_sim, 4)})
        else:
            unmatched_t1.append({"axiom": t1_ax.get("axiom", ""), "best_match": t0_axioms[best_i].get("axiom", ""), "sim": round(best_sim, 4)})

    # Find lost T0 axioms
    t0_matched = set()
    for j in range(len(t1_arr)):
        sims = [float(np.dot(t0_arr[i], t1_arr[j]) / (np.linalg.norm(t0_arr[i]) * np.linalg.norm(t1_arr[j]))) for i in range(len(t0_arr))]
        if max(sims) >= 0.85:
            t0_matched.add(int(np.argmax(sims)))
    lost = [{"axiom": t0_axioms[i].get("axiom", "")} for i in range(len(t0_axioms)) if i not in t0_matched]

    total = max(len(t0_axioms), len(t1_axioms))
    changed = len(unmatched_t1) + len(lost)

    return {
        "t0_count": len(t0_axioms), "t1_count": len(t1_axioms),
        "matched": len(matched), "new": len(unmatched_t1), "lost": len(lost),
        "axiom_delta": round(changed / total, 4) if total > 0 else 0,
        "matched_pairs": matched, "new_axioms": unmatched_t1, "lost_axioms": lost,
    }


def inject_fact(brief, fact_text):
    """Inject a fact at the end of the brief."""
    return brief + f"\n\n**ADDITIONAL BEHAVIORAL EVIDENCE**\n\n{fact_text}\n"


def print_summary(results):
    """Print a human-readable summary to stderr."""
    print(f"\n{'='*60}", file=sys.stderr)
    print(f"DRIFT EXPERIMENT 1 — RESULTS SUMMARY", file=sys.stderr)
    print(f"{'='*60}", file=sys.stderr)
    print(f"Model: {results['model']}", file=sys.stderr)
    print(f"T0 axioms: {len(results.get('t0_axioms', []))}", file=sys.stderr)

    for inj in results.get("injections", []):
        fid = inj["fact_id"]
        ad = inj.get("axiom_delta", {})
        pd = inj.get("probe_deltas", {})

        print(f"\n--- {fid} ({inj['target_dimension']}) ---", file=sys.stderr)
        print(f"  Expected: {inj['expected_direction']}", file=sys.stderr)

        if ad and "axiom_delta" in ad:
            print(f"  Axiom Delta: {ad['axiom_delta']} ({ad.get('new',0)} new, {ad.get('lost',0)} lost)", file=sys.stderr)

        if pd:
            target = inj["target_dimension"]
            target_d = pd.get(target, None)
            others = [v for k, v in pd.items() if k != target]
            other_mean = round(sum(others) / len(others), 4) if others else 0

            print(f"  Probe deltas:", file=sys.stderr)
            for pid, delta in sorted(pd.items(), key=lambda x: -x[1]):
                marker = " <-- TARGET" if pid == target else ""
                print(f"    {pid}: {delta}{marker}", file=sys.stderr)

            if target_d is not None and other_mean > 0:
                sr = round(target_d / other_mean, 2)
                print(f"  Specificity Ratio: {sr} (target={target_d}, others_avg={other_mean})", file=sys.stderr)
                if sr > 1.5:
                    print(f"  --> TARGETED DRIFT (fact affected intended dimension)", file=sys.stderr)
                elif sr > 0.8:
                    print(f"  --> DIFFUSE DRIFT (fact affected all dimensions similarly)", file=sys.stderr)
                else:
                    print(f"  --> WEAK/NO DRIFT on target", file=sys.stderr)

    # Timing
    total_elapsed = sum(r.get("elapsed", 0) for r in results.get("t0_responses", {}).values())
    for inj in results.get("injections", []):
        # estimate T1 time same as T0
        total_elapsed *= 2
    if total_elapsed > 0:
        print(f"\nTotal estimated runtime: {total_elapsed:.0f}s ({total_elapsed/60:.1f}m)", file=sys.stderr)


def run_single_condition(model, use_ollama, brief_text, brief_type, max_tokens, facts, baseline_only=False):
    """Run one condition (one brief type). Returns results dict."""
    results = {"brief_type": brief_type, "brief_chars": len(brief_text)}

    print(f"\n{'='*50}", file=sys.stderr)
    print(f"  CONDITION: {brief_type.upper()} (model={model})", file=sys.stderr)
    print(f"{'='*50}", file=sys.stderr)

    # T0
    print(f"\n  T0 baseline...", file=sys.stderr)
    start = time.time()
    t0_responses = run_probes(brief_text, model, use_ollama, label=f"T0-{brief_type}", max_tokens=max_tokens)
    results["t0_elapsed"] = round(time.time() - start, 1)
    results["t0_responses"] = t0_responses

    print(f"  Extracting T0 axioms...", file=sys.stderr)
    t0_axioms = extract_axioms(t0_responses, model, use_ollama)
    results["t0_axioms"] = t0_axioms
    print(f"  T0 axioms: {len(t0_axioms)}", file=sys.stderr)
    for ax in t0_axioms:
        if not ax.get("parse_error"):
            print(f"    - {ax.get('axiom', '???')[:80]}", file=sys.stderr)

    if baseline_only:
        return results

    # Injections
    results["injections"] = []
    for fact_info in facts:
        fid = fact_info["id"]
        print(f"\n  Injection: {fid} → {fact_info['target_dimension']}", file=sys.stderr)

        modified = inject_fact(brief_text, fact_info["fact"])
        t1_responses = run_probes(modified, model, use_ollama, label=f"T1-{brief_type}-{fid}", max_tokens=max_tokens)

        t1_axioms = extract_axioms(t1_responses, model, use_ollama)
        probe_deltas = compute_probe_delta(t0_responses, t1_responses)
        axiom_delta = compute_axiom_delta(t0_axioms, t1_axioms)

        results["injections"].append({
            "fact_id": fid,
            "fact": fact_info["fact"],
            "target_dimension": fact_info["target_dimension"],
            "expected_direction": fact_info["expected_direction"],
            "t1_responses": t1_responses,
            "t1_axioms": t1_axioms,
            "axiom_delta": axiom_delta,
            "probe_deltas": probe_deltas,
        })

    return results


def run_experiment(args):
    use_ollama = args.ollama is not None
    model = args.ollama if use_ollama else args.model
    max_tokens = args.max_tokens

    output_dir = Path(os.path.dirname(__file__)) / "drift_results"
    output_dir.mkdir(exist_ok=True)

    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    model_tag = model.replace(":", "_").replace("/", "_")

    # Determine which brief types to run
    if args.brief_type == "all":
        brief_types = ["brief", "axioms", "atomic"]
    else:
        brief_types = [args.brief_type]

    facts = INJECTION_FACTS
    if args.fact_index is not None:
        facts = [INJECTION_FACTS[args.fact_index]]

    results = {
        "experiment": "drift_experiment_1",
        "timestamp": timestamp,
        "model": model,
        "backend": "ollama" if use_ollama else "anthropic",
        "max_tokens": max_tokens,
        "brief_types": brief_types,
        "conditions": {},
    }

    # ---- RUN CONDITIONS ----
    for bt in brief_types:
        brief_text = BRIEFS[bt]
        condition_results = run_single_condition(
            model, use_ollama, brief_text, bt, max_tokens, facts, args.baseline_only
        )
        results["conditions"][bt] = condition_results

    # ---- SAVE ----
    suffix = "_".join(brief_types)
    outfile = output_dir / f"drift_exp1_{model_tag}_{suffix}_{timestamp}.json"
    with open(outfile, "w", encoding="utf-8") as f:
        json.dump(results, f, indent=2, ensure_ascii=False)

    # ---- CROSS-CONDITION SUMMARY ----
    print(f"\n{'='*60}", file=sys.stderr)
    print(f"CROSS-CONDITION SUMMARY", file=sys.stderr)
    print(f"{'='*60}", file=sys.stderr)
    print(f"Model: {model}", file=sys.stderr)

    for bt, cond in results["conditions"].items():
        t0_ax = len(cond.get("t0_axioms", []))
        print(f"\n  [{bt.upper()}] T0 axioms: {t0_ax}, brief chars: {cond['brief_chars']}", file=sys.stderr)

        for inj in cond.get("injections", []):
            fid = inj["fact_id"]
            ad = inj.get("axiom_delta", {})
            pd = inj.get("probe_deltas", {})
            target = inj["target_dimension"]

            ad_val = ad.get("axiom_delta", "?")
            if pd:
                target_d = pd.get(target, 0)
                others = [v for k, v in pd.items() if k != target]
                other_mean = round(sum(others) / len(others), 4) if others else 0
                sr = round(target_d / other_mean, 2) if other_mean > 0 else "N/A"
            else:
                sr = "N/A"

            print(f"    {fid} → {target}: AD={ad_val}, SR={sr}", file=sys.stderr)

    print(f"\nResults saved to {outfile}", file=sys.stderr)
    return results


def main():
    parser = argparse.ArgumentParser(description="Drift Experiment 1: Single-Fact Injection")
    parser.add_argument("--model", default="claude-sonnet-4-20250514", help="Anthropic model")
    parser.add_argument("--ollama", type=str, default=None, help="Ollama model name (e.g. phi4-mini:3.8b)")
    parser.add_argument("--max-tokens", type=int, default=150, help="Max output tokens per probe (default: 150)")
    parser.add_argument("--brief-type", default="brief", choices=["brief", "axioms", "atomic", "all"],
                        help="Brief format: brief (prose), axioms (compressed), atomic (flat prefs), all (run all 3)")
    parser.add_argument("--baseline-only", action="store_true", help="Run T0 only")
    parser.add_argument("--fact-index", type=int, help="Single fact injection (0-2)")
    args = parser.parse_args()
    run_experiment(args)


if __name__ == "__main__":
    main()
