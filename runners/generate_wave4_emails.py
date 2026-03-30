#!/usr/bin/env python3
"""Generate Wave 4 email drafts for 16 new subjects."""
import sys, io, os, json, re
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

from pathlib import Path

BASE = Path(__file__).parent.parent.parent
PW_FILE = Path(__file__).parent.parent / "data" / "seeds" / "passwords.json"
passwords = json.loads(PW_FILE.read_text()) if PW_FILE.exists() else {}

subjects = [
    ("derek_sivers", "Derek Sivers", "Derek", "derek-sivers", "derek@sivers.org", 544, "essays from sivers.org", 6054),
    ("andy_matuschak", "Andy Matuschak", "Andy", "andy-matuschak", "andy@andymatuschak.org", 843, "notes and essays", 12629),
    ("gwern_branwen", "Gwern Branwen", "Gwern", "gwern-branwen", "gwern@gwern.net", 356, "essays from gwern.net", 5759),
    ("kyle_harrison", "Kyle Harrison", "Kyle", "kyle-harrison", "kyle@contrary.com", 225, "Substack posts", 3314),
    ("tomasz_tunguz", "Tomasz Tunguz", "Tomasz", "tomasz-tunguz", "tt@theory.ventures", 1679, "blog posts", 25150),
    ("zvi_mowshowitz", "Zvi Mowshowitz", "Zvi", "zvi-mowshowitz", "zvi@thezvi.com", 1089, "essays and posts", 17038),
    ("eric_schwitzgebel", "Eric Schwitzgebel", "Eric", "eric-schwitzgebel", "eschwitz@ucr.edu", 1326, "blog posts", 33902),
    ("jack_clark", "Jack Clark", "Jack", "jack-clark", "placeholder@import.ai", 457, "Import AI newsletters", 12714),
    ("morgan_housel", "Morgan Housel", "Morgan", "morgan-housel", "morgan@collabfund.com", 335, "Collab Fund essays", 5525),
    ("patrick_mckenzie", "Patrick McKenzie", "Patrick", "patrick-mckenzie", "patrick@kalzumeus.com", 482, "essays", 7377),
    ("seth_godin", "Seth Godin", "Seth", "seth-godin", "seth@sethgodin.com", 200, "blog posts", 3590),
    ("visakan_veerasamy", "Visakan Veerasamy", "Visa", "visakan-veerasamy", "visakanv@gmail.com", 961, "essays and threads", 15221),
    ("ava_huang", "Ava Huang", "Ava", "ava-huang", "placeholder@substack.com", 167, "introspective essays", 2659),
    ("nabeel_qureshi", "Nabeel Qureshi", "Nabeel", "nabeel-qureshi", "nabeelsqu@gmail.com", 30, "deep essays", 454),
    ("tim_urban", "Tim Urban", "Tim", "tim-urban", "contact@waitbutwhy.com", 200, "Wait But Why essays", 2644),
    ("julia_galef", "Julia Galef", "Julia", "julia-galef", "placeholder@juliagalef.com", 165, "essays and interviews", 2182),
]

drafts = []
for subj_id, name, first, slug, email, src_count, src_desc, fact_count in subjects:
    pw = passwords.get(subj_id, "")

    # Get P1 prediction
    pred_file = BASE / "subjects" / f"{subj_id}_memory" / "data" / "identity_layers" / "predictions_v4.md"
    pred_name = pred_trigger = pred_directive = pred_fp = ""
    if pred_file.exists():
        text = pred_file.read_text(encoding="utf-8")
        m = re.search(r'\*\*P1\.\s+([A-Z][A-Z0-9 _-]+)\*\*:?\s*(.*?)(?=\n---\n|\n\*\*P2\.|\Z)', text, re.DOTALL)
        if m:
            pred_name = m.group(1).strip()
            body = m.group(2).strip()
            t = re.search(r'^(.*?)(?=\s*Detection:|\s*\n-)', body, re.DOTALL)
            pred_trigger = t.group(1).strip()[:300] if t else body[:250]
            d = re.search(r'Directive:\s*(.*?)(?=\nFalse positive|\n\*\*P|\n---|\Z)', body, re.DOTALL)
            pred_directive = d.group(1).strip()[:300] if d else ""
            f = re.search(r'False positive[^:]*:\s*(.*?)(?=\n---|\n\*\*P|\Z)', body, re.DOTALL)
            pred_fp = f.group(1).strip()[:300] if f else ""

    subject_line = f"{fact_count:,} facts from {src_count} {src_desc}. {name}'s identity model."

    body = f"""{first},<br><br>

I've been building an open-source system that extracts behavioral identity from text, and I ran it on {src_count} of your {src_desc}. {fact_count:,} facts, compressed into one identity model. Below is one item that stood out to me:<br><br>

<ul>
<li><b><i>{pred_name}:</i></b> {pred_trigger}</li>
<li><b><i>Directive:</i></b> {pred_directive}</li>
<li><b><i>False Positive Warning:</i></b> {pred_fp}</li>
</ul>

I picked this one because I recognize a similar pattern in myself. I'm curious if it captured you correctly.<br><br>

<b>Link:</b> https://base-layer.ai/thinkers/{slug}<br>
<b>Password:</b> {pw}<br><br>

Every conclusion is inspectable, with complete traceability/audit trail from the extracted facts to the final synthesis. You are welcome to edit, use, delete, and experiment as you see fit.<br><br>

I hope you enjoy your identity model, and that it reveals something you forgot or couldn't quite put into words.<br>
Aarik"""

    drafts.append({
        "name": name,
        "to": email,
        "subject": subject_line,
        "body": body,
        "slug": slug,
    })

    print(f"{name:25s} -> {email}")
    print(f"  Subject: {subject_line}")
    print(f"  Prediction: {pred_name}")
    print()

# Save drafts as JSON for push_gmail_drafts.py
output_file = BASE / "drafts" / "wave4_drafts.json"
output_file.parent.mkdir(exist_ok=True)
with open(output_file, "w", encoding="utf-8") as fp:
    json.dump(drafts, fp, indent=2, ensure_ascii=False)

print(f"\n{len(drafts)} drafts saved to {output_file}")
print(f"Placeholder emails (need manual fix): Jack Clark, Ava Huang, Julia Galef")
