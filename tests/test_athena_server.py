"""Tests for servers/mcp_athena_server.py — chunked write, threshold, lifecycle, PII.

Tests core functions directly (not over MCP transport), driving the chunked
writer with a fake cursor so no live Athena connection is needed.
"""

import csv
from pathlib import Path

import pytest

import servers.mcp_athena_server as srv


class FakeCursor:
    """Minimal cursor: hands out rows in fetchmany batches."""

    def __init__(self, columns, rows):
        self.description = [(c,) for c in columns]
        self._rows = list(rows)
        self._pos = 0

    def fetchmany(self, n):
        batch = self._rows[self._pos:self._pos + n]
        self._pos += len(batch)
        return batch


def _read_csv(path):
    with open(path, newline="") as f:
        return list(csv.reader(f))


def test_write_result_csv_streams_all_rows_one_header(tmp_path):
    rows = [(i, f"v{i}") for i in range(12000)]  # > 2 chunks at CHUNK=5000
    cur = FakeCursor(["id", "val"], rows)
    out = tmp_path / "out.csv"

    total, redacted = srv._write_result_csv(cur, ["id", "val"], str(out))

    assert total == 12000
    assert redacted == []
    data = _read_csv(out)
    assert data[0] == ["id", "val"]        # exactly one header row
    assert len(data) == 12001              # header + 12000 data rows
    assert data[1] == ["0", "v0"]
    assert data[-1] == ["11999", "v11999"]


def test_write_result_csv_zero_rows_writes_header_only(tmp_path):
    cur = FakeCursor(["id", "val"], [])
    out = tmp_path / "empty.csv"

    total, redacted = srv._write_result_csv(cur, ["id", "val"], str(out))

    assert total == 0
    data = _read_csv(out)
    assert data == [["id", "val"]]         # header only, no data rows


def test_write_result_csv_redacts_pii_columns(tmp_path):
    rows = [(1, "a@b.com", 99), (2, "c@d.com", 88)]
    cur = FakeCursor(["user_id", "email", "amount"], rows)
    out = tmp_path / "redacted.csv"

    total, redacted = srv._write_result_csv(
        cur, ["user_id", "email", "amount"], str(out)
    )

    assert total == 2
    assert "email" in redacted
    data = _read_csv(out)
    assert data[0] == ["user_id", "amount"]   # email column gone from header
    assert "a@b.com" not in [cell for r in data for cell in r]


def test_resolve_out_dir_empty_uses_session_cache(tmp_path, monkeypatch):
    monkeypatch.setenv("AI_ANALYST_WORKSPACE", str(tmp_path))
    monkeypatch.setenv("AI_ANALYST_SESSION_ID", "sess1")

    final, is_deliverable, warning = srv._resolve_out_dir("")

    assert is_deliverable is False
    assert warning is None
    assert ".query-cache" in str(final)
    assert "sess1" in str(final)


def test_resolve_out_dir_inside_workspace_is_deliverable(tmp_path, monkeypatch):
    monkeypatch.setenv("AI_ANALYST_WORKSPACE", str(tmp_path))
    target = tmp_path / "data" / "orders.csv"

    final, is_deliverable, warning = srv._resolve_out_dir(str(target))

    assert is_deliverable is True
    assert warning is None
    assert Path(final) == target


def test_resolve_out_dir_traversal_falls_back_to_cache(tmp_path, monkeypatch):
    monkeypatch.setenv("AI_ANALYST_WORKSPACE", str(tmp_path))
    monkeypatch.setenv("AI_ANALYST_SESSION_ID", "sess1")

    final, is_deliverable, warning = srv._resolve_out_dir("../../etc/evil.csv")

    assert is_deliverable is False
    assert warning is not None
    assert ".query-cache" in str(final)


def test_sweep_stale_cache_removes_old_keeps_fresh(tmp_path, monkeypatch):
    import os as _os, time as _time
    monkeypatch.setenv("AI_ANALYST_WORKSPACE", str(tmp_path))
    cache = tmp_path / ".query-cache"
    old = cache / "old_sess"
    fresh = cache / "fresh_sess"
    old.mkdir(parents=True)
    fresh.mkdir(parents=True)
    # Backdate the old dir past the 24h threshold
    stale = _time.time() - srv.STALE_SWEEP_SECONDS - 10
    _os.utime(old, (stale, stale))

    removed = srv._sweep_stale_cache()

    assert removed == 1
    assert not old.exists()
    assert fresh.exists()


