import logging

from backupmanager.logging_setup import setup_logging


def test_setup_logging_writes_file_and_queue(tmp_path):
    sink = setup_logging(tmp_path, level=logging.DEBUG)

    log = logging.getLogger("test.logger")
    log.info("hallo backup")

    logfile = tmp_path / "backupmanager.log"
    assert logfile.exists()
    content = logfile.read_text(encoding="utf-8")
    assert "hallo backup" in content

    drained = sink.drain()
    assert any("hallo backup" in line for line in drained)
    assert sink.drain() == []  # zweimal drainen liefert leere Liste


def test_gui_log_queue_drops_oldest_when_full(tmp_path):
    sink = setup_logging(tmp_path, level=logging.INFO)
    log = logging.getLogger("test.cap")
    sink._queue.maxsize  # Sanity check vorhanden  # noqa: B018

    # Befülle weit über die Standardgröße hinaus — sollte nicht blockieren.
    for i in range(10_001):
        log.info("msg %d", i)

    drained = sink.drain()
    assert len(drained) <= 5000
    assert "msg 10000" in drained[-1]
