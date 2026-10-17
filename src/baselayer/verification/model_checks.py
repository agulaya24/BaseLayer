"""Model-judged checks: prompts, task builders, reply validation and interpretation.

Phase 1 (independent calls):
  support     one call per claim: per cited fact supports/partial/unrelated/contradicts;
              contested claims also get two named poles and a side per fact; document
              corpora (--referent) also get document/author/other per fact
  voice       batches of facts whose voice the conversation record could not settle:
              who originated the content, with the turn relied on
  fidelity    turn-contract mode only: each cited fact read against its cited turn in
              context, labelled under the fixed fidelity standard (definitions.py)
  cross       candidate claim pairs plus a random recall sample of non-candidates:
              contradicts / tensions / duplicate / compatible
Phase 2 (depends on phase 1):
  adjudicate  each apparent contradiction (a fact judged `contradicts`, a contested
              claim's side-2 evidence, a cross-claim `contradicts`) as a pair of facts,
              read in its source context

Prompts are adapted from an earlier claim back-check prototype. Every reply is
validated against the exact id set the task sent; a mismatch is a failed task, never
a partial result.
"""
from __future__ import annotations

import json
import random
import re

from .definitions import NOT_HIS_MIN_LOCATED, NOT_HIS_RATIO, WEAK_SUPPORT_RATIO
from .deterministic import finding

VOICE_BATCH = 15
CROSS_BATCH = 30
ADJ_BATCH = 5

SUPPORT_PROMPT = """You are auditing one claim from a behavioural specification of a person against the evidence it cites.
Each cited fact is a short statement machine-extracted from source material. Judge each fact ONLY against the claim as written.

Per fact, `support`:
- supports: the fact directly evidences the claim as written
- partial: evidences part of the claim, or a weaker/narrower version of it
- unrelated: does not bear on the claim
- contradicts: evidences the opposite of the claim
{contested_block}{referent_block}
Also name `strongest` (the one fact id that best supports the claim, or null) and `weakest` (the one cited fact id that least belongs, or null).

CLAIM {qid} ({name}){contested_tag}
Statement: {statement}
Active when: {active_when}

CITED FACTS ({n}):
{facts}

Reply with ONLY one JSON object, no prose, no code fence:
{schema}
Every one of the {n} fact ids above must appear exactly once in "facts", and no other id."""

CONTESTED_BLOCK = """
This claim is flagged CONTESTED: its record is said to divide. First state the two poles:
- side_1: the thesis as the claim states it (one clause)
- side_2: the counter-pole the record carries (one clause). If the claim text names no counter-pole, infer the most plausible one from the facts; if none is evident write "none evident".
Then per fact give `side`: "1", "2" or "neither". A fact can be on side 2 and still be labelled contradicts or partial for support.
"""
REFERENT_BLOCK = """
Per fact also give `referent`:
- document: describes what the document itself defines, requires, or does (a property of the artefact)
- author: evidences the disposition, judgement, or working stance of the person who wrote it, beyond restating a mechanism
- other: neither (another party, general background)
"""

VOICE_PROMPT = """Each item below is a statement that an extraction model attributed to the subject (the "user") of a conversation, plus excerpts from the conversation it was extracted from (turn number and role; user turns can contain text the user pasted).

For each item decide who ORIGINATED the content of the statement:
- own_words: the subject said it in their own words (typed or dictated)
- fair_description: the statement fairly describes what the subject themselves did or said, and one of their own turns shows it
- own_document: it comes from a document the subject pasted that they evidently wrote themselves
- pasted: it comes from text the subject pasted that someone else wrote (including AI text pasted back)
- assistant: the content originates in the assistant's reply (its advice, maxims, characterisation of the subject), even if the subject then agreed
- unknown: the excerpts do not settle it

Judge from the excerpts only. If the subject asked a question and only the assistant supplied the substance, that is assistant.

{items}

Reply with ONLY one JSON object, no prose, no code fence:
{{"items": [{{"id": "V###", "voice": "own_words|fair_description|own_document|pasted|assistant|unknown", "turn": <turn number relied on or null>}}]}}
Every item id above must appear exactly once."""

