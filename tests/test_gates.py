"""
Pipeline Gate Tests — Phase 2 (S98 Refactor)

Tests that safety gates correctly block pipeline steps when prerequisites aren't met.
Gates added in S98 Phase 3A will activate the skipped tests.
"""

import sqlite3
import sys
import os
from pathlib import Path
from unittest.mock import patch

import pytest


class TestExtractionGate:
    """Extraction completeness gate — blocks author/compose if extraction incomplete."""

    def test_gate_blocks_on_no_facts(self, populated_db):
        """Author should be blocked if zero facts extracted."""
        conn, db_path = populated_db

        # Clear all facts and extraction log
        conn.execute("DELETE FROM memory_facts")
        conn.execute("DELETE FROM extraction_log")
        conn.commit()

        fact_count = conn.execute("SELECT COUNT(*) FROM memory_facts").fetchone()[0]
        assert fact_count == 0, "Should have zero facts"

        with patch("baselayer.config.DATABASE_FILE", db_path):
            from baselayer.cli import _check_extraction_complete
            with pytest.raises(SystemExit) as exc_info:
                _check_extraction_complete()
            assert exc_info.value.code == 1

    def test_gate_passes_when_facts_exist(self, populated_db):
        """Author should proceed if facts have been extracted."""
        conn, db_path = populated_db

        # populated_db has facts already
        fact_count = conn.execute("SELECT COUNT(*) FROM memory_facts WHERE superseded_by IS NULL").fetchone()[0]
        assert fact_count > 0, "populated_db should have facts"

        with patch("baselayer.config.DATABASE_FILE", db_path):
            from baselayer.cli import _check_extraction_complete
            _check_extraction_complete()  # Should NOT raise

    def test_gate_allows_override(self, populated_db):
        """BASELAYER_SKIP_EXTRACTION_GATE=1 should bypass the gate."""
        conn, db_path = populated_db

        conn.execute("DELETE FROM extraction_log")
        conn.commit()

        with patch("baselayer.config.DATABASE_FILE", db_path), \
             patch.dict(os.environ, {"BASELAYER_SKIP_EXTRACTION_GATE": "1"}):
            from baselayer.cli import _check_extraction_complete
            # Should NOT raise despite incomplete extraction
            _check_extraction_complete()


class TestFactFloorGate:
    """Multi-dimensional fact floor — blocks if insufficient identity-tier facts."""

    def test_blocks_on_low_identity_facts(self, populated_db):
        """Should block if <50 identity-tier behavioral/positional facts."""
        conn, db_path = populated_db
        # populated_db has only 4 facts — well below threshold
        with patch("baselayer.config.DATABASE_FILE", db_path):
            from baselayer.cli import _check_fact_floor
            with pytest.raises(SystemExit) as exc_info:
                _check_fact_floor()
            assert exc_info.value.code == 1

    def test_passes_on_sufficient_facts(self, temp_db):
        """Should pass if all dimensions meet threshold."""
        conn, db_path = temp_db
        import uuid

        # Insert 60 behavioral identity-tier facts with 20 distinct predicates from 10 sources
        predicates = [f"predicate_{i}" for i in range(20)]
        for i in range(60):
            fact_id = str(uuid.uuid4())
            pred = predicates[i % 20]
            src_conv = f"conv-{i % 10:03d}"
            conn.execute("""
                INSERT INTO memory_facts (id, fact_text, fact_type, knowledge_tier, predicate,
                    source_conversation_id, confidence, category)
                VALUES (?, ?, 'behavioral', 'identity', ?, ?, 0.8, 'value')
            """, (fact_id, f"test fact {i}", pred, src_conv))
        conn.commit()

        with patch("baselayer.config.DATABASE_FILE", db_path):
            from baselayer.cli import _check_fact_floor
            _check_fact_floor()  # Should NOT raise

    def test_allows_override(self, populated_db):
        """BASELAYER_SKIP_FACT_FLOOR=1 should bypass."""
        conn, db_path = populated_db
        with patch("baselayer.config.DATABASE_FILE", db_path), \
             patch.dict(os.environ, {"BASELAYER_SKIP_FACT_FLOOR": "1"}):
            from baselayer.cli import _check_fact_floor
            _check_fact_floor()  # Should NOT raise


