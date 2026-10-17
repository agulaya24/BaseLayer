"""One JSON and one markdown report per spec."""
from __future__ import annotations

import collections
import json
from pathlib import Path


def write_reports(report: dict, out_dir: Path) -> tuple[Path, Path]:
    label = report["meta"]["label"]
    jp = out_dir / f"{label}.verification.json"
    mp = out_dir / f"{label}.verification.md"
    tmp = jp.with_suffix(".json.tmp")
    tmp.write_text(json.dumps(report, indent=1, ensure_ascii=False, default=str), encoding="utf-8")
    tmp.replace(jp)
    tmp = mp.with_suffix(".md.tmp")
    tmp.write_text(render_markdown(report), encoding="utf-8")
    tmp.replace(mp)
    return jp, mp


def _cell(s) -> str:
    return str(s).replace("|", "/").replace("\n", " ")


def render_markdown(r: dict) -> str:
    m = r["meta"]
    L = [f"# Verification: {m['label']}", ""]
    L.append(f"- Spec: `{m['spec_dir']}` ({m['n_claims']} claims)")
    L.append(f"- Corpus: `{m['corpus']['db']}`, opened {m['corpus']['open_mode']}")
    L.append(f"- Voice mode: {m['voice_mode']} (per live cited fact: {m['voice_modes']}; a fact is gated iff it "
             f"carries a turn_contract_version)")
    L.append(f"- Model steps: {m['model']['status']}")
    if m["model"].get("rater"):
        pv = m["model"]["rater"]
        L.append(f"- Rater: {pv.get('rater')}, blind={pv.get('blind')}; channel: {pv.get('blind_channel')}; probe: "
                 f"{'stored' if isinstance(pv.get('probe'), dict) else pv.get('probe')}")
    L.append(f"- Versions: {m['versions']}")
    L.append("")
    s = r["summary"]
    L += ["## Summary", ""]
    for k, v in s.items():
        L.append(f"- {k}: {v}")
    L.append("")
    counts = collections.Counter((f["kind"], f["check"], f["severity"]) for f in r["findings"])
    L += ["## Findings by check", "", "| kind | check | severity | count |", "|---|---|---|---|"]
    for (k, c, sv), n in sorted(counts.items()):
        L.append(f"| {k} | {c} | {sv} | {n} |")
    L.append("")
    L += ["## Findings", "", "| check | severity | claims | fact ids | turn ids | detail |", "|---|---|---|---|---|---|"]
    order = {"error": 0, "warn": 1, "info": 2}
    for f in sorted(r["findings"], key=lambda f: (order.get(f["severity"], 3), f["check"], f["claims"])):
        fids = ", ".join(f["fact_ids"][:6]) + (f" (+{len(f['fact_ids']) - 6})" if len(f["fact_ids"]) > 6 else "")
        tids = ", ".join(f["turn_ids"][:4]) + (f" (+{len(f['turn_ids']) - 4})" if len(f["turn_ids"]) > 4 else "")
        L.append(f"| {f['check']} | {f['severity']} | {_cell(', '.join(f['claims']))} | {_cell(fids)} | {_cell(tids)} | {_cell(f['detail'])} |")
    L.append("")
    if m["model"].get("estimate"):
        L += ["## Model-step estimate", "", "```", m["model"]["estimate_text"], "```", ""]
    L += ["## Definitions", "", "```json", json.dumps(r["definitions"], indent=1), "```", ""]
    return "\n".join(L)
