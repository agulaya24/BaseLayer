"""Shared plumbing for the consolidation stages: hashing, stamps, atomic writes, --out guard."""
from __future__ import annotations

import datetime as _dt
import hashlib
import json
import os
from pathlib import Path

from . import CONSOLIDATION_VERSION, STAMP_VERSION

PKG_DIR = Path(__file__).resolve().parent


# ---------------------------------------------------------------- hashing
def sha256_bytes(b: bytes) -> str:
    return hashlib.sha256(b).hexdigest()


def sha256_text(s: str) -> str:
    return sha256_bytes(s.encode("utf-8"))


def canonical(obj) -> str:
    return json.dumps(obj, sort_keys=True, ensure_ascii=False, separators=(",", ":"))


def payload_hash(obj: dict) -> str:
    """Hash of a stage output's content, without its stamp. Two runs that produce the
    same content hash the same, so a downstream inputs hash does not change with the
    upstream run id or timestamp."""
    if isinstance(obj, dict):
        obj = {k: v for k, v in obj.items() if k != "stamp"}
    return sha256_text(canonical(obj))


def code_sha256() -> str:
    """Content hash of every module in this package, sorted by name. Stable when git is
    dirty or absent, which the git commit is not."""
    h = hashlib.sha256()
    for p in sorted(PKG_DIR.glob("*.py")):
        h.update(p.name.encode("utf-8"))
        h.update(b"\0")
        h.update(p.read_bytes().replace(b"\r\n", b"\n"))
        h.update(b"\0")
    return h.hexdigest()


def git_stamp(code_file) -> dict:
    try:
        from baselayer.turn_contract import code_path_of, git_commit_of
        return {"git_commit": git_commit_of(code_file), "code_path": code_path_of(code_file)}
    except Exception:  # a missing git must not stop a run, but must be visible
        return {"git_commit": "unknown", "code_path": f"baselayer/consolidation/{Path(code_file).name}"}


def new_run_id(seed: str) -> str:
    now = _dt.datetime.now(_dt.timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    return f"{now}-{sha256_text(seed)[:8]}"


def make_stamp(stage: str, code_file, inputs: dict, params: dict, run_id: str) -> dict:
    """inputs: {name: sha256}. The inputs hash covers names and hashes, sorted."""
    inputs_hash = sha256_text(canonical(inputs))
    return {
        "stamp_version": STAMP_VERSION,
        "consolidation_version": CONSOLIDATION_VERSION,
        "stage": stage,
        "run_id": run_id,
        "created_at": _dt.datetime.now(_dt.timezone.utc).isoformat(timespec="seconds"),
        **git_stamp(code_file),
        "code_sha256": code_sha256(),
        "inputs": inputs,
        "inputs_hash": inputs_hash,
        "params": params,
        "model_calls": 0,
    }


# ---------------------------------------------------------------- IO
def write_text_atomic(path: Path, text: str) -> None:
    """LF line endings on every platform; temp file, size check, then os.replace. Never
    truncates the destination before the new content is safely on disk."""
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    data = text.encode("utf-8")
    tmp = path.with_name(path.name + ".tmp")
    with open(tmp, "wb") as f:
        f.write(data)
    if tmp.stat().st_size != len(data):
        raise OSError(f"short write to {tmp}")
    os.replace(tmp, path)


def write_json(path: Path, obj) -> None:
    write_text_atomic(path, json.dumps(obj, indent=1, ensure_ascii=False) + "\n")


def read_json(path: Path):
    return json.loads(Path(path).read_text(encoding="utf-8"))


def file_sha256(path: Path) -> str:
    return sha256_bytes(Path(path).read_bytes())


# ---------------------------------------------------------------- write guard
def _is_data_dir(d: Path) -> bool:
    return (d / "identity_layers").is_dir() or (d / "database" / "memory.db").exists()


def guard_out(out: Path, protected: list[Path]) -> None:
    """--out must not sit inside or above the spec dir or any input, and not inside any
    Base Layer data directory (one holding identity_layers/ or database/memory.db, e.g.
    the served memory_system/data). Same rule as verify-spec, kept separate on purpose."""
    out = Path(out).resolve()
    for p in protected:
        p = Path(p).resolve()
        if out == p or p in out.parents or out in p.parents:
            raise ValueError(f"--out {out} overlaps protected path {p}")
    for d in [out, *out.parents]:
        if _is_data_dir(d):
            raise ValueError(f"--out {out} is inside a Base Layer data directory {d}")
    try:
        from baselayer import config
        served = (Path(config.PROJECT_ROOT) / "data").resolve()
        if out == served or served in out.parents:
            raise ValueError(f"--out {out} is inside the served data directory {served}")
    except ImportError:
        pass


# ---------------------------------------------------------------- degraded (fallback) mode
TRIGGERS_FALLBACK = ("identity grouping: no --grouping file was supplied, so each distinct whole "
                     "Active_When condition is its own trigger (no clauses, no grouping)")
CATEGORIES_FALLBACK = ("one flat category: no --categories assignment was supplied, so every "
                       "trigger sits in a single category named Situations")
FLAT_METHOD = "none supplied: one flat category"


def degraded_reasons(triggers_doc: dict | None, categories_doc: dict | None) -> list[str]:
    """Why a consolidation is a fallback build, or [] when it is not.

    Package defaults stand in for the model-built inputs (`build group`, `build categorize`):
    identity triggers and one flat category. The checks verify structure, not content, so such a
    run passes every check; this is the flag that says it is not the briefed consolidation.
    Read from the explicit `fallback` field and, for output written before that field existed,
    from the markers it always carried (triggers `source`, categories `method`, stage params),
    so an older degraded run is not read as clean because a field is absent."""
    out = []
    t = triggers_doc or {}
    tparams = (t.get("stamp") or {}).get("params") or {}
    if t.get("fallback") or tparams.get("fallback") is True or t.get("source") == "identity" \
            or tparams.get("grouping") == "identity":
        out.append(t.get("fallback") or TRIGGERS_FALLBACK)
    c = categories_doc or {}
    cparams = (c.get("stamp") or {}).get("params") or {}
    if c.get("fallback") or cparams.get("fallback") is True or c.get("method") == FLAT_METHOD \
            or cparams.get("assignment") == "flat":
        out.append(c.get("fallback") or CATEGORIES_FALLBACK)
    return out


def degraded_line(reasons: list[str]) -> str:
    """The printed form. Never contains 'FAILED': a degraded run is flagged, not failed."""
    return "DEGRADED (package defaults, not the model-built inputs): " + "; ".join(reasons)
