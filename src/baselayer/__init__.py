# Base Layer — Personal AI Memory System
# 4-step pipeline: Import → Extract → Author → Compose
# Extracts facts from conversation history and authors a compressed behavioral specification.

# Single source of truth: the version declared in pyproject.toml (read from the
# installed package metadata). The literal fallback is only used when running
# from a source tree with no installed dist-info; keep it in sync with pyproject.
from importlib.metadata import version as _pkg_version, PackageNotFoundError

try:
    __version__ = _pkg_version("baselayer")
except PackageNotFoundError:  # running from source without an install
    __version__ = "0.5.0"
