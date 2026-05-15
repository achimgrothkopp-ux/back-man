import json

from backman.engine.progress import ProgressEvent, SummaryEvent, parse_progress_lines


def _line(**payload) -> str:
    return json.dumps(payload)


def test_parses_status_event():
    line = _line(
        message_type="status",
        percent_done=0.42,
        total_files=10,
        files_done=4,
        total_bytes=1000,
        bytes_done=420,
        seconds_elapsed=2.5,
        current_files=["/a", "/b"],
    )
    events = list(parse_progress_lines([line]))
    assert len(events) == 1
    ev = events[0]
    assert isinstance(ev, ProgressEvent)
    assert ev.percent_done == 0.42
    assert ev.files_done == 4
    assert ev.bytes_done == 420
    assert ev.current_files == ("/a", "/b")


def test_parses_summary_event():
    line = _line(
        message_type="summary",
        snapshot_id="abc123",
        files_new=3,
        files_changed=1,
        files_unmodified=5,
        data_added=2048,
        total_bytes_processed=4096,
        total_duration=1.23,
    )
    events = list(parse_progress_lines([line]))
    assert len(events) == 1
    ev = events[0]
    assert isinstance(ev, SummaryEvent)
    assert ev.snapshot_id == "abc123"
    assert ev.files_new == 3
    assert ev.data_added == 2048


def test_ignores_unknown_types_and_blank():
    lines = [
        "",
        _line(message_type="verbose_status", action="modified", item="/x"),
        _line(message_type="error", error="boom"),
        "not json at all",
    ]
    assert list(parse_progress_lines(lines)) == []


def test_status_event_with_defaults():
    line = _line(message_type="status")
    events = list(parse_progress_lines([line]))
    ev = events[0]
    assert ev.percent_done == 0.0
    assert ev.total_files == 0
    assert ev.current_files == ()
