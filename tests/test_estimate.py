"""`baselayer estimate` prices extraction from the dated rate table in distillation/spend.py.

Before this, it carried its own table (Haiku 4.5 at $0.80/$4.00 while spend.py says $1/$5)
and printed fixed "post-extraction" figures, including a brief that `baselayer run` never
composes. No API calls: a scratch SQLite file only.
"""
import sqlite3
from types import SimpleNamespace as NS

import pytest

from baselayer import cli, config
from baselayer.distillation import spend


def _db(path, n_convos=3, n_done=1, chars=3500):
    conn = sqlite3.connect(path)
    conn.executescript("""
        CREATE TABLE conversations (id TEXT PRIMARY KEY);
        CREATE TABLE messages (id TEXT, conversation_id TEXT, content_text TEXT);
        CREATE TABLE extraction_log (conversation_id TEXT);
    """)
    for i in range(n_convos):
        conn.execute("INSERT INTO conversations VALUES (?)", (f"c{i}",))
        conn.execute("INSERT INTO messages VALUES (?, ?, ?)", (f"m{i}", f"c{i}", "x" * chars))
    for i in range(n_done):
        conn.execute("INSERT INTO extraction_log VALUES (?)", (f"c{i}",))
    conn.commit()
    conn.row_factory = sqlite3.Row
    return conn


@pytest.fixture
def scratch(tmp_path, monkeypatch):
    path = tmp_path / "memory.db"
    _db(path).close()
    monkeypatch.setattr(config, "DATABASE_FILE", path)
    monkeypatch.setattr(config, "get_db", lambda: sqlite3.connect(path))
    return path


def test_rate_comes_from_the_dated_table():
    # a dated id is looked up by the undated name; the extraction table (config) and the
    # distillation table (spend.py) agree on Haiku 4.5
    assert cli._estimate_rate("claude-haiku-4-5-20251001") == spend.RATES_PER_MTOK["claude-haiku-4-5"]
    assert cli._estimate_rate("claude-haiku-4-5") == spend.RATES_PER_MTOK["claude-haiku-4-5"]
    assert cli._estimate_rate(config.EXTRACTION_API_MODEL) == (0.10, 0.50)   # Haiku 5.5, default
    assert cli._estimate_rate("claude-opus-5-5") == spend.RATES_PER_MTOK["claude-opus-5-5"]
    assert cli._estimate_rate("no-such-model-20250101") is None


def test_estimate_prints_the_table_rate_and_date(scratch, monkeypatch, capsys):
    monkeypatch.setattr(config, "EXTRACTION_API_MODEL", "claude-haiku-4-5-20251001")
    cli.cmd_estimate(NS())
    out = capsys.readouterr().out
    i, o = spend.RATES_PER_MTOK["claude-haiku-4-5"]
    assert f"${i:g} in / ${o:g} out" in out
    assert config.SPEND_RATES_AS_OF in out
    # 2 pending conversations x 3500 chars / 3.5 chars per token = 2000 input tokens,
    # 2 x 200 output tokens; at $1 / $5 per MTok that is $0.002 + $0.002.
    assert "Pending extraction:     2" in out
    expected = 2000 / 1e6 * i + 400 / 1e6 * o
    assert f"${expected:,.2f}" in out
    assert "0.80" not in out                       # the old private rate is gone


def test_estimate_prints_no_fixed_downstream_figures(scratch, capsys):
    cli.cmd_estimate(NS())
    out = capsys.readouterr().out
    assert "Brief composition" not in out
    assert "~$0.10" not in out and "~$0.20" not in out and "~$0.30" not in out
    assert "within 2x" not in out
    assert "floor" in out


def test_estimate_with_an_unpriced_model_prints_no_cost(scratch, monkeypatch, capsys):
    monkeypatch.setattr(config, "EXTRACTION_API_MODEL", "local-model")
    cli.cmd_estimate(NS())
    out = capsys.readouterr().out
    assert "No rate for this model" in out
    assert "Estimated extraction:" not in out
