"""Local import configuration: exclusions, allowlist, meeting speaker labels, harness
signatures.

This file is the MECHANISM. The configuration itself is personal data (conversation ids,
the subject's name, machine paths, the ids of pasted segments the subject chose to keep),
so it must live outside the repository. Resolution order:

1. ``BASELAYER_IMPORT_CONFIG`` (explicit path).
2. ``<PROJECT_ROOT>/data/import_config.json``, i.e. inside the corpus directory named by
   ``MEMORY_SYSTEM_ROOT``. That path is gitignored.

A missing file means an empty configuration. A file that exists but does not parse raises:
an exclusion list that silently fails to load would import exactly what it exists to keep
out.

Keys (all optional)::

    {
      "exclude_conversations": ["<conversation id>", ...],
      "exclude_sources": ["text_file", ...],
      "exclude_path_globs": ["*/project_docs/*", ...],
      "paste_allowlist": ["<turn id>", ...],
      "subject_names": ["<name as it appears in a greeting>", ...],
      "meeting_subject_labels": ["<speaker label in meeting transcripts>", ...],
      "harness_cwd_patterns": ["<regex over a record's cwd>", ...],
      "harness_template_roots": ["<dir of prompt-building scripts>", ...],
      "harness_template_exclude_dirs": ["<dir name to skip under those roots>", ...],
      "extra_typos": ["<misspelling the subject habitually types>", ...],
      "typography_is_paste": false,
      "include_originless_queued": false,
      "canary_strings": ["<marker an injection hook writes into its context>", ...],
      "allowlist_own_writing_pasted": false,
      "own_writing_min_traits": 3,
      "detect_code_machine": true
    }

``subject_names`` is the subject's names. It serves two readers: the importer treats a
greeting addressed to one of them as pasted material, and turn-contract extraction takes it
as the corpus's REFERENT (``turn_contract.Referent``). Turn-mode extraction refuses to start
when it is empty, and maps each name, plus the generic forms "this person", "the person",
"the user" and "user", to the subject ``user``. List every form the extractor may emit, for
example a given name alone and the full name.

``detect_code_machine`` (default true) marks code and machine output inside the subject's
typed turns as pasted (``paste:code_or_machine``). Set it false for a subject whose code is
their own words, for example a developer whose way of coding is part of what the
specification should describe. docs/core/DATA_TREATMENT_POLICY.md lists every such switch.

``allowlist_own_writing_pasted`` re-classes a pasted segment the document segmenter moved
(``paste:document``) as ``own_typed`` when its typing-trait score reaches
``own_writing_min_traits`` (basis ``allowlist:own_writing_pasted``, with a ``practice`` tag;
``voice.OwnWritingRule``). Like every detector setting, it applies when a conversation is
written, so changing it takes effect on a fresh import.
"""
from __future__ import annotations

import fnmatch
import json
import os
import re
from dataclasses import dataclass, field
from pathlib import Path

from baselayer.voice import OWN_WRITING_MIN_TRAITS, OwnWritingRule, VoiceSettings

ENV_VAR = "BASELAYER_IMPORT_CONFIG"
# Injection canaries are config-only. A canary is the marker an operator's own
# context-injection hook writes at the head of what it injects; the importer flags
# a session whose hook-context attachment carries one. The package ships none: a
# default would publish one operator's private hook marker, and would silently
# assume every user runs that hook. Set `canary_strings` in the local import config.
DEFAULT_CANARIES: tuple = ()


def default_config_path() -> Path:
    from baselayer import config as _cfg
    return Path(_cfg.PROJECT_ROOT) / "data" / "import_config.json"


