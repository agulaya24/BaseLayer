"""Import-time secret redaction (docs/core/TURN_CONTRACT.md, section 1).

Every secret in this file is SYNTHETIC and built by concatenation at run time, so no
key-shaped literal sits in the tracked tree (a literal would trip push protection and the
repository's own PII scan). The tests assert behaviour through the public import entry
points: the ``turns`` table, the legacy ``messages`` table, conversation titles, and the
per-conversation counts in ``import_redactions``.
"""
import json

import pytest

import baselayer.import_conversations as IC
import baselayer.recovered_import as RI
from baselayer import redaction as R
from tests.test_turn_contract_import import (  # noqa: F401  (env is a fixture)
    assistant, cc_import, env, typed, turns, write_session,
)
from tests.test_recovered_import import make_db, write_history, h

# ----------------------------------------------------------------------- synthetic secrets
# Built from parts so the literal never appears in the file.
ANT = "sk-" + "ant-" + "api03-" + "Zq7" * 15
OAI = "sk-" + "proj-" + "Ab3d" * 8
AWS = "AK" + "IA" + "Q3EXAMPLE7KEY2ZZ"
GHP = "gh" + "p_" + "a1B2" * 10
SLACK = "xo" + "xb-" + "1234567890-abcdefghijkl"
JWT = "ey" + "J" + "hbGciOiJIUzI1NiJ9" + ".ey" + "J" + "zdWIiOiIxMjM0NTY3ODkwIn0" + "." + "dBjftJeZ4CVPmB92K27uhbUJU1p1r_wW1gFWFOEjXk"
PEM = ("-----BEGIN " + "RSA PRIVATE KEY-----\n" + ("MIIEow" + "IBAAKCAQEA" * 6 + "\n") * 3
       + "-----END " + "RSA PRIVATE KEY-----")
HEXKEY = "9f" * 20                      # 40 hex chars
CARD = "4111" + " 1111" + " 1111" + " 1111"   # Luhn-valid test Visa
SSN = "219" + "-09-" + "9999"
PW = "hunter" + "2-correct-horse"


def _secrets():
    return [ANT, OAI, AWS, GHP, SLACK, JWT, HEXKEY, CARD, SSN, PW, "MIIEow"]


def _no_secret_anywhere(conn):
    blobs = [r[0] or "" for r in conn.execute("SELECT text FROM turns")]
    blobs += [r[0] or "" for r in conn.execute("SELECT content_text FROM messages")]
    blobs += [r[0] or "" for r in conn.execute("SELECT title FROM conversations")]
    joined = "\n".join(blobs)
    return [s for s in _secrets() if s in joined]


# ----------------------------------------------------------------------- unit: kinds

@pytest.mark.parametrize("text,kind", [
    (f"my key is {ANT} ok", "anthropic_key"),
    (f"export OPENAI_API_KEY={OAI}", "openai_key"),
    (f"aws {AWS} here", "aws_access_key"),
    (f"token {GHP}", "github_token"),
    (f"slack {SLACK}", "slack_token"),
    (f"auth header {JWT}", "jwt"),
    (f"{PEM}\nafter", "private_key"),
    (f"api_key = \"{HEXKEY}\"", "context_secret"),
    (f"Authorization: Bearer {HEXKEY}", "context_secret"),
    (f"card {CARD} exp 12/29", "card_number"),
    (f"ssn {SSN} on file", "ssn"),
    (f"Password: {PW}", "password"),
    (f"'password': '{PW}',", "password"),
    (f"login pwd={PW}&x=1", "password"),
    (f"postgres://admin:{PW}@db.example.invalid/x", "url_credentials"),
])
def test_each_secret_kind_is_masked_and_counted(text, kind):
    out, counts = R.redact(text)
    assert f"[REDACTED:{kind}]" in out
    assert counts[kind] >= 1
    for s in _secrets():
        assert s not in out


def test_unterminated_private_key_is_masked():
    truncated = PEM.split("-----END")[0]
    out, counts = R.redact("see " + truncated)
    assert counts["private_key"] == 1 and "MIIEow" not in out


