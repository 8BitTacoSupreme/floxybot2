"""Tests for Co-Pilot diagnose mode."""

from __future__ import annotations

from unittest.mock import AsyncMock, patch

import pytest

from src.modes.diagnose import (
    async_diagnose,
    _gather_environment_data,
    _build_diagnostic_message,
    _local_analysis,
    _format_report,
)


class TestGatherEnvironmentData:
    def test_no_flox_env(self, tmp_path, monkeypatch):
        monkeypatch.chdir(tmp_path)
        data = _gather_environment_data()
        assert data["has_flox_env"] is False

    def test_with_flox_env(self, tmp_path, monkeypatch):
        flox_dir = tmp_path / ".flox" / "env"
        flox_dir.mkdir(parents=True)
        (flox_dir / "manifest.toml").write_text('[install]\npython3.pkg-path = "python3"\n')
        monkeypatch.chdir(tmp_path)

        with patch("subprocess.run") as mock_run:
            mock_run.return_value.stdout = "python3\nnodejs"
            mock_run.return_value.returncode = 0
            data = _gather_environment_data()

        assert data["has_flox_env"] is True
        assert "python3" in data["manifest"]


class TestBuildDiagnosticMessage:
    def test_basic_message(self):
        env_data = {
            "has_flox_env": True,
            "manifest": "[install]\npython3.pkg-path = \"python3\"",
            "packages": ["python3", "nodejs"],
            "flox_status": "Active",
        }
        msg = _build_diagnostic_message(env_data)
        assert msg["user_identity"]["channel"] == "copilot"
        assert "analyze" in msg["content"]["text"].lower()
        assert msg["context"]["channel_metadata"]["mode"] == "diagnose"


class TestLocalAnalysis:
    def test_with_packages(self):
        env_data = {
            "has_flox_env": True,
            "manifest": "[install]\npython3.pkg-path = \"python3\"",
            "packages": ["python3", "nodejs"],
        }
        report = _local_analysis(env_data)
        assert "Offline" in report
        assert "python3" in report

    def test_empty_manifest(self):
        env_data = {
            "has_flox_env": True,
            "manifest": "",
            "packages": [],
        }
        report = _local_analysis(env_data)
        assert "empty" in report.lower() or "issues" in report.lower()


class TestFormatReport:
    def test_format_with_analysis(self):
        env_data = {"has_flox_env": True, "packages": ["python3"], "flox_status": "Active"}
        report = _format_report(env_data, "Everything looks good.")
        assert "Diagnostic" in report
        assert "Everything looks good" in report


class TestAsyncDiagnose:
    @pytest.mark.asyncio
    async def test_no_flox_env(self, tmp_path, monkeypatch):
        monkeypatch.chdir(tmp_path)
        result = await async_diagnose(offline=True)
        assert result["status"] == "no_env"

    @pytest.mark.asyncio
    async def test_offline_with_env(self, tmp_path, monkeypatch):
        flox_dir = tmp_path / ".flox" / "env"
        flox_dir.mkdir(parents=True)
        (flox_dir / "manifest.toml").write_text('[install]\npython3.pkg-path = "python3"\n')
        monkeypatch.chdir(tmp_path)

        with patch("subprocess.run") as mock_run:
            mock_run.return_value.stdout = "python3"
            mock_run.return_value.returncode = 0
            result = await async_diagnose(offline=True)

        assert result["status"] == "offline"
        assert "report" in result

    @pytest.mark.asyncio
    async def test_online_success(self, tmp_path, monkeypatch):
        flox_dir = tmp_path / ".flox" / "env"
        flox_dir.mkdir(parents=True)
        (flox_dir / "manifest.toml").write_text('[install]\npython3.pkg-path = "python3"\n')
        monkeypatch.chdir(tmp_path)

        mock_client = AsyncMock()
        mock_client.post_message = AsyncMock(return_value={"text": "Your env looks healthy."})
        mock_client.close = AsyncMock()

        with patch("subprocess.run") as mock_run:
            mock_run.return_value.stdout = "python3"
            mock_run.return_value.returncode = 0
            with patch("src.api_client.CopilotAPIClient", return_value=mock_client):
                result = await async_diagnose(api_url="http://test:8000")

        assert result["status"] == "ok"
