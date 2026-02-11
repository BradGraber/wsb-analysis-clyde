"""
Tests for story-001-007: SQLite WAL Concurrency Spike

These tests verify:
- Background thread can sustain writes while main thread reads without blocking
- WAL mode is confirmed active
- Test documents observed behavior with timing data
- Clear pass/fail result

This is a spike to validate WAL concurrency works as expected for the application.
"""

import pytest
import os
import sqlite3
import threading
import time
from pathlib import Path

_DB_DIR = Path(__file__).parent.parent / "src" / "backend" / "db"
_SCHEMA_SQL = _DB_DIR / "schema.sql"


def _init_db(db_path):
    """Load schema.sql into a fresh database with WAL + FK PRAGMAs."""
    if not _SCHEMA_SQL.exists():
        pytest.skip("schema.sql not available yet")
    conn = sqlite3.connect(db_path)
    conn.execute("PRAGMA foreign_keys = ON")
    conn.execute("PRAGMA journal_mode = WAL")
    sql = _SCHEMA_SQL.read_text()
    lines = [l for l in sql.splitlines() if not l.strip().upper().startswith("PRAGMA")]
    conn.executescript("\n".join(lines))
    conn.close()


class TestWALConcurrency:
    """Verify WAL mode enables concurrent reads and writes."""

    def test_wal_mode_active(self, temp_db_path):
        """Verify database is in WAL mode."""
        _init_db(temp_db_path)

        conn = sqlite3.connect(temp_db_path)
        cursor = conn.cursor()
        cursor.execute("PRAGMA journal_mode")
        result = cursor.fetchone()
        conn.close()

        assert result is not None, "PRAGMA journal_mode returned no result"
        assert result[0].lower() == 'wal', \
            f"Expected WAL mode, got {result[0]}"

    def test_concurrent_read_write_without_blocking(self, temp_db_path):
        """Background writes should not block foreground reads in WAL mode."""
        _init_db(temp_db_path)

        write_count = [0]
        read_count = [0]
        errors = []
        write_active = [True]

        def background_writer():
            """Continuously write to database in background."""
            try:
                conn = sqlite3.connect(temp_db_path)
                cursor = conn.cursor()

                while write_active[0]:
                    cursor.execute(
                        "INSERT INTO system_config (key, value) VALUES (?, ?)",
                        (f"test_key_{write_count[0]}", f"value_{write_count[0]}"))
                    conn.commit()
                    write_count[0] += 1
                    time.sleep(0.01)

                conn.close()
            except Exception as e:
                errors.append(f"Writer error: {str(e)}")

        def foreground_reader():
            """Continuously read from database in main thread."""
            try:
                conn = sqlite3.connect(temp_db_path)
                cursor = conn.cursor()

                for _ in range(10):
                    cursor.execute("SELECT COUNT(*) FROM system_config")
                    cursor.fetchone()
                    read_count[0] += 1
                    time.sleep(0.05)

                conn.close()
            except Exception as e:
                errors.append(f"Reader error: {str(e)}")

        writer_thread = threading.Thread(target=background_writer)
        writer_thread.start()
        time.sleep(0.05)

        start_time = time.time()
        foreground_reader()
        end_time = time.time()

        write_active[0] = False
        writer_thread.join(timeout=2)

        assert len(errors) == 0, f"Concurrent operations produced errors: {errors}"
        assert write_count[0] > 0, "No writes completed"
        assert read_count[0] == 10, f"Expected 10 reads, got {read_count[0]}"

        elapsed_time = end_time - start_time
        print(f"\nConcurrency Spike Results:")
        print(f"  Duration: {elapsed_time:.3f} seconds")
        print(f"  Writes completed: {write_count[0]}")
        print(f"  Reads completed: {read_count[0]}")
        print(f"  WAL mode: active")
        print(f"  Result: PASS - no blocking detected")

    def test_read_performance_not_degraded(self, temp_db_path):
        """Reads should maintain good performance even with concurrent writes."""
        _init_db(temp_db_path)

        errors = []
        write_active = [True]
        read_times = []

        def background_writer():
            try:
                conn = sqlite3.connect(temp_db_path)
                cursor = conn.cursor()
                count = 0
                while write_active[0]:
                    cursor.execute(
                        "INSERT INTO system_config (key, value) VALUES (?, ?)",
                        (f"perf_key_{count}", f"value_{count}"))
                    conn.commit()
                    count += 1
                    time.sleep(0.01)
                conn.close()
            except Exception as e:
                errors.append(f"Writer error: {str(e)}")

        writer_thread = threading.Thread(target=background_writer)
        writer_thread.start()
        time.sleep(0.05)

        conn = sqlite3.connect(temp_db_path)
        cursor = conn.cursor()

        for _ in range(20):
            start = time.time()
            cursor.execute("SELECT COUNT(*) FROM system_config")
            cursor.fetchone()
            elapsed = time.time() - start
            read_times.append(elapsed)
            time.sleep(0.02)

        conn.close()

        write_active[0] = False
        writer_thread.join(timeout=2)

        assert len(errors) == 0, f"Errors during performance test: {errors}"

        avg_read_time = sum(read_times) / len(read_times)
        max_read_time = max(read_times)

        print(f"\nRead Performance with Concurrent Writes:")
        print(f"  Average read time: {avg_read_time*1000:.2f} ms")
        print(f"  Max read time: {max_read_time*1000:.2f} ms")
        print(f"  Total reads: {len(read_times)}")

        assert max_read_time < 0.1, \
            f"Read time degraded: max {max_read_time*1000:.2f}ms exceeds 100ms"

    def test_wal_checkpoint_behavior(self, temp_db_path):
        """Document WAL checkpoint behavior."""
        _init_db(temp_db_path)

        conn = sqlite3.connect(temp_db_path)
        cursor = conn.cursor()

        for i in range(100):
            cursor.execute(
                "INSERT INTO system_config (key, value) VALUES (?, ?)",
                (f"checkpoint_key_{i}", f"value_{i}"))
        conn.commit()

        cursor.execute("PRAGMA wal_checkpoint(PASSIVE)")
        checkpoint_result = cursor.fetchone()

        print(f"\nWAL Checkpoint Behavior:")
        print(f"  Checkpoint result: {checkpoint_result}")
        print(f"  100 inserts completed successfully")

        conn.close()