@pytest.mark.parametrize("text", [
    "commit 7400c38 and 30e3509ab12cd34ef567890abcdef1234567890a",
    "session 0596584a-7748-4b7b-a3e9-cc54dc3ebdf5",
    "epoch ms 1727200000000 and 1727200000004",
    "dated 2026-09-24 and 2026-09-24T10:11:12Z",
    "max_tokens=4096 and token_count: 123456",
    "PWD=/c/Users/someone/project",
    "sha256: " + "ab" * 32,
    "the password is managed by the vault",
    "phone 555-867-5309",
    "password: None",
])
def test_ordinary_text_is_not_masked(text):
    out, counts = R.redact(text)
    assert out == text, (text, out)
    assert not counts


def test_redaction_is_idempotent_and_leaves_existing_markers():
    once, c1 = R.redact(f"key {ANT} and an older [REDACTED_API_KEY] marker")
    twice, c2 = R.redact(once)
    assert once == twice and not c2 and c1["anthropic_key"] == 1
    assert "[REDACTED_API_KEY]" in once


def test_long_text_is_linear_enough():
    import time
    big = ("ordinary words and 12345 numbers, paths C:/a/b.py:12 " * 20000) + ANT
    t0 = time.time()
    out, counts = R.redact(big)
    assert counts["anthropic_key"] == 1
    assert time.time() - t0 < 5


# ----------------------------------------------------------------------- import paths

def test_claude_code_import_masks_citable_and_context_rows_and_counts_them(env):
    sid = "sess-secret"
    recs = [typed(f"use this key {ANT} for the pilot run tonight please", sid),
            assistant(f"Stored it. The card on file is {CARD}.", sid),
            typed(f"This session is being continued from a previous conversation that ran out "
                  f"of context. Summary: the key was {OAI}.", sid)]
    write_session(env.projects, sid, recs)
    cc_import(env)
    assert _no_secret_anywhere(env.conn) == []
    counts = dict(((k, n) for k, n in env.conn.execute(
        "SELECT kind, n FROM import_redactions WHERE conversation_id=? AND source='claude_code'",
        (sid,))))
    assert counts == {"anthropic_key": 2, "card_number": 1, "openai_key": 1}  # key also in the title
    by_class = {("citable" if r["voice_class"].startswith("own_") else r["voice_class"])
                for r in turns(env.conn, sid) if "[REDACTED:" in r["text"]}
    assert by_class == {"citable", "assistant", "compaction_summary"}


def test_grown_session_with_a_secret_is_grown_not_conflict(env):
    sid = "sess-grow-secret"
    p = write_session(env.projects, sid, [typed(f"first question with {GHP} in it", sid),
                                          assistant("First answer.", sid)])
    cc_import(env)
    with open(p, "a", encoding="utf-8") as fh:
        fh.write(json.dumps(typed("a later question", sid)) + "\n")
    cc_import(env)
    st = env.conn.execute("SELECT status FROM import_state WHERE conversation_id=?",
                          (sid,)).fetchone()
    assert st[0] == "grown"
    n = env.conn.execute("SELECT SUM(n) FROM import_redactions WHERE conversation_id=?",
                         (sid,)).fetchone()[0]
    assert n == 2  # turn + title, counted once, not once per import


def test_history_prompt_with_a_secret_still_dedupes_against_its_transcript(env, tmp_path):
    prompt = f"set the key to {ANT} and then rerun the nightly backup job again"
    write_session(env.projects, "sess-t", [typed(prompt, "sess-t")])
    cc_import(env)
    hist = tmp_path / "history.jsonl"
    hist.write_text(json.dumps({"display": prompt, "pastedContents": {}, "timestamp": 1,
                                "sessionId": "h-9"}) + "\n", encoding="utf-8")
    IC.import_history(env.conn, [hist], set())
    rows = turns(env.conn, "history_h-9")
    assert [r["duplicate_of"] for r in rows] == ["sess-t"]
    assert _no_secret_anywhere(env.conn) == []
    src = dict(env.conn.execute("SELECT source, SUM(n) FROM import_redactions GROUP BY source"))
    assert src["claude_code_history"] == 2  # the prompt and the title made from it


