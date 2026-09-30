"""Model backends for the consolidation builders, and the checkpointed call runner.

The builders (duplicate judge, trigger grouper, category builder) turn prompts into
parsed JSON. They never talk to a model directly: they hand a list of calls to a
`CallRunner`, which asks a `Backend` for each reply, checkpoints every accepted reply
to disk, and resumes from that file on a rerun.

Backends:
    FakeBackend       replies from a function of the prompt. Tests use it; it never bills.
    ApiBackend        the Anthropic API. Priced BEFORE any client exists: the rates come
                      from distillation/spend.py (one dated table the operator confirms), the
                      run is refused unless a spend ceiling covers the estimate, and every
                      call is checked against the ceiling before it is sent and recorded
                      after. No other price table is used.
    ClaudeCliBackend  `claude -p` on the local subscription. The child's environment has
                      ANTHROPIC_API_KEY and ANTHROPIC_AUTH_TOKEN removed (a bare `claude -p`
                      inherits the key and bills API credits), BASELAYER_SPEC_INJECT=0, hooks
                      and auto memory off, --safe-mode (drops the user-scope CLAUDE.md), an
                      empty strict MCP config, no tools, no session persistence, and a cwd
                      outside every project tree. A context probe of the actual child must
                      come back clean before any builder call is made.

Limits: a usage or rate limit is never recorded as a result. The runner backs off on a
schedule shared by all workers and, if the limit persists, stops cleanly with the
checkpoint intact (`UsageLimitStop`); a rerun resumes where it stopped.
"""
from __future__ import annotations

import hashlib
import json
import os
import re
import shutil
import subprocess
import threading
import time
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass, field
from pathlib import Path
from typing import Callable

LIMIT_RE = re.compile(r"usage limit|rate limit|rate_limit|limit reached|too many requests|\b429\b|overloaded|"
                      r"\b529\b|quota|hit your limit|limit will reset|resets at", re.I)
DEFAULT_BACKOFF_S = (60, 120, 240, 480, 900)
SPEC_INJECTION_CANARY = "BACKGROUND ON THE PERSON YOU ARE WORKING WITH"


@dataclass
class Reply:
    text: str | None
    model: str | None = None
    wall_s: float | None = None
    error: str | None = None
    limit: bool = False
    tokens_in: int | None = None
    tokens_out: int | None = None
    cost_usd: float | None = None
    raw: dict = field(default_factory=dict)


class UsageLimitStop(Exception):
    """A usage or rate limit persisted through the whole backoff schedule. The checkpoint
    holds every reply accepted so far; rerun the same command to resume."""


def sha(s: str) -> str:
    return hashlib.sha256(s.encode("utf-8")).hexdigest()


# ---------------------------------------------------------------- backends
class Backend:
    name = "abstract"
    bills_api = False
    model = None

    def prepare(self, calls: list[dict], label: str = "") -> dict:
        """Called once with every planned call ({"prompt_chars", "max_tokens"}) before the
        first model call. Returns the price estimate; may refuse to run."""
        return {"backend": self.name, "calls": len(calls), "usd": 0.0, "billing": "none"}

    def complete(self, prompt: str, max_tokens: int = 16000) -> Reply:  # pragma: no cover - interface
        raise NotImplementedError

    def provenance(self) -> dict:
        return {"backend": self.name, "model": self.model, "bills_api": self.bills_api}


class FakeBackend(Backend):
    """Scripted replies. `fn(prompt) -> str | Reply`. Records every prompt it was sent."""
    name = "fake"

    def __init__(self, fn: Callable, model: str = "fake"):
        self.fn = fn
        self.model = model
        self.prompts: list[str] = []
        self.prepared: list[dict] = []
        self.lock = threading.Lock()

    def prepare(self, calls, label=""):
        self.prepared.append({"label": label, "calls": len(calls)})
        return super().prepare(calls, label)

    def complete(self, prompt, max_tokens=16000):
        with self.lock:
            self.prompts.append(prompt)
        r = self.fn(prompt)
        return r if isinstance(r, Reply) else Reply(text=r, model=self.model, wall_s=0.0)