def test_run_query_small_result_inlines_and_writes_file(tmp_path, monkeypatch):
    monkeypatch.setenv("AI_ANALYST_WORKSPACE", str(tmp_path))
    rows = [(i, i * 10) for i in range(10)]  # <= 50 -> inline
    cur = FakeCursor(["day", "orders"], rows)

    import json
    result = json.loads(srv._run_query(cur, ""))

    assert result["row_count"] == 10
    assert "data" in result and len(result["data"]) == 10   # inlined
    assert "file_path" in result                            # still written
    assert Path(result["file_path"]).exists()


def test_run_query_large_result_returns_handle_only(tmp_path, monkeypatch):
    monkeypatch.setenv("AI_ANALYST_WORKSPACE", str(tmp_path))
    rows = [(i, i * 10) for i in range(51)]  # > 50 -> handle only
    cur = FakeCursor(["day", "orders"], rows)

    import json
    result = json.loads(srv._run_query(cur, ""))

    assert result["row_count"] == 51
    assert "data" not in result                 # NOT inlined
    assert len(result["preview"]) == srv.PREVIEW_ROWS
    assert result["columns"] == ["day", "orders"]
    assert Path(result["file_path"]).exists()


def test_query_athena_blocks_pii_select(monkeypatch):
    import json
    out = json.loads(srv.query_athena("SELECT email FROM users"))
    assert "error" in out
    assert out["blocked_columns"]


def test_run_query_deliverable_path_is_kept(tmp_path, monkeypatch):
    monkeypatch.setenv("AI_ANALYST_WORKSPACE", str(tmp_path))
    rows = [(i, i) for i in range(60)]
    cur = FakeCursor(["a", "b"], rows)
    target = tmp_path / "data" / "deliverable.csv"

    import json
    result = json.loads(srv._run_query(cur, str(target)))

    assert result["is_deliverable"] is True
    assert Path(result["file_path"]) == target
    assert target.exists()


