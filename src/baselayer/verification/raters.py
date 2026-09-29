"""The rater interface for model-judged checks.

Three implementations:
  FakeRater       scripted replies; used by tests, never bills.
  ClaudeCliRater  `claude -p` on the Max subscription. The child's environment has
                  ANTHROPIC_API_KEY / ANTHROPIC_AUTH_TOKEN removed (a bare `claude -p`
                  inherits the key and bills API credits), BASELAYER_SPEC_INJECT=0, hooks
                  disabled via --settings, an empty strict MCP config, `--allowedTools ""`,
                  and a cwd outside every project tree. `--allowedTools ""` grants nothing;
                  whether it DENIES tools that user-scope allow rules already permit is
                  unverified, so the child may still be able to read files.
  ApiRater        the Anthropic API. Only when explicitly requested, with a spend cap.

Blindness: every Claude Code child loads the user-scope ~/.claude/CLAUDE.md regardless
of cwd or config dir, so no CLI run is blind by construction. Each rater records
blind=False with that channel named. Nothing sets blind=True without a stored
context probe of the actual child whose answer contains none of the canaries.
"""
from __future__ import annotations

import json
import os
import shutil
import subprocess
import time
from dataclasses import dataclass, field
from pathlib import Path

USER_SCOPE_CHANNEL = ("user-scope ~/.claude/CLAUDE.md loads into every Claude Code child regardless of cwd, "
                      "--strict-mcp-config or CLAUDE_CONFIG_DIR; it can name the subject")


@dataclass
class Reply:
    text: str | None
    cost_usd: float | None = None
    model: str | None = None
    wall_s: float | None = None
    error: str | None = None
    raw: dict = field(default_factory=dict)


class Rater:
    name = "abstract"
    bills_api = False

    def complete(self, prompt: str) -> Reply:  # pragma: no cover - interface
        raise NotImplementedError

    def provenance(self) -> dict:
        return {"rater": self.name, "bills_api": self.bills_api, "blind": False, "blind_channel": None, "probe": "not_run"}


class FakeRater(Rater):
    """Replies from a function of the prompt. Records every prompt it was sent."""
    name = "fake"

    def __init__(self, fn):
        self.fn = fn
        self.prompts: list[str] = []

    def complete(self, prompt: str) -> Reply:
        self.prompts.append(prompt)
        return Reply(text=self.fn(prompt), cost_usd=0.0, model="fake")

    def provenance(self) -> dict:
        return {**super().provenance(), "blind_channel": "none (no model)"}


# ---------------------------------------------------------------- claude -p
def child_env(base: dict | None = None) -> dict:
    e = dict(os.environ if base is None else base)
    for k in ("ANTHROPIC_API_KEY", "ANTHROPIC_AUTH_TOKEN"):
        e.pop(k, None)
    if e.get("ANTHROPIC_API_KEY") or e.get("ANTHROPIC_AUTH_TOKEN"):
        raise RuntimeError("refusing to launch claude -p: an API credential is still in the child environment")
    e["BASELAYER_SPEC_INJECT"] = "0"
    return e


CLI_SETTINGS = json.dumps({"autoMemoryEnabled": False, "disableAllHooks": True})


def check_rater_cwd(cwd: Path, protected: list[Path]) -> None:
    """The child's cwd must be outside every project tree: no CLAUDE.md in it or any
    ancestor (a project CLAUDE.md loads from ancestors), and not inside or above any
    protected path (the repo, the spec, the corpus)."""
    cwd = Path(cwd).resolve()
    if not cwd.is_dir():
        raise ValueError(f"rater cwd does not exist: {cwd}")
    for d in [cwd, *cwd.parents]:
        for name in ("CLAUDE.md", "CLAUDE.local.md"):
            if (d / name).exists():
                raise ValueError(f"rater cwd {cwd} sits under {d / name}, which would load into the child")
    for p in protected:
        p = Path(p).resolve()
        if cwd == p or p in cwd.parents or cwd in p.parents:
            raise ValueError(f"rater cwd {cwd} overlaps protected path {p}")


