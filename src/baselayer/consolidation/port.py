"""Convert the 2026-09-28/29 prototype files into consolidation stage inputs. No model.

    python -m baselayer.consolidation.port --trigger-index trigger_index.json \
        --groups groups.json [--mapping mapping.json] --out <dir>

    trigger_index.json (the 9/29 hand grouping)  -> <dir>/grouping.json
        Each trigger keeps its key, members and member clauses. Its stored category is
        DROPPED: the categories stage recomputes it from the claim-level assignment, so
        reproducing the 9/29 layout tests the rule rather than copying its answer.
        The wording source's clause is recovered as the one member whose claim is the
        wording source and whose clause, first letter capitalised, equals the wording;
        anything other than exactly one such member is an error.
    groups.json (the 9/28 merge preview)          -> <dir>/categories.json
        The categories with their member claims, ids T1..Tn in file order.
    mapping.json (the 9/28 merge preview)          -> <dir>/dedupe_map.json   (optional)
        {"source_to_group": claim -> merged claim}, for `--dedupe-basis external`.

The outputs hold claim ids, clause text and category names from one person's spec, so
they belong beside that spec's working files, never in this repository.
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

from .common import file_sha256, read_json, write_json

WHOLE = "*"


def grouping_from_trigger_index(ti: dict) -> dict:
    out = []
    for t in ti["triggers"]:
        members = [{"claim": m["claim"], "clause": WHOLE if m["whole_condition"] else m["clause"]}
                   for m in t["members"]]
        src = [m for m in t["members"] if m["claim"] == t["wording_source"]
               and (m["clause"][:1].upper() + m["clause"][1:]) == t["wording"]]
        if len(src) != 1:
            raise ValueError(f"trigger {t['id']} ({t['key']}): {len(src)} members match its wording source")
        s = src[0]
        out.append({"key": t["key"], "wording_source": {"claim": s["claim"],
                                                        "clause": WHOLE if s["whole_condition"] else s["clause"]},
                    "members": members})
    return {"method": ti.get("method"), "ported_from": "trigger index (prototype, 2026-09-29)", "triggers": out}


def categories_from_groups(g: dict) -> dict:
    cats = [{"id": f"T{i}", "name": c["name"], "members": list(c["members"])}
            for i, c in enumerate(g["categories"], 1)]
    return {"method": "claim-level assignment ported from the 2026-09-28 merge preview", "categories": cats}


def dedupe_map_from_mapping(m: dict) -> dict:
    return {"source_to_group": dict(m["source_to_merged"]),
            "ported_from": "merge preview mapping (prototype, 2026-09-28)"}


def main(argv=None) -> int:
    p = argparse.ArgumentParser(prog="python -m baselayer.consolidation.port", description=__doc__,
                                formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--trigger-index", required=True)
    p.add_argument("--groups", required=True)
    p.add_argument("--mapping")
    p.add_argument("--out", required=True)
    a = p.parse_args(argv)
    out = Path(a.out)
    prov = {"trigger_index": file_sha256(a.trigger_index), "groups": file_sha256(a.groups)}
    gr = grouping_from_trigger_index(read_json(a.trigger_index))
    gr["source_sha256"] = prov["trigger_index"]
    write_json(out / "grouping.json", gr)
    cat = categories_from_groups(read_json(a.groups))
    cat["source_sha256"] = prov["groups"]
    write_json(out / "categories.json", cat)
    print(f"grouping.json: {len(gr['triggers'])} triggers; categories.json: {len(cat['categories'])} categories")
    if a.mapping:
        dm = dedupe_map_from_mapping(read_json(a.mapping))
        dm["source_sha256"] = file_sha256(a.mapping)
        write_json(out / "dedupe_map.json", dm)
        print(f"dedupe_map.json: {len(dm['source_to_group'])} claims")
    return 0


if __name__ == "__main__":
    sys.exit(main())
