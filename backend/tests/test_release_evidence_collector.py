from __future__ import annotations

import importlib.util
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[2]
COLLECTOR_PATH = REPO_ROOT / "scripts" / "collect_release_evidence.py"
SPEC = importlib.util.spec_from_file_location("collect_release_evidence", COLLECTOR_PATH)
assert SPEC is not None and SPEC.loader is not None
collector = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(collector)


def test_backend_python_prefers_repo_environment(monkeypatch, tmp_path: Path):
    expected = tmp_path / "backend" / ".venv" / "bin" / "python"

    def fake_probe(executable: str):
        return executable == str(expected), "Python 3.12 ready"

    monkeypatch.setattr(collector, "_probe_backend_python", fake_probe)
    executable, detail = collector._resolve_backend_python(
        repo_root=tmp_path,
        environ={},
        current_executable="/usr/bin/python3",
    )

    assert executable == str(expected)
    assert detail == "Python 3.12 ready"


def test_backend_python_honors_explicit_environment(monkeypatch, tmp_path: Path):
    explicit = str(tmp_path / "release-python")
    attempts: list[str] = []

    def fake_probe(executable: str):
        attempts.append(executable)
        return True, "explicit environment ready"

    monkeypatch.setattr(collector, "_probe_backend_python", fake_probe)
    executable, _ = collector._resolve_backend_python(
        repo_root=tmp_path,
        environ={"RELEASE_BACKEND_PYTHON": explicit},
        current_executable="/usr/bin/python3",
    )

    assert executable == explicit
    assert attempts == [explicit]


def test_missing_command_is_recorded_as_failed_gate(tmp_path: Path):
    result = collector._run(
        name="missing_tool",
        command=[str(tmp_path / "does-not-exist")],
        cwd=tmp_path,
        output_dir=tmp_path,
    )

    assert result["status"] == "failed"
    assert result["exit_code"] == 127
    assert "FileNotFoundError" in (tmp_path / "missing_tool.log").read_text()
