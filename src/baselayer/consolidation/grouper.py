"""Builder: the trigger grouper. Active_When conditions to a grouping file, by a model.

Implements `triggers.TriggerGrouper`. Two model steps, each checked mechanically, so a
model can propose but never write text into the output:

  1. SPLIT. Each non-always-on claim's condition is split into situation clauses, in
     batches. The model sees only the conditions, shuffled by `seed`, under neutral
     ids. A proposed clause is kept only as the SLICE of the authored condition it
     locates (exact, then case-insensitive, then whitespace-folded), so every stored
     clause is an exact substring by construction. The split is accepted only if the
     clauses leave no content-bearing span uncovered, by the same `checks.uncovered`
     the checks stage runs (K08). A split that fails either test falls back to the
     whole condition (`*`), which always passes, and the fallback is recorded.
     A condition returned as one clause is recorded as `*`.
     Split rule (grouper/2): split only between situations that can each occur on their
     own; never inside a list of objects, verbs or qualifiers that completes one
     situation ("giving water, feed or shade to a seedling" is one situation, not
     three). The prompt says so, and a mechanical guard backs it: every piece must be a
     standalone situation by `standalone()` (three or more words, or two words one of
     which is a verb form ending in -ing or -ed). A split with any piece that fails is
     kept whole, and the model's proposal is recorded beside the reason.
  2. GROUP. Every clause (whole conditions included) is listed once under a neutral id,
     shuffled by `seed`. The model groups the lines that name the same situation and
     picks, for each group, the member line whose wording names it. The reply is ids
     only, so a trigger's wording is a member's clause verbatim by construction. A line
     the reply leaves out becomes its own trigger, a repeated line keeps its first
     placement, and a wording that is not a member falls back to the first member; a
     wording whose text sits, as whole words, strictly inside another member's line is
     narrower than that member, so the wording moves to the longest such member. Each
     repair is recorded. Many-to-many follows from step 1: a claim whose condition was
     split has one edge per clause.

Always-on claims are left out. The output is the grouping-file shape the triggers stage
reads, so every existing trigger check (K03 to K08) runs on it unchanged.
"""
from __future__ import annotations

import random
import re

from .backends import CallRunner, parse_json
from .checks import uncovered
from .triggers import WHOLE

TEMPLATE = "grouper/3 (grouper/2 with a neutral split-rule example, design decision 2026-10-17)"
MAX_TOKENS = 32000

SPLIT_HEAD = """Below are {n} conditions. Each one says when a piece of advice about one person applies. Do not use any tool; answer directly from the text.

For each condition, list the distinct situations it names, as clauses.

Rules:
- Copy each clause EXACTLY from its condition: one contiguous run of the condition's characters, with the same spelling, capitalisation and punctuation. Do not rephrase, abbreviate, reorder, or join pieces that are not next to each other.
- Split only between situations that can each occur on their own, each of which could stand as a complete condition by itself (for example "When drafting emails or reviewing contracts" names two). A condition that names one situation is returned as one clause, the whole condition.
- Never split inside a list of objects, verbs or qualifiers that completes one situation. The items of such a list share one head ("giving", "reviewing any", "mentions of") and none of them is a situation without it. "Before giving water, feed or shade to a seedling" is ONE situation: return it whole, never "Before giving water" / "feed" / "shade to a seedling". "When reviewing any email, report, message or proposal" is ONE situation: return it whole.
- Every clause you return must read as a situation on its own. A clause that is only a noun or a list item ("time", "report", "the budget") means the split is wrong: return the condition whole.
- Together, a condition's clauses must cover every word of it that carries meaning. Connecting words such as "and", "or", "when", "any" may be left out.

Return STRICT JSON only, one key per condition id:
{{"S001": ["clause", "clause"], "S002": ["whole condition"], ...}}

Conditions:
{lines}
"""

GROUP_HEAD = """Below are {n} numbered lines. Each describes a situation in which some advice about one person applies. Do not use any tool; answer directly from the text.

Group the lines that name the SAME situation: a message or moment that matches one line of a group would match the others. Lines that share only a topic or some words, but describe different situations, stay in different groups. Every line goes in exactly one group; a group may hold a single line. For each group, choose the one member line whose wording best names the situation for the whole group.

Return STRICT JSON only:
{{"groups": [{{"members": ["K001", "K017"], "wording": "K017"}}, ...]}}

Lines:
{lines}
"""


