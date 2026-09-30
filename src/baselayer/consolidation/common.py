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