FIDELITY_PROMPT = """Each item below is a fact that was machine-extracted about the subject of a conversation. It cites one turn the subject wrote or spoke, with a verbatim evidence span, and the turns around it for context. The quote is known to be the subject's words; the question is whether the FACT is a faithful reading of them.

Label each item:
- own_words: the fact's content is in the subject's own words in the cited turn, read with its context
- fair_description: the fact describes what the subject did or said, and their own turn shows it (the assistant's account of what they did does not count)
- overreach: their turn supports only a narrower or weaker statement than the fact makes
- misread: the fact misstates the turn (wrong polarity, a hypothetical recorded as fact, wrong subject, garbled)
- not_his: the content originates in context the subject did not write (assistant, pasted, another person)

{items}

Reply with ONLY one JSON object, no prose, no code fence:
{{"items": [{{"id": "D###", "label": "own_words|fair_description|overreach|misread|not_his", "reason": "<one clause>"}}]}}
Every item id above must appear exactly once."""

CROSS_PROMPT = """Below are claims from ONE behavioural specification of one person, then pairs of those claims.
For each pair decide how the two claims relate AS WRITTEN, including their "Active when" conditions:
- contradicts: they cannot both hold of the same person in the same situation
- tensions: they pull in opposite directions but can both hold, because a condition separates them (different situations, domains, time, or stated-vs-enacted)
- duplicate: they make substantially the same claim (one could be merged into the other with no loss)
- compatible: neither of the above
For contradicts and tensions give `condition`: the one condition that separates them, or that would have to be specified to reconcile them (one clause); otherwise null.
Do not judge whether either claim is true of the person.

CLAIMS:
{claims}

PAIRS:
{pairs}

Reply with ONLY one JSON object, no prose, no code fence:
{{"items": [{{"id": "Q###", "relation": "contradicts|tensions|duplicate|compatible", "condition": "..."}}]}}
Every pair id above must appear exactly once."""

ADJ_PROMPT = """You are adjudicating apparent contradictions between pairs of facts that were machine-extracted about one person. Each fact comes with the ORIGINAL source context it was extracted from.

Rules:
- Evidence counts only in the person's OWN words. Assistant turns and pasted text are context for interpreting what the person said; they are never evidence of what the person holds.
- Decide what the apparent contradiction really is:
  - real_contradiction: in the person's own words, the two genuinely conflict with no separating condition
  - context_split: both are true of the person under different conditions; name the condition
  - misattribution: at least one fact is not the person's (assistant words, advice or characterisation; pasted text by someone else); say which fact
  - extraction_error: at least one fact misstates its source (wrong polarity, hypothetical recorded as fact, garbled, wrong subject); say which
  - no_conflict: read in context, the two facts do not conflict
- Also say for each fact whether the person's own words in the context support it: yes / partly / no.

{items}

Reply with ONLY one JSON object, no prose, no code fence:
{{"items": [{{"id": "K###", "verdict": "real_contradiction|context_split|misattribution|extraction_error|no_conflict", "condition": "<separating condition or null>", "which_fact": "<fact id or null>", "own_words_support": {{"<fact id>": "yes|partly|no"}}, "reason": "<one clause>"}}]}}
Every item id above must appear exactly once."""


# ---------------------------------------------------------------- parsing and validation
def parse_json(s: str | None):
    if not s:
        return None
    s = re.sub(r"^```(?:json)?\s*|\s*```$", "", s.strip())
    try:
        return json.loads(s)
    except Exception:
        i, j = s.find("{"), s.rfind("}")
        if i >= 0 and j > i:
            try:
                return json.loads(s[i:j + 1])
            except Exception:
                return None
    return None


ENUMS = {
    "support": ("support", {"supports", "partial", "unrelated", "contradicts"}),
    "voice": ("voice", {"own_words", "fair_description", "own_document", "pasted", "assistant", "unknown"}),
    "fidelity": ("label", {"own_words", "fair_description", "overreach", "misread", "not_his"}),
    "cross": ("relation", {"contradicts", "tensions", "duplicate", "compatible"}),
    "adjudicate": ("verdict", {"real_contradiction", "context_split", "misattribution", "extraction_error", "no_conflict"}),
}


def validate(kind: str, obj, ids: list[str]) -> str | None:
    if not isinstance(obj, dict):
        return "unparseable"
    items = obj.get("facts" if kind == "support" else "items")
    if not isinstance(items, list):
        return "no item list"
    if not all(isinstance(x, dict) and isinstance(x.get("id"), str) for x in items):
        return "malformed item: every item must be an object with a string id"
    got = [x["id"] for x in items]
    if sorted(got) != sorted(ids):
        return (f"id_mismatch missing={sorted(set(ids) - set(got))[:5]} extra={sorted(set(got) - set(ids))[:5]} "
                f"dup={len(got) - len(set(got))}")
    field, allowed = ENUMS[kind]
    bad = [x["id"] for x in items if not isinstance(x.get(field), str) or x.get(field) not in allowed]
    if bad:
        return f"bad {field} value on {bad[:5]}"
    return None


