from __future__ import annotations

import argparse
import json
import os
import shutil
import socket
import ssl
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import urlparse
from urllib.request import urlopen


REPO_ROOT = Path(__file__).resolve().parents[1]
BACKEND_REQUIRED_MODULES = (
    "fastapi",
    "lightgbm",
    "pandas",
    "pytest",
    "scipy",
    "sklearn",
    "sqlalchemy",
)


def _timestamp() -> str:
    return datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")


def _write_json(path: Path, payload: object) -> None:
    path.write_text(
        json.dumps(payload, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )


def _run(
    *,
    name: str,
    command: list[str],
    cwd: Path,
    output_dir: Path,
    env: dict[str, str] | None = None,
) -> dict:
    started = datetime.now(timezone.utc)
    try:
        completed = subprocess.run(
            command,
            cwd=cwd,
            env={**os.environ, **(env or {})},
            text=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            check=False,
        )
        output = completed.stdout
        return_code = completed.returncode
    except OSError as exc:
        output = f"{type(exc).__name__}: {exc}\n"
        return_code = 127
    finished = datetime.now(timezone.utc)
    log_path = output_dir / f"{name}.log"
    log_path.write_text(output, encoding="utf-8")
    return {
        "name": name,
        "command": command,
        "cwd": str(cwd),
        "started_at": started.isoformat(),
        "finished_at": finished.isoformat(),
        "duration_seconds": round((finished - started).total_seconds(), 3),
        "exit_code": return_code,
        "status": "passed" if return_code == 0 else "failed",
        "log": log_path.name,
    }


def _probe_backend_python(executable: str) -> tuple[bool, str]:
    imports = ", ".join(repr(module) for module in BACKEND_REQUIRED_MODULES)
    probe = (
        "import importlib, sys; "
        "assert sys.version_info[:2] == (3, 12), "
        "f'expected Python 3.12, got {sys.version.split()[0]}'; "
        f"[importlib.import_module(name) for name in ({imports},)]; "
        "print(sys.executable); print(sys.version.split()[0])"
    )
    try:
        completed = subprocess.run(
            [executable, "-c", probe],
            text=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            check=False,
        )
    except OSError as exc:
        return False, f"{type(exc).__name__}: {exc}"
    return completed.returncode == 0, completed.stdout.strip()


def _resolve_backend_python(
    *,
    repo_root: Path = REPO_ROOT,
    environ: dict[str, str] | None = None,
    current_executable: str = sys.executable,
) -> tuple[str, str]:
    environment = os.environ if environ is None else environ
    explicit = environment.get("RELEASE_BACKEND_PYTHON")
    if explicit:
        candidates = [explicit]
    else:
        venv_binary = Path("Scripts/python.exe") if os.name == "nt" else Path("bin/python")
        candidates = [
            str(repo_root / "backend" / ".venv" / venv_binary),
            str(repo_root / "backend" / "venv" / venv_binary),
            str(repo_root / ".venv" / venv_binary),
            str(repo_root / "venv" / venv_binary),
            current_executable,
        ]
        python312 = shutil.which("python3.12")
        if python312:
            candidates.append(python312)

    diagnostics: list[str] = []
    seen: set[str] = set()
    for candidate in candidates:
        normalized = str(Path(candidate).expanduser())
        if normalized in seen:
            continue
        seen.add(normalized)
        passed, detail = _probe_backend_python(normalized)
        if passed:
            return normalized, detail
        diagnostics.append(f"- {normalized}: {detail or 'probe failed'}")

    attempted = "\n".join(diagnostics)
    raise RuntimeError(
        "No usable RestockIQ backend Python environment was found. The release "
        "gates require Python 3.12 with backend/requirements.txt installed.\n"
        "Create it with:\n"
        "  cd backend\n"
        "  python3.12 -m venv .venv\n"
        "  .venv/bin/python -m pip install -r requirements.txt\n"
        "Or set RELEASE_BACKEND_PYTHON to that interpreter.\n"
        f"Attempted interpreters:\n{attempted}"
    )


def _write_preflight_failure(
    *,
    output_dir: Path,
    metadata: dict,
    failure: str,
    log_name: str,
    detail: str,
) -> None:
    (output_dir / log_name).write_text(detail.rstrip() + "\n", encoding="utf-8")
    _write_json(output_dir / "metadata.json", metadata)
    _write_json(
        output_dir / "https.json",
        {"status": "not_run", "reason": "Source preflight did not pass."},
    )
    _write_json(
        output_dir / "summary.json",
        {
            "status": "failed",
            "failures": [failure],
            "commands": [],
            "https": {"status": "not_run"},
        },
    )


def _git_value(*args: str) -> str:
    return subprocess.check_output(
        ["git", *args],
        cwd=REPO_ROOT,
        text=True,
    ).strip()


def _https_evidence(base_url: str) -> dict:
    parsed = urlparse(base_url)
    if parsed.scheme != "https":
        return {
            "status": "not_applicable",
            "reason": "Base URL is not HTTPS.",
            "base_url": base_url,
        }

    hostname = parsed.hostname
    if hostname is None:
        raise ValueError(f"HTTPS hostname tidak valid: {base_url}")
    port = parsed.port or 443
    context = ssl.create_default_context()
    with socket.create_connection((hostname, port), timeout=15) as raw_socket:
        with context.wrap_socket(raw_socket, server_hostname=hostname) as tls_socket:
            certificate = tls_socket.getpeercert()
            tls = {
                "status": "passed",
                "base_url": base_url,
                "hostname": hostname,
                "port": port,
                "tls_version": tls_socket.version(),
                "cipher": tls_socket.cipher(),
                "certificate_subject": certificate.get("subject"),
                "certificate_issuer": certificate.get("issuer"),
                "certificate_not_before": certificate.get("notBefore"),
                "certificate_not_after": certificate.get("notAfter"),
                "subject_alt_names": certificate.get("subjectAltName"),
            }

    with urlopen(f"{base_url.rstrip('/')}/health/ready", timeout=15) as response:
        tls["readiness_status"] = response.status
        tls["readiness_body"] = response.read().decode(errors="replace")
    return tls


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Collect a deterministic RestockIQ release-candidate evidence pack."
    )
    parser.add_argument(
        "--base-url",
        default=os.getenv("RESTOCKIQ_BASE_URL", "http://localhost"),
    )
    parser.add_argument("--output-dir", type=Path)
    parser.add_argument("--skip-docker", action="store_true")
    parser.add_argument("--skip-browser", action="store_true")
    parser.add_argument(
        "--allow-http",
        action="store_true",
        help="Allow a non-HTTPS base URL for a non-certifying local rehearsal.",
    )
    args = parser.parse_args()

    output_dir = (
        args.output_dir
        if args.output_dir is not None
        else REPO_ROOT.parent
        / "RestockIQ_evidence"
        / f"restockiq-rc-{_timestamp()}"
    ).resolve()
    output_dir.mkdir(parents=True, exist_ok=False)

    source_status = subprocess.check_output(
        ["git", "status", "--porcelain"],
        cwd=REPO_ROOT,
        text=True,
    )
    metadata = {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "base_url": args.base_url,
        "git_commit": _git_value("rev-parse", "HEAD"),
        "git_branch": _git_value("branch", "--show-current"),
        "git_describe": _git_value("describe", "--always", "--dirty"),
        "python": sys.version,
        "skip_docker": args.skip_docker,
        "skip_browser": args.skip_browser,
        "allow_http": args.allow_http,
        "source_clean": not bool(source_status.strip()),
    }

    if not metadata["source_clean"]:
        _write_preflight_failure(
            output_dir=output_dir,
            metadata=metadata,
            failure="source_worktree_dirty",
            log_name="00_source_preflight.log",
            detail=(
                "Release evidence requires a clean tracked and untracked source tree.\n"
                "Move generated patches/evidence outside the repository and commit or "
                f"revert source changes before rerunning.\n\n{source_status}"
            ),
        )
        print(f"Evidence directory: {output_dir}")
        print("Evidence status: failed")
        print("Failed gate: source_worktree_dirty")
        print(source_status.rstrip())
        return 1

    try:
        backend_python, backend_python_probe = _resolve_backend_python()
    except RuntimeError as exc:
        metadata["backend_python"] = None
        metadata["backend_python_probe"] = None
        metadata["backend_python_error"] = str(exc)
        _write_preflight_failure(
            output_dir=output_dir,
            metadata=metadata,
            failure="backend_environment_invalid",
            log_name="00_backend_environment.log",
            detail=str(exc),
        )
        print(f"Evidence directory: {output_dir}")
        print("Evidence status: failed")
        print("Failed gate: backend_environment_invalid")
        print(exc)
        return 1

    metadata["backend_python"] = backend_python
    metadata["backend_python_probe"] = backend_python_probe
    _write_json(output_dir / "metadata.json", metadata)

    backend_test_env = {
        "DATABASE_URL": os.getenv(
            "RELEASE_TEST_DATABASE_URL",
            "sqlite+pysqlite:///:memory:",
        )
    }

    commands: list[tuple[str, list[str], Path, dict[str, str] | None]] = [
        (
            "01_git_status",
            ["git", "status", "--short", "--branch"],
            REPO_ROOT,
            None,
        ),
        (
            "02_git_log",
            ["git", "log", "-12", "--oneline", "--decorate"],
            REPO_ROOT,
            None,
        ),
        (
            "03_backend_tests",
            [backend_python, "-m", "pytest", "tests/", "-q"],
            REPO_ROOT / "backend",
            backend_test_env,
        ),
        (
            "04_artifact_verifier",
            [backend_python, "-m", "app.ml.verify_release_artifacts"],
            REPO_ROOT / "backend",
            backend_test_env,
        ),
        (
            "05_rc_contract",
            [backend_python, "-m", "app.ml.verify_rc_contract"],
            REPO_ROOT / "backend",
            backend_test_env,
        ),
        (
            "06_fastapi_import",
            [
                backend_python,
                "-c",
                "from app.main import app; print('FastAPI import OK')",
            ],
            REPO_ROOT / "backend",
            backend_test_env,
        ),
        (
            "07_frontend_install",
            ["npm", "ci"],
            REPO_ROOT / "frontend",
            None,
        ),
        (
            "08_frontend_lint",
            ["npm", "run", "lint"],
            REPO_ROOT / "frontend",
            None,
        ),
        (
            "09_frontend_typecheck",
            ["npx", "tsc", "--noEmit"],
            REPO_ROOT / "frontend",
            None,
        ),
        (
            "10_frontend_build",
            ["npm", "run", "build"],
            REPO_ROOT / "frontend",
            None,
        ),
    ]

    if not args.skip_docker:
        commands.extend(
            [
                (
                    "11_compose_config",
                    ["docker", "compose", "config", "--quiet"],
                    REPO_ROOT,
                    None,
                ),
                (
                    "12_compose_ps",
                    ["docker", "compose", "ps"],
                    REPO_ROOT,
                    None,
                ),
            ]
        )

    commands.append(
        (
            "13_release_smoke",
            [sys.executable, "scripts/release_smoke.py"],
            REPO_ROOT,
            {"RESTOCKIQ_BASE_URL": args.base_url},
        )
    )

    if not args.skip_browser:
        commands.append(
            (
                "14_browser_e2e",
                ["npm", "run", "test:e2e"],
                REPO_ROOT / "frontend",
                {
                    "PLAYWRIGHT_BASE_URL": args.base_url,
                    "PLAYWRIGHT_OUTPUT_DIR": str(
                        output_dir / "playwright-results"
                    ),
                    "PLAYWRIGHT_REPORT_DIR": str(
                        output_dir / "playwright-report"
                    ),
                },
            )
        )

    results = [
        _run(
            name=name,
            command=command,
            cwd=cwd,
            output_dir=output_dir,
            env=env,
        )
        for name, command, cwd, env in commands
    ]

    try:
        https = _https_evidence(args.base_url)
    except Exception as exc:
        https = {
            "status": "failed",
            "base_url": args.base_url,
            "error": f"{type(exc).__name__}: {exc}",
        }
    _write_json(output_dir / "https.json", https)

    failures = [result["name"] for result in results if result["status"] != "passed"]
    if not metadata["source_clean"]:
        failures.append("source_worktree_dirty")
    if args.skip_docker:
        failures.append("docker_skipped")
    if args.skip_browser:
        failures.append("browser_skipped")
    if not args.base_url.startswith("https://") and not args.allow_http:
        failures.append("public_https_not_tested")
    if args.base_url.startswith("https://") and https["status"] != "passed":
        failures.append("https")

    if failures:
        evidence_status = "failed"
    elif args.allow_http:
        evidence_status = "passed_non_certifying"
    else:
        evidence_status = "passed"

    summary = {
        "status": evidence_status,
        "failures": failures,
        "commands": results,
        "https": https,
    }
    _write_json(output_dir / "summary.json", summary)
    print(f"Evidence directory: {output_dir}")
    print(f"Evidence status: {summary['status']}")
    if failures:
        print("Failed gates:", ", ".join(failures))
        for result in results:
            if result["status"] == "failed":
                print(f"- {result['name']}: {output_dir / result['log']}")
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
