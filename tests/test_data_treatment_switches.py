"""Switches in the local import config that change what counts as the subject's own words
(docs/core/DATA_TREATMENT_POLICY.md). Each test shows the default and the switched outcome
through the importer's own path, not only through the settings object. Synthetic text only.
"""
import pytest

from baselayer import turn_import as TI
from baselayer import voice as V
from baselayer.import_config import config_from_dict

CODE = "\n".join([
    "def total(rows):",
    "    acc = 0",
    "    for r in rows:",
    "        acc += r.amount",
    "    return acc",
])
PROMPT = "ok so this keeps returning the wrong total\n\n" + CODE + "\n\ncan you tell me why"


def _history_rows(cfg):
    entries = [{"display": PROMPT, "timestamp": 1_700_000_000_000}]
    return TI.build_history_turns("s1", entries, cfg).rows


def test_detect_code_machine_defaults_on():
    cfg = config_from_dict({})
    assert cfg.detect_code_machine is True
    assert cfg.voice_settings().detect_code_machine is True
    rows = _history_rows(cfg)
    moved = [r for r in rows if r.detector == V.D_PASTE_CODE_MACHINE]
    assert moved and moved[0].text.strip() == CODE


def test_detect_code_machine_off_keeps_code_as_own_words():
    cfg = config_from_dict({"detect_code_machine": False})
    assert cfg.voice_settings().detect_code_machine is False
    rows = _history_rows(cfg)
    assert all(r.detector != V.D_PASTE_CODE_MACHINE for r in rows)
    own = "".join(r.text for r in rows if r.citable)
    assert CODE in own


@pytest.mark.parametrize("on", [True, False])
def test_the_switch_reaches_the_message_list_importer(on):
    cfg = config_from_dict({"detect_code_machine": on})
    msgs = [{"role": "user", "text": PROMPT, "id": "m1", "created_at": 1.0},
            {"role": "assistant", "text": "It sums amounts.", "id": "m2", "created_at": 2.0}]
    rows = TI.build_message_list_turns(msgs, cfg, "h").rows
    moved = any(r.detector == V.D_PASTE_CODE_MACHINE for r in rows)
    assert moved is on


def test_detect_code_machine_must_be_a_boolean():
    with pytest.raises(ValueError):
        config_from_dict({"detect_code_machine": "no"})