# ---------------------------------------------------------------- task builders
def support_tasks(spec, profiles, referent: bool) -> list[dict]:
    tasks = []
    for cl in spec.claims:
        prof = profiles[cl.qid]
        live = [r for r in prof["facts"] if r["status"] == "live"]
        if not live:
            continue
        ids = [r["id"] for r in live]
        fields = ['"support": "supports|partial|unrelated|contradicts"']
        if cl.contested:
            fields.append('"side": "1|2|neither"')
        if referent:
            fields.append('"referent": "document|author|other"')
        schema = "{" + (' "side_1": "...", "side_2": "...",' if cl.contested else "") + \
            ' "facts": [{"id": "F-xxxxxxxx", ' + ", ".join(fields) + '}], "strongest": "F-xxxxxxxx", "weakest": "F-xxxxxxxx"}'
        prompt = SUPPORT_PROMPT.format(
            contested_block=CONTESTED_BLOCK if cl.contested else "", referent_block=REFERENT_BLOCK if referent else "",
            qid=cl.qid, name=cl.name, contested_tag=" [CONTESTED]" if cl.contested else "", statement=cl.statement,
            active_when=cl.active_when, n=len(ids), facts="\n".join(f"{r['id']}: {r['text']}" for r in live), schema=schema)
        tasks.append({"kind": "support", "key": "S_" + cl.qid.replace(":", "_"), "prompt": prompt, "ids": ids, "claim": cl.qid})
    return tasks


def voice_tasks(spec, profiles, corpus) -> list[dict]:
    items, seen = [], set()
    for q, prof in profiles.items():
        for r in prof["facts"]:
            if r["status"] != "live" or r.get("voice") != "unresolved_turn_level" or r["id"] in seen:
                continue
            seen.add(r["id"])
            ex = corpus.excerpts(r["text"], r["conversation_id"])
            if ex is None:
                continue
            items.append({"fid": r["id"], "text": r["text"], **ex})
    tasks = []
    for b in range(0, len(items), VOICE_BATCH):
        batch = items[b:b + VOICE_BATCH]
        vids, parts, mp = [], [], {}
        for k, it in enumerate(batch):
            vid = f"V{b + k:04d}"
            vids.append(vid)
            mp[vid] = {"fid": it["fid"], "conversation_id": it["conversation_id"],
                       "turns": {str(e["turn"]): e["message_id"] for e in it["excerpts"]}}
            exs = "\n".join(f"  [turn {e['turn']} {e['role']}] {e['text']}" for e in it["excerpts"]) or "  (no excerpts)"
            parts.append(f"ITEM {vid}\nStatement: {it['text']}\nConversation: {it['title']!r} ({it['source']}, {it['n_msgs']} messages)\nExcerpts:\n{exs}")
        tasks.append({"kind": "voice", "key": f"V_{b // VOICE_BATCH:03d}", "prompt": VOICE_PROMPT.format(items="\n\n".join(parts)),
                      "ids": vids, "map": mp})
    return tasks


def fidelity_tasks(spec, profiles, corpus) -> list[dict]:
    items, seen = [], set()
    for q, prof in profiles.items():
        for r in prof["facts"]:
            if r["status"] != "live" or r.get("voice_mode") != "turn_contract" or not r["turn_ids"] or r["id"] in seen:
                continue
            seen.add(r["id"])
            f = corpus.fact(r["id"])
            ctx = corpus.turn_context(r["turn_ids"][0])
            if ctx is None:
                continue
            items.append({"fid": r["id"], "text": r["text"], "span": f.evidence_span, "turn_id": r["turn_ids"][0], **ctx})
    tasks = []
    for b in range(0, len(items), VOICE_BATCH):
        batch = items[b:b + VOICE_BATCH]
        dids, parts, mp = [], [], {}
        for k, it in enumerate(batch):
            did = f"D{b + k:04d}"
            dids.append(did)
            mp[did] = {"fid": it["fid"], "turn_id": it["turn_id"], "context_turn_ids": it["turn_ids"],
                       "conversation_id": it["conversation_id"]}
            parts.append(f"ITEM {did}\nFact: {it['text']}\nCited turn: {it['turn_id']}\nEvidence span: {it['span']!r}\nContext:\n{it['render']}")
        tasks.append({"kind": "fidelity", "key": f"D_{b // VOICE_BATCH:03d}", "prompt": FIDELITY_PROMPT.format(items="\n\n".join(parts)),
                      "ids": dids, "map": mp})
    return tasks