# ---------------------------------------------------------------- clause location
def locate(cond: str, clause: str) -> str | None:
    """The slice of `cond` that `clause` names, or None. Exact first; then a case-folded
    match; then a whitespace-folded one. Surrounding quotes and trailing punctuation the
    model may add are stripped first. The return value is always cond[i:j]."""
    if not isinstance(clause, str):
        return None
    cl = clause.strip().strip("\"'`").strip()
    cl = cl.rstrip(",;:").strip()
    if not cl:
        return None
    i = cond.find(cl)
    if i >= 0:
        return cond[i:i + len(cl)]
    i = cond.lower().find(cl.lower())
    if i >= 0:
        return cond[i:i + len(cl)]
    words = cl.split()
    pat = r"\s+".join(re.escape(w) for w in words)
    m = re.search(pat, cond, flags=re.I)
    if m:
        return cond[m.start():m.end()]
    return None


# ---------------------------------------------------------------- the standalone guard
MIN_WORDS = 3
NOT_VERB_FORMS = {"thing", "something", "anything", "everything", "nothing", "during", "morning", "evening"}
NOT_STANDALONE = "a piece is not a standalone situation"


def _words(text: str) -> list[str]:
    return re.findall(r"[A-Za-z0-9][A-Za-z0-9'\-]*", text)


def _verb_form(w: str) -> bool:
    w = w.lower()
    return len(w) > 4 and w not in NOT_VERB_FORMS and (w.endswith("ing") or w.endswith("ed"))


def standalone(piece: str) -> bool:
    """Whether a split piece can name a situation by itself: MIN_WORDS (3) or more words,
    or exactly two words one of which is a verb form ending in -ing or -ed ("pruning
    hedges", "When watering"). One word never passes.

    Why these numbers: on the claims this was calibrated on, every one-word piece the
    model produced was a list item cut from a shared head, and the two-word pieces split
    by kind: a verb with its object is a situation ("repotting seedlings"), a bare noun
    phrase is the object of a head that stayed in another piece ("the budget"). The
    -ing / -ed test is the cheapest signal that a piece carries its own verb. It is a
    backstop for the prompt, not a parser: a three-word list item ("an unclear term")
    still passes, and a noun ending in -ing ("seedling trays") counts as a verb form."""
    w = _words(piece)
    if len(w) >= MIN_WORDS:
        return True
    return len(w) == 2 and any(_verb_form(x) for x in w)


def accept_split(cond: str, proposed) -> tuple[list[str] | None, str | None]:
    """(clauses or ["*"], fallback reason). Clauses are slices of the stripped condition."""
    c = cond.strip()
    if not isinstance(proposed, list) or not proposed:
        return [WHOLE], "no clauses returned"
    got = []
    for p in proposed:
        s = locate(c, p)
        if s is None:
            return [WHOLE], "a clause is not a substring of the condition"
        s = s.strip().rstrip(",;:").strip()
        if s and s not in got:
            got.append(s)
    # a clause contained in another clause of the same condition adds nothing
    got = [s for s in got if not any(s != o and s in o for o in got)]
    if len(got) <= 1:
        return [WHOLE], None if got else "no clauses returned"
    if uncovered(c, got):
        return [WHOLE], "clauses leave a content-bearing span uncovered"
    if not all(standalone(s) for s in got):
        return [WHOLE], NOT_STANDALONE
    return got, None


def _fold(text: str) -> str:
    return re.sub(r"\s+", " ", text.strip().lower()).rstrip(".,;: ")


def narrower(wording: str, member: str) -> bool:
    """True when the wording sits strictly inside the member's line as whole words, case
    and space folded: the trigger line would then name less than that member does. This
    is the only form of "narrower" a mechanical rule can decide. A wording narrower in
    meaning but not in text needs a model judge, which is not built."""
    w, m = _fold(wording), _fold(member)
    return bool(w) and w != m and re.search(r"(?<![a-z0-9])" + re.escape(w) + r"(?![a-z0-9])", m) is not None


def _slug(text: str, used: set) -> str:
    words = re.findall(r"[a-z0-9]+", text.lower())[:5] or ["trigger"]
    base = "_".join(words)
    k, n = base, 2
    while k in used:
        k, n = f"{base}_{n}", n + 1
    used.add(k)
    return k