def test_chatgpt_import_masks_secrets(env, tmp_path):
    conv = {"conversation_id": "cg-sec", "title": "t", "create_time": 1, "update_time": 2,
            "mapping": {
                "r": {"id": "r", "parent": None, "children": ["u"], "message": None},
                "u": {"id": "u", "parent": "r", "children": ["a"], "message": {
                    "id": "u", "author": {"role": "user"}, "create_time": 1,
                    "content": {"content_type": "text", "parts": [f"my ssn is {SSN} ok"]}}},
                "a": {"id": "a", "parent": "u", "children": [], "message": {
                    "id": "a", "author": {"role": "assistant"}, "create_time": 2,
                    "content": {"content_type": "text", "parts": [f"Noted {AWS}."]}}}}}
    f = tmp_path / "conversations.json"
    f.write_text(json.dumps([conv]), encoding="utf-8")
    IC.import_chatgpt(env.conn, str(f), set())
    assert _no_secret_anywhere(env.conn) == []
    got = dict(env.conn.execute("SELECT kind, n FROM import_redactions WHERE source='chatgpt'"))
    assert got == {"ssn": 1, "aws_access_key": 1}


def test_db_copy_import_masks_secrets_and_keeps_redacted_copy_precedence(env, tmp_path):
    sid = "0596584a-0000-4000-8000-000000000001"
    text = f"please rotate {ANT} tonight before the demo"
    a = make_db(tmp_path / "a.db", {sid: [("user", text), ("assistant", "ok")]})
    b = make_db(tmp_path / "b.db", {sid: [("user", "please rotate [REDACTED_KEY] tonight "
                                                   "before the demo"), ("assistant", "ok")]})
    stats = RI.import_db_copies(env.conn, [("a", a), ("b", b)], [env_hist(tmp_path)])
    assert stats["conflicts_resolved_redacted"] == 1
    rows = turns(env.conn, f"dbcopy_{sid}")
    assert "[REDACTED_KEY]" in rows[0]["text"]
    assert _no_secret_anywhere(env.conn) == []


def test_db_copy_secret_in_the_only_copy_is_masked(env, tmp_path):
    sid = "0596584a-0000-4000-8000-000000000002"
    a = make_db(tmp_path / "a.db", {sid: [("user", f"the key is {OAI} use it"),
                                          ("assistant", f"Using {OAI}.")]})
    RI.import_db_copies(env.conn, [("a", a)], [env_hist(tmp_path)])
    assert _no_secret_anywhere(env.conn) == []
    got = dict(env.conn.execute("SELECT kind, SUM(n) FROM import_redactions "
                                "WHERE source='claude_code_db_copy' GROUP BY kind"))
    assert got["openai_key"] >= 2


def env_hist(tmp_path):
    p = tmp_path / "hist_empty.jsonl"
    if not p.exists():
        write_history(p, [h("unrelated", "nothing", 1)])
    return p


def test_json_file_import_masks_secrets(env, tmp_path):
    f = tmp_path / "notes.json"
    f.write_text(json.dumps({"content": f"remember the api_key = {HEXKEY} for later use " * 2}),
                 encoding="utf-8")
    IC.import_json_files(env.conn, str(f), set())
    assert _no_secret_anywhere(env.conn) == []


# A legacy encrypted PEM (RFC 1421 headers) is masked whole. Synthetic key material only.
_ENC_BODY = "MIIE" + "owFAKEFAKE" * 6


def _encrypted_pem():
    return ("-----BEGIN " + "RSA PRIVATE KEY-----\n"
            "Proc-Type: 4,ENCRYPTED\n"
            "DEK-Info: AES-128-CBC,ABCDEF0123456789ABCDEF0123456789\n\n"
            + (_ENC_BODY + "\n") * 3
            + "-----END " + "RSA PRIVATE KEY-----")


def test_encrypted_pem_body_and_end_line_are_masked():
    out, counts = R.redact("key follows\n" + _encrypted_pem() + "\nafter")
    assert counts["private_key"] == 1
    assert "owFAKEFAKE" not in out
    assert "-----END" not in out
    assert out.startswith("key follows\n") and out.endswith("\nafter")


def test_plain_pem_unchanged_behaviour():
    pem = ("-----BEGIN " + "RSA PRIVATE KEY-----\n" + (_ENC_BODY + "\n") * 3
           + "-----END " + "RSA PRIVATE KEY-----")
    out, counts = R.redact(pem + "\nafter")
    assert counts["private_key"] == 1 and "owFAKEFAKE" not in out and out.endswith("\nafter")
