from pathlib import Path

from app.latest_pointer import list_recent_archive_runs, read_latest_run_folder_rel


def test_read_latest_run_folder_rel_resolves_relative(tmp_path: Path):
    root = tmp_path
    run_dir = root / "logs" / "archive_run_test"
    run_dir.mkdir(parents=True)
    ptr = root / "logs" / "latest_run.txt"
    ptr.parent.mkdir(parents=True, exist_ok=True)
    ptr.write_text("logs/archive_run_test", encoding="utf-8")
    rel = read_latest_run_folder_rel(root, "watch_later")
    assert rel == "logs/archive_run_test"


def test_read_latest_run_folder_rel_absolute_under_root(tmp_path: Path):
    root = tmp_path.resolve()
    run_dir = root / "logs" / "archive_run_abs"
    run_dir.mkdir(parents=True)
    ptr = root / "logs" / "latest_run_channel.txt"
    ptr.write_text(str(run_dir), encoding="utf-8")
    rel = read_latest_run_folder_rel(root, "channels")
    assert rel == "logs/archive_run_abs"


def test_read_latest_missing_returns_none(tmp_path: Path):
    assert read_latest_run_folder_rel(tmp_path, "videos") is None


def test_list_recent_archive_runs(tmp_path: Path):
    root = tmp_path
    logs = root / "logs"
    logs.mkdir()
    (logs / "archive_run_b").mkdir()
    (logs / "archive_run_a").mkdir()
    (logs / "not_run").mkdir()
    names = list_recent_archive_runs(root, limit=10)
    assert "archive_run_b" in names and "archive_run_a" in names
    assert "not_run" not in names
    assert names[0] == "archive_run_b"
