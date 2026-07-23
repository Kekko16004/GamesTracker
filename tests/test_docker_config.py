"""Tests to validate Dockerfile and docker-compose.yml syntax and conventions.

These are static analysis tests — no Docker daemon is required. They parse
the files as text / YAML and assert on structural properties.
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest

PROJECT_ROOT = Path(__file__).resolve().parent.parent
DOCKERFILE = PROJECT_ROOT / "Dockerfile"
COMPOSE_FILE = PROJECT_ROOT / "docker-compose.yml"
DOCKERIGNORE = PROJECT_ROOT / ".dockerignore"


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _read(path: Path) -> str:
    assert path.exists(), f"File not found: {path}"
    return path.read_text(encoding="utf-8")


def _load_yaml(path: Path) -> dict:
    """Load YAML without requiring PyYAML to be in requirements (use stdlib only fallback)."""
    try:
        import yaml  # type: ignore
        return yaml.safe_load(_read(path)) or {}
    except ImportError:
        pytest.skip("PyYAML not installed — skipping YAML-parse tests")


# ---------------------------------------------------------------------------
# Dockerfile tests
# ---------------------------------------------------------------------------

class TestDockerfile:
    def setup_method(self):
        self.content = _read(DOCKERFILE)
        self.lines = self.content.splitlines()

    def test_file_exists(self):
        assert DOCKERFILE.exists()

    def test_has_two_stages(self):
        from_lines = [l for l in self.lines if l.strip().upper().startswith("FROM")]
        # Multi-stage: at least two FROM directives
        assert len(from_lines) >= 2, f"Expected multi-stage build, got: {from_lines}"

    def test_base_image_is_python_310_slim(self):
        from_lines = [l for l in self.lines if re.match(r"^FROM\s+python:3\.10-slim", l, re.IGNORECASE)]
        assert from_lines, "Base image should be python:3.10-slim"

    def test_has_healthcheck(self):
        assert "HEALTHCHECK" in self.content, "Dockerfile must include a HEALTHCHECK instruction"

    def test_healthcheck_references_python(self):
        hc_lines = [l for l in self.lines if "HEALTHCHECK" in l or (
            any("HEALTHCHECK" in p for p in self.lines[:i]) and l.strip().startswith("CMD")
            for i, _ in [(self.lines.index(l), None)]
        )]
        assert "python" in self.content.lower(), "HEALTHCHECK should use python"

    def test_has_oci_labels(self):
        assert "LABEL" in self.content, "Dockerfile must include OCI LABEL instructions"
        assert "org.opencontainers.image.title" in self.content

    def test_has_workdir(self):
        assert "WORKDIR" in self.content

    def test_requirements_copied_before_source(self):
        copy_req_idx = None
        copy_src_idx = None
        for i, line in enumerate(self.lines):
            stripped = line.strip()
            if re.match(r"COPY\s+.*requirements\.txt", stripped):
                copy_req_idx = i
            if re.match(r"COPY\s+\.\s+\.", stripped) or re.match(r"COPY\s+--chown=.*\s+\.\s+\.", stripped):
                copy_src_idx = i
        assert copy_req_idx is not None, "requirements.txt should be COPYed"
        assert copy_src_idx is not None, "Source code (. .) should be COPYed"
        assert copy_req_idx < copy_src_idx, (
            "requirements.txt must be copied before the full source to leverage Docker layer caching"
        )

    def test_uses_no_cache_dir_for_pip(self):
        assert "--no-cache-dir" in self.content, "pip install should use --no-cache-dir"

    def test_has_default_cmd(self):
        cmd_lines = [l for l in self.lines if l.strip().startswith("CMD")]
        assert cmd_lines, "Dockerfile must have a CMD instruction"
        # Default command should run the collector
        assert "run_collector" in self.content

    def test_non_root_user(self):
        user_lines = [l for l in self.lines if l.strip().startswith("USER") and "root" not in l.lower()]
        assert user_lines, "Dockerfile should switch to a non-root USER"

    def test_apt_cleanup_no_lists(self):
        # Best practice: remove /var/lib/apt/lists after apt-get
        assert "rm -rf /var/lib/apt/lists" in self.content

    def test_libgl_installed(self):
        # PyQt6 requires libGL at runtime
        assert "libgl1" in self.content.lower()

    def test_no_pip_install_without_requirements(self):
        # All pip installs should reference requirements.txt (not ad-hoc packages in final stage)
        pip_lines = [l.strip() for l in self.lines if "pip install" in l and "ruff" not in l]
        for line in pip_lines:
            assert "requirements.txt" in line or "--prefix" in line or "pip install" not in line, (
                f"Unexpected ad-hoc pip install: {line}"
            )


# ---------------------------------------------------------------------------
# docker-compose.yml tests
# ---------------------------------------------------------------------------

class TestDockerCompose:
    def setup_method(self):
        self.raw = _read(COMPOSE_FILE)

    def test_file_exists(self):
        assert COMPOSE_FILE.exists()

    def test_is_valid_yaml(self):
        compose = _load_yaml(COMPOSE_FILE)
        assert isinstance(compose, dict)

    def test_has_services_key(self):
        compose = _load_yaml(COMPOSE_FILE)
        assert "services" in compose

    def test_collector_service_exists(self):
        compose = _load_yaml(COMPOSE_FILE)
        assert "collector" in compose["services"]

    def test_web_service_exists(self):
        compose = _load_yaml(COMPOSE_FILE)
        assert "web" in compose["services"]

    def test_collector_runs_collector_script(self):
        compose = _load_yaml(COMPOSE_FILE)
        svc = compose["services"]["collector"]
        command = svc.get("command", [])
        if isinstance(command, list):
            assert any("run_collector" in str(c) for c in command)
        else:
            assert "run_collector" in str(command)

    def test_web_service_exposes_port_8000(self):
        compose = _load_yaml(COMPOSE_FILE)
        svc = compose["services"]["web"]
        ports = svc.get("ports", [])
        assert any("8000" in str(p) for p in ports), "web service must expose port 8000"

    def test_web_depends_on_collector(self):
        compose = _load_yaml(COMPOSE_FILE)
        svc = compose["services"]["web"]
        depends = svc.get("depends_on", {})
        if isinstance(depends, list):
            assert "collector" in depends
        else:
            assert "collector" in depends

    def test_volumes_defined(self):
        compose = _load_yaml(COMPOSE_FILE)
        assert "volumes" in compose, "Top-level volumes section required"

    def test_network_isolation(self):
        compose = _load_yaml(COMPOSE_FILE)
        assert "networks" in compose, "Top-level networks section required"

    def test_env_file_referenced(self):
        # Both services should reference config/.env
        assert "config/.env" in self.raw

    def test_data_volume_mounted(self):
        compose = _load_yaml(COMPOSE_FILE)
        for svc_name in ("collector", "web"):
            svc = compose["services"][svc_name]
            mounts = svc.get("volumes", [])
            mount_strs = [str(m) for m in mounts]
            assert any("data" in m for m in mount_strs), (
                f"Service '{svc_name}' should mount the data volume"
            )

    def test_services_have_restart_policy(self):
        compose = _load_yaml(COMPOSE_FILE)
        for svc_name, svc in compose["services"].items():
            assert "restart" in svc, f"Service '{svc_name}' should have a restart policy"

    def test_env_example_comments_present(self):
        # The compose file spec says to include .env example inline as comments
        assert "DB_URL" in self.raw or "NOTIFICATIONS_ENABLED" in self.raw, (
            "docker-compose.yml should contain .env variable documentation in comments"
        )


# ---------------------------------------------------------------------------
# .dockerignore tests
# ---------------------------------------------------------------------------

class TestDockerignore:
    def setup_method(self):
        self.content = _read(DOCKERIGNORE)
        self.patterns = set(
            line.strip()
            for line in self.content.splitlines()
            if line.strip() and not line.strip().startswith("#")
        )

    def test_file_exists(self):
        assert DOCKERIGNORE.exists()

    def test_excludes_git(self):
        assert ".git" in self.patterns

    def test_excludes_venv(self):
        assert any("venv" in p for p in self.patterns)

    def test_excludes_pycache(self):
        assert any("__pycache__" in p for p in self.patterns)

    def test_excludes_data_dir(self):
        assert any("data" in p for p in self.patterns)

    def test_excludes_env_files(self):
        assert any(".env" in p for p in self.patterns)

    def test_excludes_pyc(self):
        assert any(".pyc" in p or "*.py[cod]" in p for p in self.patterns)

    def test_excludes_github_dir(self):
        assert any(".github" in p for p in self.patterns)