@dataclass
class ImportConfig:
    exclude_conversations: frozenset = frozenset()
    exclude_sources: frozenset = frozenset()
    exclude_path_globs: tuple = ()
    paste_allowlist: frozenset = frozenset()
    subject_names: tuple = ()
    meeting_subject_labels: tuple = ()
    harness_cwd_patterns: tuple = ()
    harness_template_roots: tuple = ()
    harness_template_exclude_dirs: tuple = ()
    extra_typos: frozenset = frozenset()
    typography_is_paste: bool = False
    # Queued prompts an older client wrote with no origin cannot be told apart from queued
    # notifications by any field, so they are excluded unless this is set (basis
    # recovered:queued_no_origin). Off by default; it is the subject's call.
    include_originless_queued: bool = False
    canary_strings: tuple = DEFAULT_CANARIES
    # Pasted documents that carry the subject's typing traits are the subject's own writing
    # (voice.OwnWritingRule). Off by default; the subject opts in.
    allowlist_own_writing_pasted: bool = False
    own_writing_min_traits: int = OWN_WRITING_MIN_TRAITS
    # Code and machine output inside typed turns is not the subject's words (on by
    # default). Off: it stays own and can be cited.
    detect_code_machine: bool = True
    path: str | None = None
    _cwd_res: list = field(default_factory=list, repr=False)

    def __post_init__(self):
        self._cwd_res = [re.compile(p, re.I) for p in self.harness_cwd_patterns]

    # -- exclusion ---------------------------------------------------------------
    def excluded_reason(self, conversation_id: str | None = None, source: str | None = None,
                        path: str | os.PathLike | None = None) -> str | None:
        """Why this conversation must not be imported, or None."""
        if source and source in self.exclude_sources:
            return f"source:{source}"
        if conversation_id and conversation_id in self.exclude_conversations:
            return "conversation_id"
        if path is not None and self.exclude_path_globs:
            p = str(path).replace("\\", "/")
            for g in self.exclude_path_globs:
                if fnmatch.fnmatch(p, g.replace("\\", "/")):
                    return f"path_glob:{g}"
        return None

    # -- harness -----------------------------------------------------------------
    def is_harness_cwd(self, cwd: str | None) -> bool:
        return bool(cwd) and any(r.search(cwd) for r in self._cwd_res)

    def voice_settings(self) -> VoiceSettings:
        return VoiceSettings(subject_names=tuple(self.subject_names),
                             extra_typos=frozenset(w.lower() for w in self.extra_typos),
                             typography_is_paste=self.typography_is_paste,
                             detect_code_machine=self.detect_code_machine)

    def own_writing_rule(self) -> OwnWritingRule | None:
        """The own-writing re-class rule, or None when the switch is off."""
        if not self.allowlist_own_writing_pasted:
            return None
        return OwnWritingRule(settings=self.voice_settings(), min_traits=self.own_writing_min_traits)

    def is_meeting_subject(self, label: str) -> bool:
        lab = (label or "").strip().lower()
        return any(lab == s.strip().lower() for s in self.meeting_subject_labels)


_LIST_KEYS = {
    "exclude_conversations": frozenset, "exclude_sources": frozenset,
    "exclude_path_globs": tuple, "paste_allowlist": frozenset, "subject_names": tuple,
    "meeting_subject_labels": tuple, "harness_cwd_patterns": tuple,
    "harness_template_roots": tuple, "harness_template_exclude_dirs": tuple,
    "extra_typos": frozenset, "canary_strings": tuple,
}


_BOOL_KEYS = ("typography_is_paste", "include_originless_queued", "allowlist_own_writing_pasted",
              "detect_code_machine")
_POSITIVE_INT_KEYS = ("own_writing_min_traits",)


def config_from_dict(d: dict, path: str | None = None) -> ImportConfig:
    unknown = set(d) - set(_LIST_KEYS) - set(_BOOL_KEYS) - set(_POSITIVE_INT_KEYS) - {"_comment"}
    if unknown:
        raise ValueError(f"import config: unknown keys {sorted(unknown)} (typo? an ignored "
                         f"exclusion key would import what it was meant to exclude)")
    kw = {}
    for k, typ in _LIST_KEYS.items():
        if k in d:
            v = d[k]
            if not isinstance(v, list) or not all(isinstance(x, str) for x in v):
                raise ValueError(f"import config: {k} must be a list of strings")
            kw[k] = typ(v)
    for k in _BOOL_KEYS:
        if k in d:
            if not isinstance(d[k], bool):
                raise ValueError(f"import config: {k} must be true or false")
            kw[k] = d[k]
    for k in _POSITIVE_INT_KEYS:
        if k in d:
            v = d[k]
            # bool is an int subclass in Python: reject it explicitly
            if isinstance(v, bool) or not isinstance(v, int) or v < 1:
                raise ValueError(f"import config: {k} must be a positive integer")
            kw[k] = v
    return ImportConfig(path=path, **kw)


def load_import_config(path: str | os.PathLike | None = None) -> ImportConfig:
    if path is None:
        env = os.environ.get(ENV_VAR)
        path = Path(env) if env else default_config_path()
        if env and not path.exists():
            raise FileNotFoundError(f"{ENV_VAR} points at a missing file: {path}")
    path = Path(path)
    if not path.exists():
        return ImportConfig()
    with open(path, encoding="utf-8") as f:
        d = json.load(f)
    if not isinstance(d, dict):
        raise ValueError(f"import config {path}: top level must be an object")
    return config_from_dict(d, str(path))