def cross_tasks(spec, pairs, n_select: int, n_recall: int, seed: int = 20260924) -> list[dict]:
    rng = random.Random(seed)
    C = {c.qid: c for c in spec.claims}
    sel = pairs[:n_select]
    have = {(p["a"], p["b"]) for p in sel}
    # always judged, whatever the cut: pairs sharing two or more cited facts, and identical names
    extra = [p for p in pairs[n_select:] if p["shared_facts"] >= 2 or p.get("same_name")]
    sel = [dict(p, arm="selected") for p in sel + extra]
    have |= {(p["a"], p["b"]) for p in extra}
    rest = [p for p in pairs if (p["a"], p["b"]) not in have]
    rec = [dict(p, arm="recall_sample") for p in rng.sample(rest, min(n_recall, len(rest)))]
    allp = sel + rec
    rng.shuffle(allp)  # the rater cannot tell selected from recall pairs
    tasks = []
    for b in range(0, len(allp), CROSS_BATCH):
        batch = allp[b:b + CROSS_BATCH]
        for k, p in enumerate(batch):
            p["pid"] = f"Q{b + k:04d}"
        qids = sorted({p["a"] for p in batch} | {p["b"] for p in batch})
        ctext = "\n".join(f"[{q}] {C[q].name}: {C[q].statement} (Active when: {C[q].active_when})" for q in qids)
        ptext = "\n".join(f"{p['pid']}: {p['a']} vs {p['b']}" for p in batch)
        tasks.append({"kind": "cross", "key": f"X_{b // CROSS_BATCH:03d}", "prompt": CROSS_PROMPT.format(claims=ctext, pairs=ptext),
                      "ids": [p["pid"] for p in batch], "pairs": batch})
    return tasks


def adjudicate_pairs(profiles: dict, support: dict, cross: list[dict]) -> list[dict]:
    """Phase-2 fact pairs from phase-1 results."""
    P = []

    def strongest(q, side=None):
        s = support.get(q) or {}
        pool = [r for r in s.get("facts", []) if r.get("support") == "supports" and (side is None or r.get("side") == side)]
        best = s.get("strongest")
        if best and any(r["id"] == best for r in pool):
            return best
        return pool[0]["id"] if pool else None
    for q, s in support.items():
        contested = profiles[q]["contested"]
        base = strongest(q, "1" if contested else None)
        contra = [r["id"] for r in s.get("facts", []) if r.get("support") == "contradicts"]
        for fid in contra:
            if base and fid != base:
                P.append({"kind": "within_contradicts", "claims": [q], "f1": base, "f2": fid})
        if contested and base:
            s2 = [r["id"] for r in s.get("facts", []) if r.get("side") == "2" and r["id"] not in contra][:3]
            for fid in s2:
                P.append({"kind": "within_contested", "claims": [q], "f1": base, "f2": fid})
    seen = set()
    for r in cross:
        if r.get("relation") != "contradicts":
            continue
        fa, fb = strongest(r["a"]), strongest(r["b"])
        if fa and fb and fa != fb and (fa, fb) not in seen:
            seen.add((fa, fb))
            P.append({"kind": "cross_claim", "claims": [r["a"], r["b"]], "f1": fa, "f2": fb})
    return P


def adjudicate_tasks(pairs: list[dict], profiles: dict, corpus, voice_turns: dict) -> list[dict]:
    fact_rows = {r["id"]: r for p in profiles.values() for r in p["facts"]}
    items = []
    for k, p in enumerate(pairs):
        blocks, refs, ok = [], {}, True
        for tag in ("f1", "f2"):
            fid = p[tag]
            r = fact_rows.get(fid)
            if not r or not r.get("conversation_id"):
                ok = False
                break
            if r.get("voice_mode") == "turn_contract" and r["turn_ids"]:
                w = corpus.turn_context(r["turn_ids"][0])
                ref = {"conversation_id": w["conversation_id"], "turn_ids": w["turn_ids"]} if w else None
            else:
                w = corpus.message_window(r["conversation_id"], voice_turns.get(fid), r["text"])
                ref = {"conversation_id": w["conversation_id"], "turn_ids": w["message_ids"]} if w else None
            if w is None:
                ok = False
                break
            refs[fid] = ref
            blocks.append(f"Fact {fid}: {r['text']}\n Context:\n{w['render']}")
        if not ok:
            continue
        kid = f"K{k:04d}"
        items.append((dict(p, kid=kid, context_refs=refs),
                      f"ITEM {kid} ({p['kind']}; claims {', '.join(p['claims'])})\n" + "\n".join(blocks)))
    tasks = []
    for b in range(0, len(items), ADJ_BATCH):
        batch = items[b:b + ADJ_BATCH]
        tasks.append({"kind": "adjudicate", "key": f"K_{b // ADJ_BATCH:03d}", "prompt": ADJ_PROMPT.format(items="\n\n".join(t for _, t in batch)),
                      "ids": [p["kid"] for p, _ in batch], "pairs": [p for p, _ in batch]})
    return tasks