class ApiBackend(Backend):
    """The Anthropic API, priced and capped through distillation/spend.py.

    prepare() resolves the rates (the operator confirms the dated table or gives rates),
    prints nothing itself but returns the estimate, and fixes the ceiling via
    spend.plan_ceiling (refused when there is none, or when the estimate exceeds it).
    The client is created at the first call, never in prepare(), so a refused or
    plan-only run never constructs one.
    complete() checks the ceiling against measured spend plus this call's worst case,
    sends, and records the billed usage.
    """
    name = "anthropic_api"
    bills_api = True
    DEFAULT_MODEL = "claude-opus-5"
    # output tokens per call assumed by the point estimate; the ceiling, not this, bounds a run
    DEFAULT_OUT_TOKENS = 6000

    def __init__(self, model: str = DEFAULT_MODEL, *, rates_confirmed: str | None = None,
                 rate_in: float | None = None, rate_out: float | None = None,
                 confirm_spend: float | None = None, out_tokens_each: int = DEFAULT_OUT_TOKENS,
                 effort: str | None = None, client_factory: Callable | None = None):
        self.model = model
        self.rates_confirmed = rates_confirmed
        self.rate_in, self.rate_out = rate_in, rate_out
        self.confirm_spend = confirm_spend
        self.out_tokens_each = out_tokens_each
        self.effort = effort
        self.client_factory = client_factory
        self.client = None
        self.guard = None
        self.estimates: list[dict] = []
        self.lock = threading.Lock()

    def prepare(self, calls, label=""):
        from baselayer.distillation import spend
        rates = spend.resolve_rates(self.model, self.rate_in, self.rate_out, self.rates_confirmed)
        point, worst = spend.estimate_calls([c["prompt_chars"] for c in calls], self.out_tokens_each, rates,
                                            max((c["max_tokens"] for c in calls), default=0))
        spent = self.guard.spent_usd if self.guard else 0.0
        ceiling = spend.plan_ceiling(spent + point, self.confirm_spend)
        est = {"backend": self.name, "label": label, "model": self.model, "calls": len(calls),
               "prompt_chars": sum(c["prompt_chars"] for c in calls), "usd": round(point, 4),
               "usd_worst": round(worst, 4), "ceiling_usd": ceiling, "spent_before_usd": round(spent, 4),
               "rates": {"in": rates["in"], "out": rates["out"], "source": rates["source"], "as_of": rates["as_of"]},
               "assumed_out_tokens_per_call": self.out_tokens_each, "billing": "API credits: real spend"}
        self.estimates.append(est)
        if self.guard is None:
            self.guard = spend.SpendGuard(rates, ceiling, label="consolidation builders")
        else:
            self.guard.ceiling_usd = float(ceiling)
        return est

    def _client(self):
        with self.lock:
            if self.client is None:
                if self.client_factory is not None:
                    self.client = self.client_factory()
                else:
                    import anthropic
                    self.client = anthropic.Anthropic()
        return self.client

    def complete(self, prompt, max_tokens=16000):
        if self.guard is None:
            raise RuntimeError("ApiBackend.complete before prepare(): a billed call must be priced first")
        with self.lock:
            self.guard.check(len(prompt), max_tokens)
        client = self._client()
        t = time.time()
        kw = {"model": self.model, "max_tokens": max_tokens, "messages": [{"role": "user", "content": prompt}]}
        if self.effort:
            kw["output_config"] = {"effort": self.effort}
        try:
            resp = client.messages.create(**kw)
        except Exception as e:  # noqa: BLE001 -- classified below, never swallowed as a result
            status = getattr(e, "status_code", None)
            msg = f"{type(e).__name__}: {str(e)[:300]}"
            is_limit = status in (429, 529) or type(e).__name__ in ("RateLimitError", "OverloadedError") \
                or bool(LIMIT_RE.search(msg))
            return Reply(text=None, error=msg, limit=is_limit, wall_s=round(time.time() - t, 1))
        u = resp.usage
        with self.lock:
            self.guard.record(u.input_tokens, u.output_tokens)
        from baselayer.distillation import spend
        cost = spend.cost_usd(self.guard.rates, u.input_tokens, u.output_tokens)
        # 5-generation replies put a thinking block first: join text blocks, never content[0]
        text = "".join(getattr(b, "text", "") or "" for b in resp.content if getattr(b, "type", None) == "text")
        err = None
        if resp.stop_reason == "refusal":
            err = "refusal"
        elif resp.stop_reason == "max_tokens":
            err = "max_tokens: reply truncated"
        return Reply(text=text or None, model=getattr(resp, "model", self.model), wall_s=round(time.time() - t, 1),
                     error=err, tokens_in=u.input_tokens, tokens_out=u.output_tokens, cost_usd=cost,
                     raw={"stop_reason": resp.stop_reason})

    def provenance(self):
        return {"backend": self.name, "model": self.model, "bills_api": True,
                "billing": "API credits, priced from distillation/spend.py and capped by a ceiling",
                "estimates": self.estimates, "spend": self.guard.summary() if self.guard else None,
                "blind_channel": "none known for a bare API call; no Claude Code context is loaded"}