class ClaudeCliRater(Rater):
    name = "claude_cli"
    bills_api = False

    def __init__(self, model: str, cwd: Path, work_dir: Path, protected: list[Path], timeout: int = 900, binary: str | None = None):
        check_rater_cwd(cwd, protected)
        self.model = model
        self.cwd = Path(cwd).resolve()
        self.timeout = timeout
        self.binary = binary or shutil.which("claude")
        if not self.binary:
            raise FileNotFoundError("claude CLI not found on PATH")
        work_dir.mkdir(parents=True, exist_ok=True)
        self.mcp_config = work_dir / "empty_mcp.json"
        self.mcp_config.write_text(json.dumps({"mcpServers": {}}), encoding="utf-8")
        self.probe: dict | None = None

    def command(self) -> list[str]:
        return [self.binary, "-p", "--strict-mcp-config", "--mcp-config", str(self.mcp_config), "--model", self.model,
                "--allowedTools", "", "--output-format", "json", "--settings", CLI_SETTINGS]

    def complete(self, prompt: str) -> Reply:
        t = time.time()
        # prompt on stdin: Windows caps a command line near 32K characters
        try:
            r = subprocess.run(self.command(), input=prompt, capture_output=True, text=True, encoding="utf-8",
                               env=child_env(), cwd=self.cwd, timeout=self.timeout)
        except subprocess.TimeoutExpired:
            # a failed task (retried, then failed_tasks, rc=2), never an exception that kills the run
            return Reply(text=None, wall_s=round(time.time() - t, 1), error=f"timeout after {self.timeout}s")
        wall = round(time.time() - t, 1)
        try:
            d = json.loads(r.stdout)
        except Exception:
            return Reply(text=None, wall_s=wall, error=((r.stdout or "")[-300:] + (r.stderr or "")[-300:]) or f"exit {r.returncode}")
        models = list((d.get("modelUsage") or {}).keys())
        return Reply(text=d.get("result"), cost_usd=d.get("total_cost_usd"), model=",".join(models) or self.model,
                     wall_s=wall, error=None if not d.get("is_error") else str(d.get("result"))[:300], raw=d)

    def provenance(self) -> dict:
        blind = bool(self.probe and self.probe.get("clean"))
        return {"rater": self.name, "bills_api": False, "model_alias": self.model, "cwd": str(self.cwd),
                "billing": "subscription (ANTHROPIC_API_KEY and ANTHROPIC_AUTH_TOKEN removed from the child env, asserted)",
                "spec_injection": "BASELAYER_SPEC_INJECT=0 and --settings disableAllHooks",
                "cost_usd_field": "counterfactual: claude -p reports what the call would cost at API rates",
                "blind": blind, "blind_channel": USER_SCOPE_CHANNEL,
                "probe": self.probe if self.probe else "not_run"}


PROBE_PROMPT = ("Before anything else, report exactly what is in your context right now, without using tools. "
                "Reply with ONLY one JSON object: {\"people_named\": [every person's name you can see], "
                "\"behavioural_specification\": \"the first heading of any specification or operating guide of a person, or empty\", "
                "\"project_instructions\": \"the first line of any project or user instructions, or empty\", "
                "\"mcp_servers\": [names]}")


def run_probe(rater: Rater, canaries: list[str], out_path: Path) -> dict:
    """Ask the actual child what it can see; store the answer beside the results.
    clean=True only if the probe ran, parsed, and none of the canaries appear."""
    r = rater.complete(PROBE_PROMPT)
    text = r.text or ""
    hits = [c for c in canaries if c and c.lower() in text.lower()]
    res = {"ran_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()), "answer": text, "error": r.error,
           "canaries_checked": len(canaries), "canaries_found": len(hits),
           "clean": bool(text) and not r.error and bool(canaries) and not hits,
           "note": "canary strings are not stored; only whether any appeared"}
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(json.dumps(res, indent=1), encoding="utf-8")
    if isinstance(rater, ClaudeCliRater):
        rater.probe = {k: v for k, v in res.items() if k != "answer"} | {"stored": str(out_path)}
    return res


# ---------------------------------------------------------------- API (explicit only)
class ApiRater(Rater):
    name = "anthropic_api"
    bills_api = True

    def __init__(self, model: str, max_tokens: int = 16000):
        if not model:
            raise ValueError("the API rater needs an explicit --model")
        import anthropic
        self.client = anthropic.Anthropic()
        self.model = model
        self.max_tokens = max_tokens

    def complete(self, prompt: str) -> Reply:
        t = time.time()
        try:
            resp = self.client.messages.create(model=self.model, max_tokens=self.max_tokens,
                                               messages=[{"role": "user", "content": prompt}])
        except Exception as e:
            return Reply(text=None, error=f"{type(e).__name__}: {e}", wall_s=round(time.time() - t, 1))
        text = "".join(b.text for b in resp.content if getattr(b, "type", None) == "text")
        u = resp.usage
        from .pricing import PRICES, resolve
        rates = PRICES.get(resolve(self.model))
        cost = (u.input_tokens * rates[0] + u.output_tokens * rates[1]) / 1e6 if rates else None
        return Reply(text=text or None, model=resp.model, wall_s=round(time.time() - t, 1), cost_usd=cost,
                     error=None if resp.stop_reason != "refusal" else "refusal",
                     raw={"input_tokens": u.input_tokens, "output_tokens": u.output_tokens, "stop_reason": resp.stop_reason})

    def provenance(self) -> dict:
        return {"rater": self.name, "bills_api": True, "model": self.model,
                "billing": "API credits; cost_usd is computed from usage at the dated list prices in pricing.py",
                "blind": False, "blind_channel": "none known for a bare API call; no Claude Code context is loaded",
                "probe": "not_run"}