# ---------------------------------------------------------------- interpretation
OWN_VOICES = {"own_words", "fair_description", "own_document"}
NOT_OWN_VOICES = {"assistant", "pasted"}


def interpret_support(profiles, results: dict) -> tuple[dict, list[dict]]:
    """results: claim qid -> parsed support reply. Returns per-claim support and findings."""
    out, per = [], {}
    for q, obj in results.items():
        facts = obj.get("facts", [])
        lab = {k: 0 for k in ("supports", "partial", "unrelated", "contradicts")}
        for r in facts:
            lab[r["support"]] += 1
        n = sum(lab.values())
        ratio = (lab["supports"] + 0.5 * lab["partial"]) / n if n else None
        rec = {"labels": lab, "judged": n, "support_ratio": round(ratio, 3) if ratio is not None else None,
               "strongest": obj.get("strongest"), "weakest": obj.get("weakest"), "facts": facts}
        if ratio is not None and ratio < WEAK_SUPPORT_RATIO:
            out.append(finding("weak_support", "warn", [q], [r["id"] for r in facts if r["support"] in ("unrelated", "contradicts")],
                               kind="model", detail=f"support ratio {ratio:.2f} over {n} judged facts", support_ratio=round(ratio, 3)))
        contra = [r["id"] for r in facts if r["support"] == "contradicts"]
        if contra:
            out.append(finding("cited_fact_contradicts_claim", "warn", [q], contra, kind="model",
                               detail=f"{len(contra)} cited fact(s) judged to evidence the opposite of the claim"))
        if profiles[q]["contested"]:
            sides = {"1": [], "2": []}
            for r in facts:
                if r.get("side") in sides and r["support"] in ("supports", "partial"):
                    sides[r["side"]].append(r["id"])
            rec["sides"] = {"side_1": obj.get("side_1"), "side_2": obj.get("side_2"), "side_1_evidence": sides["1"], "side_2_evidence": sides["2"]}
            empty = [s for s in ("1", "2") if not sides[s]]
            if empty:
                out.append(finding("contested_unsupported", "warn", [q], kind="model",
                                   detail=f"contested claim: side {' and '.join(empty)} has no supporting fact"))
        if any("referent" in r for r in facts):
            rc = {k: sum(r.get("referent") == k for r in facts) for k in ("document", "author", "other")}
            tot = sum(rc.values())
            rec["referent"] = {**rc, "on_referent_ratio": round(rc["author"] / tot, 3) if tot else None}
            if tot and rc["author"] / tot < NOT_HIS_RATIO:
                out.append(finding("claim_rests_on_document", "warn", [q], kind="model",
                                   detail=f"{rc['author']} of {tot} cited facts evidence the author; the rest describe the document"))
        per[q] = rec
    return per, out