CLI_SETTINGS = json.dumps({"autoMemoryEnabled": False, "disableAllHooks": True})


class ClaudeCliBackend(Backend):
    """`claude -p` on the subscription ($0). See the module docstring for the isolation."""
    name = "claude_cli"
    bills_api = False

    def __init__(self, model: str, cwd: Path, work_dir: Path, protected: list[Path], timeout: int = 900,
                 binary: str | None = None):
        from baselayer.verification.raters import check_rater_cwd
        check_rater_cwd(cwd, protected)
        self.model = model
        self.cwd = Path(cwd).resolve()
        self.timeout = timeout
        self.binary = binary or shutil.which("claude")
        if not self.binary:
            raise FileNotFoundError("claude CLI not found on PATH")
        work_dir = Path(work_dir).resolve()  # the child runs in another cwd: every path it gets is absolute
        work_dir.mkdir(parents=True, exist_ok=True)
        self.mcp_config = work_dir / "empty_mcp.json"
        self.mcp_config.write_text(json.dumps({"mcpServers": {}}), encoding="utf-8")
        self.probe: dict | None = None
        self.version = None

    def command(self) -> list[str]:
        return [self.binary, "-p", "--strict-mcp-config", "--mcp-config", str(self.mcp_config), "--model", self.model,
                "--tools", "", "--output-format", "json", "--settings", CLI_SETTINGS,
                "--safe-mode", "--no-session-persistence", "--system-prompt-snapshot", "off"]

    def prepare(self, calls, label=""):
        from baselayer.verification.pricing import CHARS_PER_TOKEN
        if not (self.probe and self.probe.get("clean")):
            raise RuntimeError("claude -p backend: no clean context probe of the child; run probe() first")
        return {"backend": self.name, "label": label, "model": self.model, "calls": len(calls),
                "prompt_tokens_approx": int(sum(c["prompt_chars"] for c in calls) / CHARS_PER_TOKEN),
                "usd": 0.0, "billing": "subscription: bills nothing (API credentials removed from the child env)"}

    def complete(self, prompt, max_tokens=16000):
        """max_tokens is not passed to the CLI, which has no such flag."""
        from baselayer.verification.raters import child_env
        t = time.time()
        try:
            r = subprocess.run(self.command(), input=prompt, capture_output=True, text=True, encoding="utf-8",
                               env=child_env(), cwd=self.cwd, timeout=self.timeout)
        except subprocess.TimeoutExpired:
            return Reply(text=None, error=f"timeout after {self.timeout}s", wall_s=round(time.time() - t, 1))
        wall = round(time.time() - t, 1)
        try:
            d = json.loads(r.stdout)
        except Exception:  # noqa: BLE001
            msg = ((r.stdout or "")[-300:] + " " + (r.stderr or "")[-300:]).strip() or f"exit {r.returncode}"
            return Reply(text=None, error=msg, limit=bool(LIMIT_RE.search(msg)), wall_s=wall)
        models = sorted((d.get("modelUsage") or {}).keys())
        if d.get("is_error") or d.get("result") is None:
            msg = str(d.get("result") or d.get("subtype") or "error")[:300]
            return Reply(text=None, error=msg, limit=bool(LIMIT_RE.search(msg + " " + (r.stderr or ""))),
                         model=",".join(models) or None, wall_s=wall)
        u = d.get("usage") or {}
        return Reply(text=d.get("result"), model=",".join(models) or self.model, wall_s=wall,
                     tokens_in=u.get("input_tokens"), tokens_out=u.get("output_tokens"),
                     cost_usd=d.get("total_cost_usd"), raw={"models": models, "session_id": d.get("session_id")})

    def run_probe(self, canaries: list[str], out_path: Path) -> dict:
        """Ask the actual child what is in its context; store the answer beside the results.
        The spec-injection canary is always checked in addition to the caller's list."""
        from baselayer.verification.raters import run_probe
        cans = list(dict.fromkeys([SPEC_INJECTION_CANARY, *canaries]))
        res = run_probe(self, cans, Path(out_path))
        try:
            v = subprocess.run([self.binary, "--version"], capture_output=True, text=True, timeout=60)
            self.version = (v.stdout or "").strip()
        except Exception:  # noqa: BLE001
            self.version = "unknown"
        res["cli_version"] = self.version
        res["command"] = self.command()
        res["cwd"] = str(self.cwd)
        res["child_env"] = {"ANTHROPIC_API_KEY_present": False, "ANTHROPIC_AUTH_TOKEN_present": False,
                            "BASELAYER_SPEC_INJECT": "0"}
        Path(out_path).write_text(json.dumps(res, indent=1), encoding="utf-8")
        self.probe = {k: v for k, v in res.items() if k != "answer"} | {"stored": str(out_path)}
        return res

    def provenance(self):
        return {"backend": self.name, "model_alias": self.model, "bills_api": False, "cwd": str(self.cwd),
                "cli_version": self.version, "command": self.command(),
                "billing": "subscription (ANTHROPIC_API_KEY and ANTHROPIC_AUTH_TOKEN removed from the child env)",
                "spec_injection": "BASELAYER_SPEC_INJECT=0 and --settings disableAllHooks",
                "user_scope_instructions": "--safe-mode",
                "probe": self.probe or "not_run"}