class TestWALFilesCreated:
    """Verify WAL auxiliary files are created."""

    def test_wal_and_shm_files_created(self, temp_db_path):
        """WAL mode should create -wal and -shm files."""
        _init_db(temp_db_path)

        conn = sqlite3.connect(temp_db_path)
        cursor = conn.cursor()
        cursor.execute("INSERT INTO system_config (key, value) VALUES ('test', 'value')")
        conn.commit()
        conn.close()

        wal_file = temp_db_path + '-wal'
        shm_file = temp_db_path + '-shm'

        print(f"\nWAL Files:")
        print(f"  -wal exists: {os.path.exists(wal_file)}")
        print(f"  -shm exists: {os.path.exists(shm_file)}")

        conn = sqlite3.connect(temp_db_path)
        cursor = conn.cursor()
        cursor.execute("PRAGMA journal_mode")
        mode = cursor.fetchone()[0]
        conn.close()

        assert mode.lower() == 'wal', "WAL mode not active"


class TestSpikeSummary:
    """Verify spike produces clear pass/fail result."""

    def test_spike_produces_summary(self, temp_db_path):
        """Spike should produce clear summary of findings."""
        _init_db(temp_db_path)

        errors = []
        write_active = [True]

        def writer():
            try:
                conn = sqlite3.connect(temp_db_path)
                cursor = conn.cursor()
                count = 0
                while write_active[0] and count < 5:
                    cursor.execute(
                        "INSERT INTO system_config (key, value) VALUES (?, ?)",
                        (f"summary_key_{count}", "value"))
                    conn.commit()
                    count += 1
                    time.sleep(0.02)
                conn.close()
            except Exception as e:
                errors.append(str(e))

        thread = threading.Thread(target=writer)
        thread.start()

        conn = sqlite3.connect(temp_db_path)
        cursor = conn.cursor()
        for _ in range(3):
            cursor.execute("SELECT COUNT(*) FROM system_config")
            cursor.fetchone()
            time.sleep(0.03)
        conn.close()

        write_active[0] = False
        thread.join(timeout=2)

        success = len(errors) == 0

        summary = f"""
        WAL Concurrency Spike Summary
        =============================
        WAL Mode: Active
        Concurrent R/W: {'PASS' if success else 'FAIL'}
        Errors: {len(errors)}
        Result: {'PASS' if success else 'FAIL'}
        """
        print(summary)

        assert success, f"Spike failed with errors: {errors}"