class TestManifestGate:
    """Source fingerprint gate — blocks if source data unchanged."""

    def test_fingerprint_deterministic(self, tmp_path):
        """Same files should produce same fingerprint."""
        source_dir = tmp_path / "source"
        source_dir.mkdir()
        (source_dir / "file1.txt").write_text("content one")
        (source_dir / "file2.txt").write_text("content two")

        from baselayer.config import compute_source_fingerprint
        fp1 = compute_source_fingerprint(str(source_dir))
        fp2 = compute_source_fingerprint(str(source_dir))
        assert fp1 == fp2, "Same source should produce same fingerprint"

    def test_fingerprint_changes_on_new_file(self, tmp_path):
        """Adding a file should change the fingerprint."""
        source_dir = tmp_path / "source"
        source_dir.mkdir()
        (source_dir / "file1.txt").write_text("content one")

        from baselayer.config import compute_source_fingerprint
        fp1 = compute_source_fingerprint(str(source_dir))

        (source_dir / "file2.txt").write_text("content two")
        fp2 = compute_source_fingerprint(str(source_dir))
        assert fp1 != fp2, "New file should change fingerprint"

    def test_blocks_on_unchanged_source(self, temp_db):
        """Should block if fingerprint matches stored value."""
        conn, db_path = temp_db
        # Create subjects table and insert a subject with a known fingerprint
        conn.execute("""
            INSERT INTO subjects (id, name, status, source_fingerprint)
            VALUES ('test_subject', 'Test Subject', 'complete', 'abc123')
        """)
        conn.commit()

        with patch("baselayer.config.DATABASE_FILE", db_path), \
             patch("baselayer.config.compute_source_fingerprint", return_value="abc123"):
            from baselayer.cli import _check_manifest
            with pytest.raises(SystemExit):
                _check_manifest("test_subject", "/fake/source")

    def test_passes_on_changed_source(self, temp_db):
        """Should allow if fingerprint differs from stored value."""
        conn, db_path = temp_db
        conn.execute("""
            INSERT INTO subjects (id, name, status, source_fingerprint)
            VALUES ('test_subject', 'Test Subject', 'complete', 'abc123')
        """)
        conn.commit()

        with patch("baselayer.config.DATABASE_FILE", db_path), \
             patch("baselayer.config.compute_source_fingerprint", return_value="xyz789"):
            from baselayer.cli import _check_manifest
            _check_manifest("test_subject", "/fake/source")  # Should NOT raise


class TestConcurrencyLock:
    """Pipeline concurrency limit — max 2 simultaneous runs."""

    def test_lock_file_created(self, tmp_path):
        """Pipeline lock should create a lock file with PID."""
        with patch("baselayer.config.PROJECT_ROOT", tmp_path):
            from baselayer.cli import _check_pipeline_lock
            _check_pipeline_lock()
            lock_file = tmp_path / "data" / ".pipeline.lock"
            assert lock_file.exists(), "Lock file should be created"
            content = lock_file.read_text().strip()
            assert str(os.getpid()) in content

    def test_blocks_on_third_pipeline(self, tmp_path):
        """Should block if 2 PIDs already running."""
        lock_file = tmp_path / "data" / ".pipeline.lock"
        lock_file.parent.mkdir(parents=True, exist_ok=True)
        # Write 2 fake PIDs that are "alive" (use current PID twice as trick)
        lock_file.write_text(f"{os.getpid()}\n{os.getpid()}")

        with patch("baselayer.config.PROJECT_ROOT", tmp_path):
            from baselayer.cli import _check_pipeline_lock
            with pytest.raises(SystemExit) as exc_info:
                _check_pipeline_lock()
            assert exc_info.value.code == 1


class TestSnapshotBeforeClear:
    """V2 snapshot — backs up DB + vectors before extraction reset."""

    def test_snapshot_creates_backup(self, tmp_path):
        """Snapshot should copy database to .snapshot/ directory."""
        # Create a fake DB
        db_dir = tmp_path / "data" / "database"
        db_dir.mkdir(parents=True)
        (db_dir / "memory.db").write_text("fake db content")

        from baselayer.cli import _snapshot_before_clear
        snapshot_dir = _snapshot_before_clear(memory_dir=str(tmp_path))

        assert snapshot_dir.exists()
        assert (snapshot_dir / "memory.db").exists()
        assert (snapshot_dir / "memory.db").read_text() == "fake db content"
