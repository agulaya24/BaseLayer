"""Every stage stamps the working-tree state the same way.

Found 2026-10-05: the extraction stamp read `<sha>-dirty` and the layer stamps read plain
`<sha>` for the same tree. `git_commit_of` ran `git status -- .` from the CODE FILE'S OWN
DIRECTORY, so `extract_facts.py` (src/baselayer/) saw the uncommitted cli.py and the untracked
consolidation/serve.py, while a stamp written from src/baselayer/distillation/ saw neither.
The commit names the whole tree, so "-dirty" must describe the whole tree, from any stage.

Built in a throwaway git repository under tmp_path; nothing touches this checkout.
"""
import shutil
import subprocess

import pytest

from baselayer import turn_contract as tc

pytestmark = pytest.mark.skipif(shutil.which("git") is None, reason="needs git")


def _git(repo, *args):
    return subprocess.run(["git", "-c", "user.name=t", "-c", "user.email=t@example.invalid",
                           "-c", "commit.gpgsign=false", "-c", "core.hooksPath=/dev/null",
                           "-C", str(repo), *args],
                          capture_output=True, text=True, check=True).stdout.strip()


@pytest.fixture
def repo(tmp_path):
    r = tmp_path / "repo"
    pkg = r / "src" / "pkg"
    for rel in ("extract.py", "cli.py", "distillation/author.py", "verification/run.py"):
        p = pkg / rel
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text("x = 1\n", encoding="utf-8")
    (r / "README.md").write_text("synthetic\n", encoding="utf-8")
    _git(r, "init", "-q")
    _git(r, "add", "-A")
    _git(r, "commit", "-q", "-m", "init")
    return r


def _stage_files(repo):
    pkg = repo / "src" / "pkg"
    return {"extraction": pkg / "extract.py", "distillation": pkg / "distillation" / "author.py",
            "verification": pkg / "verification" / "run.py"}


def test_clean_tree_every_stage_stamps_the_plain_head(repo):
    head = _git(repo, "rev-parse", "HEAD")
    stamps = {k: tc.git_commit_of(f) for k, f in _stage_files(repo).items()}
    assert set(stamps.values()) == {head}, stamps


@pytest.mark.parametrize("dirty", [
    "modified sibling in the package root (cli.py, as on 10/5)",
    "untracked file in another subpackage (consolidation/serve.py, as on 10/5)",
    "modified file outside the package (README.md)",
])
def test_dirty_tree_every_stage_stamps_dirty(repo, dirty):
    head = _git(repo, "rev-parse", "HEAD")
    pkg = repo / "src" / "pkg"
    if dirty.startswith("modified sibling"):
        (pkg / "cli.py").write_text("x = 2\n", encoding="utf-8")
    elif dirty.startswith("untracked"):
        (pkg / "consolidation").mkdir()
        (pkg / "consolidation" / "serve.py").write_text("y = 1\n", encoding="utf-8")
    else:
        (repo / "README.md").write_text("changed\n", encoding="utf-8")
    stamps = {k: tc.git_commit_of(f) for k, f in _stage_files(repo).items()}
    assert set(stamps.values()) == {head + "-dirty"}, stamps
    # the artifact stamp (layers, packages, trees) and the extraction stamp agree
    a = tc.artifact_stamp("layer", code_file=_stage_files(repo)["distillation"])
    e = tc.extraction_stamp("m", "h", code_file=_stage_files(repo)["extraction"])
    assert a["git_commit"] == e["git_commit"] == head + "-dirty"


def test_verification_stamp_uses_the_same_tree_state(repo):
    from baselayer.verification import run as vrun
    head = _git(repo, "rev-parse", "HEAD")
    (repo / "src" / "pkg" / "cli.py").write_text("x = 3\n", encoding="utf-8")
    st = vrun._git_stamp(_stage_files(repo)["verification"])
    assert st["git_commit"] == head and st["code_dirty"] is True
