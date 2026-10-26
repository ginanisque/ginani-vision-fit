from uuid import uuid4

import pytest

from app import capture_store


class QueryResult:
    def __init__(self, row=None, rows=None, rowcount=0):
        self.row = row
        self.rows = rows or []
        self.rowcount = rowcount

    def fetchone(self):
        return self.row

    def fetchall(self):
        return self.rows


class FakeConnection:
    def __init__(self, events):
        self.events = events

    def __enter__(self):
        return self

    def __exit__(self, *_args):
        return False

    def execute(self, query, _params):
        normalized = " ".join(query.split())
        self.events.append(normalized)
        if normalized.startswith("select id from capture_sessions"):
            return QueryResult(row={"id": "session-1"})
        if normalized.startswith("select storage_key from capture_assets"):
            return QueryResult(rows=[{"storage_key": "private/object-1"}])
        if normalized.startswith("delete from measurement_tables"):
            return QueryResult(rowcount=2)
        if normalized.startswith("delete from capture_sessions"):
            return QueryResult(row={"id": "session-1"})
        raise AssertionError(f"Unexpected SQL: {normalized}")


def test_session_deletion_removes_objects_before_database_rows(monkeypatch):
    events = []
    monkeypatch.setattr(capture_store, "connection", lambda: FakeConnection(events))
    monkeypatch.setattr(
        capture_store, "delete_private",
        lambda key: events.append(f"delete-object:{key}"),
    )

    result = capture_store.delete_capture_session("session-1", owner_id=uuid4())

    assert result == {"assetsDeleted": 1, "measurementTablesDeleted": 2}
    assert events[2] == "delete-object:private/object-1"
    assert events[3].startswith("delete from measurement_tables")
    assert events[4].startswith("delete from capture_sessions")


def test_failed_object_deletion_preserves_database_rows(monkeypatch):
    events = []
    monkeypatch.setattr(capture_store, "connection", lambda: FakeConnection(events))

    def fail_delete(_key):
        raise RuntimeError("storage unavailable")

    monkeypatch.setattr(capture_store, "delete_private", fail_delete)
    with pytest.raises(RuntimeError, match="storage unavailable"):
        capture_store.delete_capture_session("session-1", owner_id=uuid4())

    assert not any(event.startswith("delete from ") for event in events)