# ---------------------------------------------------------------- checkpoint
class CallStore:
    """Append-only JSONL of accepted replies, keyed by the caller's key. A reply is stored
    only after it parsed; errors and limits are logged to a separate file and never
    stored as results. Resuming with a changed prompt under the same key is refused."""

    def __init__(self, path: Path):
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.err_path = self.path.with_name(self.path.stem + ".errors.jsonl")
        self.done: dict[str, dict] = {}
        if self.path.exists():
            raw = self.path.read_bytes()
            for line in raw.decode("utf-8").splitlines():
                try:
                    rec = json.loads(line)
                except Exception:  # noqa: BLE001 -- a torn last line from a crash
                    continue
                self.done[rec["key"]] = rec
            if raw and not raw.endswith(b"\n"):
                with self.path.open("ab") as f:
                    f.write(b"\n")
        self.lock = threading.Lock()

    def get(self, key: str, prompt: str) -> dict | None:
        rec = self.done.get(key)
        if rec is not None and rec["prompt_sha"] != sha(prompt):
            raise RuntimeError(f"checkpoint mismatch at {key}: the prompt changed; refusing to resume "
                               f"({self.path})")
        return rec

    def put(self, key: str, prompt: str, reply: Reply, meta: dict) -> dict:
        rec = {"key": key, "prompt_sha": sha(prompt), "ts": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
               "text": reply.text, "model": reply.model, "wall_s": reply.wall_s, "tokens_in": reply.tokens_in,
               "tokens_out": reply.tokens_out, "cost_usd": reply.cost_usd, **meta}
        with self.lock:
            with self.path.open("a", encoding="utf-8") as f:
                f.write(json.dumps(rec, ensure_ascii=False) + "\n")
            self.done[key] = rec
        return rec

    def log_error(self, key: str, reply: Reply, meta: dict) -> None:
        rec = {"key": key, "ts": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()), "error": reply.error,
               "limit": reply.limit, "model": reply.model, "text_head": (reply.text or "")[:300], **meta}
        with self.lock:
            with self.err_path.open("a", encoding="utf-8") as f:
                f.write(json.dumps(rec, ensure_ascii=False) + "\n")