class FakeS3:
    """Minimal S3 client: download_file writes recorded bytes to the dest path.
    Optionally fails partway to model an interrupted download."""

    def __init__(self, payload: bytes, fail=False):
        self._payload = payload
        self._fail = fail
        self.calls = []

    def download_file(self, Bucket, Key, Filename):
        self.calls.append((Bucket, Key, Filename))
        if self._fail:
            # Write a partial chunk to the staging path, then blow up.
            with open(Filename, "wb") as f:
                f.write(self._payload[: len(self._payload) // 2])
            raise ConnectionError("S3 download interrupted")
        with open(Filename, "wb") as f:
            f.write(self._payload)


def test_deliver_from_s3_copies_result_to_out_path(tmp_path):
    payload = b"id,val\n1,a\n2,b\n"
    s3 = FakeS3(payload)
    out = tmp_path / "data" / "deliverable.csv"

    srv._deliver_from_s3(
        "s3://org-bucket/athena-output/abc123.csv", str(out), s3_client=s3
    )

    assert out.exists()
    assert out.read_bytes() == payload
    # Parsed the s3 uri into bucket/key correctly.
    bucket, key, _ = s3.calls[0]
    assert bucket == "org-bucket"
    assert key == "athena-output/abc123.csv"


def test_deliver_from_s3_interrupted_leaves_no_final_file(tmp_path):
    s3 = FakeS3(b"id,val\n1,a\n2,b\n", fail=True)
    out = tmp_path / "deliverable.csv"

    with pytest.raises(Exception):
        srv._deliver_from_s3("s3://bucket/key.csv", str(out), s3_client=s3)

    # The bug we are killing: a partial file must NOT appear at the final path.
    assert not out.exists(), "interrupted download must not leave a file at out_path"


def test_strip_pii_from_select_removes_pii_columns():
    sql = "SELECT user_id, email, total_amount FROM orders WHERE day >= '2026-01-01'"
    cleaned, removed = srv._strip_pii_from_select(sql)
    assert "email" in removed
    assert "email" not in cleaned.lower().split("from")[0]
    assert "user_id" in cleaned and "total_amount" in cleaned


def test_run_query_write_failure_falls_back_to_inline(tmp_path, monkeypatch):
    monkeypatch.setenv("AI_ANALYST_WORKSPACE", str(tmp_path))
    rows = [(i, i) for i in range(200)]   # large; would normally be handle-only
    cur = FakeCursor(["a", "b"], rows)

    # Force the CSV write to fail.
    def boom(*a, **k):
        raise OSError("disk full")
    monkeypatch.setattr(srv, "_write_result_csv", boom)

    import json
    result = json.loads(srv._run_query(cur, ""))

    assert "data" in result                       # degraded to inline
    assert len(result["data"]) == srv.INLINE_THRESHOLD
    assert "Could not write results" in result["notice"]


def test_workspace_root_falls_back_when_cwd_unwritable(tmp_path, monkeypatch):
    """Deployed MCP servers (Claude Desktop/Cowork) start with cwd='/' which is
    read-only; the workspace root must fall back to a writable directory."""
    import os as _os
    monkeypatch.delenv("AI_ANALYST_WORKSPACE", raising=False)
    ro = tmp_path / "readonly-cwd"
    ro.mkdir()
    ro.chmod(0o555)
    try:
        monkeypatch.setattr(srv.Path, "cwd", classmethod(lambda cls: ro))
        root = srv._workspace_root()
        assert root != ro.resolve()
        assert root.is_dir()
        assert _os.access(root, _os.W_OK)
    finally:
        ro.chmod(0o755)


def test_session_cache_dir_readonly_workspace_falls_back(tmp_path, monkeypatch):
    """Even with an unwritable workspace root, the session cache must land
    somewhere writable instead of raising Errno 30."""
    ro = tmp_path / "readonly-ws"
    ro.mkdir()
    ro.chmod(0o555)
    try:
        monkeypatch.setenv("AI_ANALYST_WORKSPACE", str(ro))
        monkeypatch.setenv("AI_ANALYST_SESSION_ID", "sess-ro")
        d = srv._session_cache_dir()
        assert d.is_dir()
        (d / "probe.csv").write_text("ok")  # must be writable
    finally:
        ro.chmod(0o755)


class FakeExecConn:
    """Minimal connection: records executed SQL, hands rows to any cursor."""

    def __init__(self, columns, rows):
        self.columns = columns
        self.rows = list(rows)
        self.executes = []
        self.connections = 0

    def cursor(self):
        conn = self

        class C:
            description = [(c,) for c in conn.columns]

            def __init__(self):
                self._pos = 0

            def execute(self, sql, *a, **k):
                conn.executes.append(sql)

            def fetchmany(self, n):
                batch = conn.rows[self._pos:self._pos + n]
                self._pos += len(batch)
                return batch

            def fetchall(self):
                return conn.rows

            def close(self):
                pass

        return C()

    def close(self):
        pass


@pytest.fixture
def cache_env(tmp_path, monkeypatch):
    monkeypatch.setenv("AI_ANALYST_WORKSPACE", str(tmp_path))
    monkeypatch.setenv("AI_ANALYST_SESSION_ID", "cache-sess")
    return tmp_path


def test_query_athena_identical_sql_served_from_cache(cache_env, monkeypatch):
    """The second run of the same SQL must not hit Athena: it returns the
    already-written CSV handle with cached=True."""
    import json
    conn = FakeExecConn(["day", "orders"], [("2026-01-01", 10), ("2026-01-02", 20)])
    monkeypatch.setattr(srv, "_get_connection", lambda: conn)
    sql = "SELECT day, COUNT(*) AS orders FROM t GROUP BY day"

    r1 = json.loads(srv.query_athena(sql))
    r2 = json.loads(srv.query_athena(sql))

    assert len(conn.executes) == 1, "identical SQL must not re-execute"
    assert r2.get("cached") is True
    assert r1.get("cached") is None or r1.get("cached") is False
    assert r2["file_path"] == r1["file_path"]
    assert r2["row_count"] == 2
    assert r2["columns"] == ["day", "orders"]
    assert "data" in r2  # small results stay inlined on cache hits too


def test_query_athena_cache_ignores_whitespace_differences(cache_env, monkeypatch):
    import json
    conn = FakeExecConn(["n"], [(1,)])
    monkeypatch.setattr(srv, "_get_connection", lambda: conn)

    json.loads(srv.query_athena("SELECT COUNT(*) AS n FROM t"))
    r2 = json.loads(srv.query_athena("SELECT   COUNT(*) AS n\n  FROM t ;"))

    assert len(conn.executes) == 1
    assert r2.get("cached") is True


def test_query_athena_refresh_bypasses_cache(cache_env, monkeypatch):
    import json
    conn = FakeExecConn(["n"], [(1,)])
    monkeypatch.setattr(srv, "_get_connection", lambda: conn)
    sql = "SELECT COUNT(*) AS n FROM t"

    json.loads(srv.query_athena(sql))
    r2 = json.loads(srv.query_athena(sql, refresh=True))

    assert len(conn.executes) == 2, "refresh=True must re-execute"
    assert r2.get("cached") is not True


def test_query_athena_cache_hit_copies_to_deliverable(cache_env, monkeypatch):
    """A cached result requested again with out_path must be copied to the
    deliverable path without re-querying Athena."""
    import json
    conn = FakeExecConn(["day", "orders"], [("2026-01-01", 10)])
    monkeypatch.setattr(srv, "_get_connection", lambda: conn)
    sql = "SELECT day, COUNT(*) AS orders FROM t GROUP BY day"

    json.loads(srv.query_athena(sql))
    r2 = json.loads(srv.query_athena(sql, out_path="data/orders.csv"))

    assert len(conn.executes) == 1
    assert r2.get("cached") is True
    assert r2["is_deliverable"] is True
    target = cache_env / "data" / "orders.csv"
    assert Path(r2["file_path"]) == target
    assert target.exists()


def test_describe_athena_table_batch_one_call(monkeypatch):
    """Describing several tables must run ONE information_schema query and
    return columns grouped per table."""
    import json
    rows = [
        ("orders", "order_id", "bigint"),
        ("orders", "amount", "double"),
        ("users", "user_id", "bigint"),
    ]
    conn = FakeExecConn(["table_name", "column_name", "data_type"], rows)
    monkeypatch.setattr(srv, "_get_connection", lambda: conn)

    out = json.loads(srv.describe_athena_table(tables=["orders", "users", "ghost"], database="db1"))

    assert len(conn.executes) == 1
    assert out["database"] == "db1"
    assert out["tables"]["orders"] == [
        {"name": "order_id", "type": "bigint"},
        {"name": "amount", "type": "double"},
    ]
    assert out["tables"]["users"] == [{"name": "user_id", "type": "bigint"}]
    assert out["missing"] == ["ghost"]


def test_describe_athena_table_single_keeps_legacy_shape(monkeypatch):
    import json
    rows = [("orders", "order_id", "bigint"), ("orders", "amount", "double")]
    conn = FakeExecConn(["table_name", "column_name", "data_type"], rows)
    monkeypatch.setattr(srv, "_get_connection", lambda: conn)

    out = json.loads(srv.describe_athena_table(table="orders", database="db1"))

    assert out["table"] == "orders"
    assert out["columns"] == [
        {"name": "order_id", "type": "bigint"},
        {"name": "amount", "type": "double"},
    ]


def test_resolve_out_dir_unwritable_deliverable_falls_back_to_cache(tmp_path, monkeypatch):
    """A deliverable path whose parent cannot be created must degrade to the
    session cache with a warning, not raise."""
    ro = tmp_path / "readonly-ws2"
    ro.mkdir()
    ro.chmod(0o555)
    try:
        monkeypatch.setenv("AI_ANALYST_WORKSPACE", str(ro))
        monkeypatch.setenv("AI_ANALYST_SESSION_ID", "sess-ro2")
        final, is_deliverable, warning = srv._resolve_out_dir("data/out.csv")
        assert is_deliverable is False
        assert warning is not None
        assert ".query-cache" in str(final)
    finally:
        ro.chmod(0o755)
