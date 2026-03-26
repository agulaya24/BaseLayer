#!/usr/bin/env python3
"""Build Google Apps Script to create Gmail drafts for all outreach emails."""

import csv
import json

NO_EMAIL = {"substack-dm", "substack", "no-public-email", "swyx.io", "pluralistic.net"}

with open("C:/Users/Aarik/Anthropic/outreach_emails.csv", encoding="utf-8-sig") as f:
    reader = csv.DictReader(f)
    rows = list(reader)

lines = ["function createOutreachDrafts() {", "  var drafts = ["]

missing = []
for row in rows:
    name = row["Name"]
    email = row["Email"]
    subject = row["Subject Line"]
    body = row["Email Body"].replace(" | ", "\n").replace("\n| ", "\n")

    if email in NO_EMAIL:
        missing.append(f"{name} ({email})")
        lines.append(f"    // SKIPPED: {name} - no direct email ({email})")
        continue

    # Escape for JS string
    body_escaped = body.replace("\\", "\\\\").replace('"', '\\"').replace("\n", "\\n")
    subject_escaped = subject.replace('"', '\\"')

    lines.append(f'    {{to: "{email}", subject: "{subject_escaped}", body: "{body_escaped}"}},')

lines.append("  ];")
lines.append("")
lines.append("  for (var i = 0; i < drafts.length; i++) {")
lines.append("    var d = drafts[i];")
lines.append("    GmailApp.createDraft(d.to, d.subject, d.body);")
lines.append("    Logger.log('Draft created for: ' + d.to);")
lines.append("  }")
lines.append("")
lines.append("  Logger.log('Done! ' + drafts.length + ' drafts created.');")
lines.append("}")

script = "\n".join(lines) + "\n"

with open("C:/Users/Aarik/Anthropic/gmail_drafts.gs", "w", encoding="utf-8") as f:
    f.write(script)

have_email = sum(1 for r in rows if r["Email"] not in NO_EMAIL)
print(f"Script written: gmail_drafts.gs")
print(f"Drafts: {have_email} with emails")
print(f"Missing emails ({len(missing)}):")
for m in missing:
    print(f"  - {m}")