def interpret_voice(profiles, voice_results: dict) -> tuple[dict, list[dict]]:
    """voice_results: fact id -> {voice, turn_id?, conversation_id}. Updates fact rows; returns per-claim voice and findings."""
    per, out = {}, []
    for q, prof in profiles.items():
        c = {"own": 0, "not_own": 0, "unsettled": 0, "fair_description": 0}
        not_own_ids = []
        for r in prof["facts"]:
            if r["status"] != "live":
                continue
            v = voice_results.get(r["id"])
            if v:
                r["model_voice"] = v["voice"]
                if v.get("turn_id") and not r["turn_ids"]:
                    r["turn_ids"] = [v["turn_id"]]
                    r["turn_resolution"] = "rater_turn_mapped_to_message_id"
            voice = r.get("model_voice") or r.get("voice")
            # a turn-contract fact keeps its deterministic verdict (corpus._voice_turn): own only if
            # every span's turn is own, None (unsettled) when no span's turn resolved
            own = r.get("own")
            if r.get("voice_mode") != "turn_contract" and r.get("model_voice"):
                own = True if voice in OWN_VOICES else (False if voice in NOT_OWN_VOICES else None)
            if own is True:
                c["own"] += 1
                c["fair_description"] += voice == "fair_description"
            elif own is False:
                c["not_own"] += 1
                not_own_ids.append(r["id"])
            else:
                c["unsettled"] += 1
        located = c["own"] + c["not_own"]
        ratio = c["own"] / located if located else None
        strict = (c["own"] - c["fair_description"]) / located if located else None
        per[q] = {**c, "own_voice_ratio": round(ratio, 3) if ratio is not None else None,
                  "own_voice_ratio_strict": round(strict, 3) if strict is not None else None}
        if ratio is not None and located >= NOT_HIS_MIN_LOCATED and ratio < NOT_HIS_RATIO:
            turns = [t for r in prof["facts"] if r["id"] in not_own_ids for t in r["turn_ids"]]
            out.append(finding("claim_not_his", "warn", [q], not_own_ids, turns, kind="model",
                               detail=f"own-voice ratio {ratio:.2f} over {located} located facts ({c['unsettled']} unsettled)",
                               own_voice_ratio=round(ratio, 3)))
    return per, out


def interpret_fidelity(profiles, fid_results: dict) -> tuple[dict, list[dict]]:
    per, out = {}, []
    for q, prof in profiles.items():
        labs = {}
        for r in prof["facts"]:
            v = fid_results.get(r["id"])
            if v:
                r["fidelity"] = v["label"]
                labs[r["id"]] = v["label"]
        if not labs:
            continue
        n = len(labs)
        strict = sum(v == "own_words" for v in labs.values()) / n
        lenient = sum(v in ("own_words", "fair_description") for v in labs.values()) / n
        per[q] = {"n": n, "strict": round(strict, 3), "lenient": round(lenient, 3),
                  "labels": {k: sum(v == k for v in labs.values()) for k in set(labs.values())}}
        bad = [f for f, v in labs.items() if v in ("overreach", "misread", "not_his")]
        if bad:
            turns = [t for r in prof["facts"] if r["id"] in bad for t in r["turn_ids"]]
            out.append(finding("fidelity_failure", "warn", [q], bad, turns, kind="model",
                               detail=f"{len(bad)} of {n} cited facts do not faithfully read their cited turn "
                                      f"(strict {strict:.2f}, lenient {lenient:.2f})"))
    return per, out


def interpret_cross(cross: list[dict]) -> list[dict]:
    out = []
    for r in cross:
        rel = r.get("relation")
        if rel == "contradicts":
            out.append(finding("claims_contradict", "warn", [r["a"], r["b"]], kind="model", detail=f"condition: {r.get('condition')}", arm=r.get("arm")))
        elif rel == "duplicate":
            out.append(finding("claims_duplicate", "info", [r["a"], r["b"]], kind="model", detail="judged the same claim", arm=r.get("arm")))
        elif rel == "tensions":
            out.append(finding("claims_in_tension", "info", [r["a"], r["b"]], kind="model", detail=f"condition: {r.get('condition')}", arm=r.get("arm")))
    return out


def interpret_adjudication(adj: list[dict]) -> list[dict]:
    out = []
    sev = {"real_contradiction": "error", "misattribution": "warn", "extraction_error": "warn", "context_split": "info", "no_conflict": "info"}
    for a in adj:
        refs = a.get("context_refs", {})
        turns = [t for v in refs.values() if v for t in v.get("turn_ids", [])]
        convs = sorted({v["conversation_id"] for v in refs.values() if v})
        out.append(finding("contradiction_" + a["verdict"], sev[a["verdict"]], a["claims"], [a["f1"], a["f2"]], turns, convs,
                           kind="model", detail=f"{a['kind']}: {a.get('reason') or ''}".strip(),
                           condition=a.get("condition"), which_fact=a.get("which_fact")))
    # contested confirmation
    return out


def contested_confirmation(profiles, adj: list[dict]) -> dict:
    conf = {}
    for q, p in profiles.items():
        if not p["contested"]:
            continue
        mine = [a for a in adj if a["kind"] == "within_contested" and q in a["claims"]]
        confirmed = any(a["verdict"] in ("context_split", "real_contradiction") for a in mine)
        conf[q] = {"pairs_read": len(mine), "confirmed": confirmed,
                   "status": "confirmed" if confirmed else ("unconfirmed" if mine else "not_read")}
    return conf