# ---------------------------------------------------------------- the grouper
class ModelTriggerGrouper:
    """triggers.TriggerGrouper over a backend."""

    def __init__(self, runner: CallRunner, *, seed: int = 20260930, split_batch: int = 20, key_prefix: str = ""):
        self.runner, self.seed, self.split_batch, self.key_prefix = runner, seed, split_batch, key_prefix
        self.report: dict = {}

    def _key(self, step: str, n) -> str:
        b = self.runner.backend
        return f"{self.key_prefix}group|{TEMPLATE}|{b.name}|{b.model}|seed{self.seed}|{step}{n}"

    # -------- step 1
    def split_calls(self, claims: list[dict]) -> list[dict]:
        order = list(claims)
        random.Random(self.seed).shuffle(order)
        calls = []
        for n in range(0, len(order), self.split_batch):
            chunk = order[n:n + self.split_batch]
            sid = {f"S{i:03d}": c["id"] for i, c in enumerate(chunk, 1)}
            lines = "\n".join(f"{s}: {next(c for c in chunk if c['id'] == cid)['active_when'].strip()}"
                              for s, cid in sid.items())
            prompt = SPLIT_HEAD.format(n=len(chunk), lines=lines)

            def parse(text, _ids=tuple(sid)):
                p = parse_json(text)
                if not isinstance(p, dict) or not all(k in p for k in _ids):
                    return None
                return p
            calls.append({"key": self._key("split", n // self.split_batch + 1), "prompt": prompt,
                          "max_tokens": MAX_TOKENS, "parse": parse, "sid": sid})
        return calls

    def group_prompt(self, lines: list[tuple[str, str]]) -> tuple[str, dict]:
        """lines: [(line id in the output, clause text)]; returns (prompt, neutral id -> line id)."""
        order = list(lines)
        random.Random(self.seed + 1).shuffle(order)
        width = max(3, len(str(len(order))))
        kid = {f"K{i:0{width}d}": lid for i, (lid, _) in enumerate(order, 1)}
        text = dict(lines)
        body = "\n".join(f"{k}: {text[lid]}" for k, lid in kid.items())
        return GROUP_HEAD.format(n=len(order), lines=body), kid

    def group_lines(self, lines: list[tuple[str, str]]) -> tuple[list, dict]:
        """Step 2 alone, on any line set: lines are [(line id, text)]. Returns
        ([(member line ids, wording line id)], repairs); every line is in exactly one group."""
        prompt, kid = self.group_prompt(lines)
        n_lines = len(kid)
        text = dict(lines)

        def gparse(text):
            p = parse_json(text)
            if not isinstance(p, dict) or not isinstance(p.get("groups"), list):
                return None
            placed = {m for g in p["groups"] if isinstance(g, dict) for m in (g.get("members") or [])
                      if isinstance(m, str) and m in kid}
            return p if len(placed) >= n_lines - max(1, n_lines // 10) else None
        gres = self.runner.run([{"key": self._key("group", 1), "prompt": prompt, "max_tokens": MAX_TOKENS,
                                 "parse": gparse}], meta={"builder": "group", "step": "group"})
        got = gres.get(self._key("group", 1))
        if got is None:
            raise RuntimeError("trigger grouper: the group call failed after retries; no grouping written")
        seen, groups, repairs = set(), [], {"missing_lines": [], "repeated_lines": [], "unknown_ids": [],
                                           "wording_not_member": 0, "wording_narrower_than_member": []}
        for g in got["parsed"]["groups"]:
            if not isinstance(g, dict):
                continue
            mem = []
            for m in g.get("members") or []:
                if m not in kid:
                    repairs["unknown_ids"].append(m)
                elif m in seen:
                    repairs["repeated_lines"].append(kid[m])
                else:
                    seen.add(m)
                    mem.append(m)
            if not mem:
                continue
            w = g.get("wording")
            if w not in mem:
                repairs["wording_not_member"] += 1
                w = mem[0]
            wider = [m for m in mem if narrower(text[kid[w]], text[kid[m]])]
            if wider:
                to = max(wider, key=lambda m: (len(text[kid[m]]), -mem.index(m)))
                repairs["wording_narrower_than_member"].append({"from": kid[w], "to": kid[to]})
                w = to
            groups.append(([kid[m] for m in mem], kid[w]))
        for k in kid:
            if k not in seen:
                repairs["missing_lines"].append(kid[k])
                groups.append(([kid[k]], kid[k]))
        return groups, repairs

    def plan(self, claims: list[dict], always_on: list[str]) -> list[dict]:
        """Every call this grouper will make, sized before any is made. The group call's
        prompt depends on the splits, so it is sized at its upper bound: every condition
        listed whole plus a bound on added clauses (the conditions' total length again)."""
        ao = set(always_on)
        cl = [c for c in claims if c["id"] not in ao]
        calls = [{"prompt_chars": len(c["prompt"]), "max_tokens": c["max_tokens"]} for c in self.split_calls(cl)]
        bound = len(GROUP_HEAD) + 2 * sum(len(c["active_when"]) + 8 for c in cl)
        calls.append({"prompt_chars": bound, "max_tokens": MAX_TOKENS})
        return calls

    def group(self, claims: list[dict], always_on: list[str]) -> dict:
        ao = set(always_on)
        cl = [c for c in claims if c["id"] not in ao]
        cmap = {c["id"]: c for c in cl}
        pos = {c["id"]: n for n, c in enumerate(claims)}
        # ---- step 1: split
        scalls = self.split_calls(cl)
        sres = self.runner.run([{k: c[k] for k in ("key", "prompt", "max_tokens", "parse")} for c in scalls],
                               meta={"builder": "group", "step": "split"})
        splits, fallbacks, proposed = {}, {}, {}
        for c in scalls:
            got = sres.get(c["key"])
            for s, cid in c["sid"].items():
                if got is None:
                    splits[cid], why = [WHOLE], "split call failed"
                else:
                    proposed[cid] = got["parsed"].get(s)
                    splits[cid], why = accept_split(cmap[cid]["active_when"], proposed[cid])
                if why:
                    fallbacks[cid] = why
        # ---- step 2: group
        lines, lmeta = [], {}
        for c in cl:
            cond = c["active_when"].strip()
            for n, clause in enumerate(splits[c["id"]]):
                lid = f"{c['id']}#{n}"
                lines.append((lid, cond if clause == WHOLE else clause))
                start = 0 if clause == WHOLE else cond.find(clause)
                lmeta[lid] = {"claim": c["id"], "clause": clause, "pos": (pos[c["id"]], start)}
        groups, repairs = self.group_lines(lines)
        # ---- assemble the grouping file, in a stable order
        used: set = set()
        out = []
        for mem, w in groups:
            lm = sorted((lmeta[m] for m in mem), key=lambda x: x["pos"])
            wl = lmeta[w]
            wtext = cmap[wl["claim"]]["active_when"].strip() if wl["clause"] == WHOLE else wl["clause"]
            out.append({"members": [{"claim": x["claim"], "clause": x["clause"]} for x in lm],
                        "wording_source": {"claim": wl["claim"], "clause": wl["clause"]},
                        "_pos": lm[0]["pos"], "_wording": wtext})
        out.sort(key=lambda t: t["_pos"])
        for t in out:
            t["key"] = _slug(t.pop("_wording"), used)
            t.pop("_pos")
        triggers = [{"key": t["key"], "wording_source": t["wording_source"], "members": t["members"]} for t in out]
        n_split = sum(1 for v in splits.values() if v != [WHOLE])
        self.report = {
            "splits": {cid: splits[cid] for cid in cmap}, "split_fallbacks": fallbacks,
            "split_proposed": {cid: proposed.get(cid) for cid in cmap}, "group_repairs": repairs,
            "stats": {"claims": len(cl), "always_on_excluded": len(ao & set(c["id"] for c in claims)),
                      "claims_split": n_split, "clauses": len(lines), "split_fallbacks": len(fallbacks),
                      "split_rejected_not_standalone": sum(1 for v in fallbacks.values() if v == NOT_STANDALONE),
                      "triggers": len(triggers), "edges": sum(len(t["members"]) for t in triggers),
                      "singleton_triggers": sum(1 for t in triggers if len({m["claim"] for m in t["members"]}) == 1)},
        }
        return {"method": f"model grouper ({TEMPLATE}); seed {self.seed}", "triggers": triggers}


def build(claims_doc: dict, always_on_doc: dict, runner: CallRunner, *, seed: int = 20260930,
          split_batch: int = 20, key_prefix: str = "") -> dict:
    g = ModelTriggerGrouper(runner, seed=seed, split_batch=split_batch, key_prefix=key_prefix)
    grouping = g.group(claims_doc["claims"], list(always_on_doc["claims"]))
    return {**grouping, "template": TEMPLATE, "params": {"seed": seed, "split_batch": split_batch},
            **g.report}
