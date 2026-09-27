"""Whether the authored specification predates a `baselayer forget`.

`forget` hides facts (soft-delete) and removes their vectors. It does not regenerate the
layers, the brief or the claim provenance built from those facts, so without a record the
MCP server keeps serving claims drawn from forgotten facts and nothing says so.

A successful forget writes a small marker beside the layers recording when it ran. A
specification file is STALE when its modification time is older than that record. Deriving
staleness from file times, rather than clearing the marker from one command, means that
regenerating the layers through any entry point (`author`, `run`, `pipeline`, or the
authoring module directly) clears the warning with no cleanup step to miss.
"""

import json
import os
import time
from pathlib import Path

MARKER_NAME = "stale_after_forget.json"


def marker_path(layers_dir):
    return Path(layers_dir) / MARKER_NAME


def record_forget(layers_dir, facts_forgotten, mode, now=None):
    """Record that `facts_forgotten` facts were hidden now. Cumulative across forgets.

    Written to a temp file and moved into place, so a failure cannot leave a truncated
    marker behind.
    """
    layers_dir = Path(layers_dir)
    layers_dir.mkdir(parents=True, exist_ok=True)
    path = marker_path(layers_dir)
    previous = read_marker(layers_dir) or {}
    data = {
        "forgotten_at": now if now is not None else time.time(),
        "facts_forgotten": int(previous.get("facts_forgotten", 0)) + int(facts_forgotten),
        "last_mode": mode,
        "note": ("Facts were hidden with `baselayer forget` after the specification files "
                 "older than forgotten_at were written. Those files may still carry claims "
                 "drawn from the hidden facts. Regenerate with `baselayer author --compose`."),
    }
    tmp = path.with_suffix(".json.tmp")
    tmp.write_text(json.dumps(data, indent=2), encoding="utf-8")
    os.replace(tmp, path)
    return path


def read_marker(layers_dir):
    path = marker_path(layers_dir)
    if not path.exists():
        return None
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        # An unreadable marker still means a forget happened; treat it as "now" so the
        # warning errs toward showing rather than silently disappearing.
        return {"forgotten_at": time.time(), "facts_forgotten": None}


def stale_files(files, layers_dir=None):
    """The existing files among `files` written before the last forget. [] if none.

    `layers_dir` defaults to the directory of the first file, which is where the layers
    and the marker live.
    """
    files = [Path(f) for f in files]
    if layers_dir is None:
        if not files:
            return []
        layers_dir = files[0].parent
    marker = read_marker(layers_dir)
    if not marker:
        return []
    cutoff = float(marker.get("forgotten_at") or 0)
    return [f for f in files if f.exists() and f.stat().st_mtime < cutoff]


def default_spec_files():
    """The authored specification files, read from config at call time (reload-safe)."""
    import baselayer.config as cfg
    return [cfg.ANCHORS_LAYER_FILE, cfg.CORE_LAYER_FILE, cfg.PREDICTIONS_LAYER_FILE,
            cfg.UNIFIED_BRIEF_FILE, cfg.UNIFIED_BRIEF_CITED_FILE, cfg.IDENTITY_MODEL_FILE]