# ---------------------------------------------------------------- runner
class CallRunner:
    """Runs a list of calls through a backend, with checkpoint, shared limit backoff,
    and a bounded retry on errors and unparseable replies.

    call = {"key", "prompt", "max_tokens"[, "parse"]}; parse(text) -> parsed object, or None
    when the reply is unusable (a call's own "parse" overrides the run's). Returns {key: {"parsed", "record"}} for every call that
    succeeded; failed keys are listed in `self.failed`."""

    def __init__(self, backend: Backend, store: CallStore, *, workers: int = 4, retries: int = 2,
                 backoff_s=DEFAULT_BACKOFF_S, sleep: Callable = time.sleep, log: Callable = print):
        self.backend, self.store = backend, store
        self.workers, self.retries = max(1, workers), retries
        self.backoff_s = tuple(backoff_s)
        self.sleep, self.log = sleep, log
        self.state = {"pause_until": 0.0, "stop": None, "limit_tries": 0, "limit_events": []}
        self.slock = threading.Lock()
        self.new_calls = 0
        self.replayed = 0
        self.failed: list[dict] = []
        self.models: dict[str, int] = {}
        # False when the caller priced the whole run up front with backend.prepare()
        self.auto_prepare = True

    def _limit(self, msg: str):
        with self.slock:
            self.state["limit_events"].append({"ts": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
                                               "msg": msg[:200]})
            n = self.state["limit_tries"]
            if n >= len(self.backoff_s):
                self.state["stop"] = f"usage/rate limit persisted after {sum(self.backoff_s)} s of backoff: {msg[:200]}"
                raise UsageLimitStop(self.state["stop"])
            wait = self.backoff_s[n]
            self.state["limit_tries"] = n + 1
            self.state["pause_until"] = max(self.state["pause_until"], time.time() + wait)
        self.log(f"LIMIT: pausing {wait} s: {msg[:120]}")

    def _wait(self):
        if self.state["stop"]:
            raise UsageLimitStop(self.state["stop"])
        w = self.state["pause_until"] - time.time()
        if w > 0:
            self.sleep(w)
        if self.state["stop"]:
            raise UsageLimitStop(self.state["stop"])

    def _one(self, call: dict, parse: Callable, meta: dict):
        key, prompt = call["key"], call["prompt"]
        parse = call.get("parse") or parse
        rec = self.store.get(key, prompt)
        if rec is not None:
            parsed = parse(rec["text"])
            if parsed is not None:
                with self.slock:
                    self.replayed += 1
                return key, {"parsed": parsed, "record": rec}
        attempts = 0
        while True:
            self._wait()
            r = self.backend.complete(prompt, call["max_tokens"])
            if r.limit:
                self.store.log_error(key, r, meta)
                self._limit(r.error or "limit")
                continue
            with self.slock:
                self.new_calls += 1
                if r.model:
                    self.models[r.model] = self.models.get(r.model, 0) + 1
                self.state["limit_tries"] = 0
            parsed = parse(r.text) if (r.text and not r.error) else None
            if parsed is not None:
                rec = self.store.put(key, prompt, r, meta | {"attempt": attempts + 1})
                return key, {"parsed": parsed, "record": rec}
            self.store.log_error(key, r, meta | {"attempt": attempts + 1,
                                                 "reason": r.error or "reply did not parse"})
            attempts += 1
            if attempts > self.retries:
                with self.slock:
                    self.failed.append({"key": key, "attempts": attempts, "last_error": r.error or "unparseable"})
                return key, None

    def run(self, calls: list[dict], parse: Callable | None = None, meta: dict | None = None) -> dict:
        meta = dict(meta or {})
        out = {}
        pending = [c for c in calls if not self._cached_ok(c, parse)]
        if pending and self.auto_prepare:
            self.backend.prepare([{"prompt_chars": len(c["prompt"]), "max_tokens": c["max_tokens"]} for c in pending],
                                 meta.get("builder", ""))
        with ThreadPoolExecutor(self.workers) as ex:
            futs = [ex.submit(self._one, c, parse, meta) for c in calls]
            err = None
            for f in futs:
                try:
                    k, v = f.result()
                except UsageLimitStop as e:
                    err = e
                    continue
                if v is not None:
                    out[k] = v
            if err is not None:
                raise err
        return out

    def _cached_ok(self, call, parse) -> bool:
        parse = call.get("parse") or parse
        rec = self.store.get(call["key"], call["prompt"])
        return rec is not None and parse(rec["text"]) is not None

    def summary(self) -> dict:
        return {"new_calls": self.new_calls, "replayed": self.replayed, "failed": list(self.failed),
                "models": dict(self.models), "limit_events": list(self.state["limit_events"])}


def parse_json(text: str | None):
    """The JSON object or list in a reply, fences and prose tolerated."""
    if not text:
        return None
    s = text.strip()
    if s.startswith("```"):
        s = s.split("\n", 1)[1] if "\n" in s else s
        s = s.rsplit("```", 1)[0]
    try:
        return json.loads(s)
    except Exception:  # noqa: BLE001 -- prose around the JSON; locate it below
        pass
    # the outermost structure is whichever bracket opens first: a one-item list must not
    # be read as its single object
    pairs = sorted((("{", "}"), ("[", "]")), key=lambda p: (s.find(p[0]) if s.find(p[0]) >= 0 else len(s)))
    for opener, closer in pairs:
        i, j = s.find(opener), s.rfind(closer)
        if i != -1 and j > i:
            try:
                return json.loads(s[i:j + 1])
            except Exception:  # noqa: BLE001
                pass
    return None


def env_has_api_key() -> bool:
    """Presence only; the value is never read into output."""
    return bool(os.environ.get("ANTHROPIC_API_KEY"))
