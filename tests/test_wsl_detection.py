"""Tests for reaper_client._is_wsl() — the check that turns a silent,
unexplained IPC timeout (Python running inside WSL, REAPER running native
Windows, two different filesystems for %TEMP%/tmp) into a specific,
actionable startup error instead.
"""

import os
import sys
from unittest import mock

from reaper_mcp.reaper_client import _is_wsl


class TestIsWSL:
    def test_non_linux_platform_is_never_wsl(self):
        with mock.patch.object(sys, "platform", "win32"):
            assert _is_wsl() is False
        with mock.patch.object(sys, "platform", "darwin"):
            assert _is_wsl() is False

    def test_detects_via_wsl_distro_name_env_var(self):
        with mock.patch.object(sys, "platform", "linux"), \
             mock.patch.dict(os.environ, {"WSL_DISTRO_NAME": "Ubuntu"}, clear=False):
            assert _is_wsl() is True

    def test_detects_via_wsl_interop_env_var(self):
        with mock.patch.object(sys, "platform", "linux"), \
             mock.patch.dict(os.environ, {"WSL_INTEROP": "/run/WSL/1_interop"}, clear=False):
            assert _is_wsl() is True

    def test_detects_via_proc_version_microsoft_marker(self):
        with mock.patch.object(sys, "platform", "linux"), \
             mock.patch.dict(os.environ, {}, clear=True):
            m = mock.mock_open(read_data="Linux version 5.15.0 (Microsoft@Microsoft.com)")
            with mock.patch("builtins.open", m):
                assert _is_wsl() is True

    def test_native_linux_is_not_flagged(self):
        """No false positives — a real Linux box must not trip this."""
        with mock.patch.object(sys, "platform", "linux"), \
             mock.patch.dict(os.environ, {}, clear=True):
            m = mock.mock_open(read_data="Linux version 6.8.0-generic (buildd@lcy02-amd64)")
            with mock.patch("builtins.open", m):
                assert _is_wsl() is False

    def test_missing_proc_version_does_not_crash(self):
        """/proc/version isn't guaranteed on every Linux (containers, minimal
        images) — must degrade to False, not raise."""
        with mock.patch.object(sys, "platform", "linux"), \
             mock.patch.dict(os.environ, {}, clear=True):
            with mock.patch("builtins.open", side_effect=OSError("no such file")):
                assert _is_wsl() is False
