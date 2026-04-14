# SPDX-FileCopyrightText: 2025 Sebastian Andersson <sebastian@bittr.nu>
#
# SPDX-License-Identifier: GPL-3.0-or-later

"""Integration tests for the spoolman2slicer CLI."""

import json
import os
import sys
from unittest.mock import MagicMock, patch
import pytest
import requests

from spoolman2slicer import spoolman2slicer

class TestCLI:
    """Test suite for the main entry point and command-line interface."""

    @patch("spoolman2slicer.spoolman2slicer.SyncEngine")
    @patch("spoolman2slicer.spoolman2slicer.FilamentRenderer")
    @patch("spoolman2slicer.spoolman2slicer.SpoolmanClient")
    @patch("spoolman2slicer.spoolman2slicer.get_user_config_dir")
    @patch("os.path.exists")
    def test_main_basic_sync(self, mock_exists, mock_config_dir, mock_client, mock_renderer, mock_engine, tmp_path):
        """Test a successful basic sync run."""
        output_dir = tmp_path / "output"
        output_dir.mkdir()
        
        # Setup mocks
        mock_exists.return_value = True # Templates exist
        mock_config_dir.return_value = str(tmp_path / "config")
        
        # Mock sys.argv
        test_args = ["spoolman2slicer", "--dir", str(output_dir), "--url", "http://test:7912"]
        with patch.object(sys, "argv", test_args):
            spoolman2slicer.main()
            
        # Verify component initialization
        mock_client.assert_called_with("http://test:7912")
        # SyncEngine.sync_all should be called
        mock_engine.return_value.sync_all.assert_called_once()

    @patch("spoolman2slicer.spoolman2slicer.SyncEngine")
    @patch("spoolman2slicer.spoolman2slicer.get_user_config_dir")
    @patch("os.path.exists")
    @patch("time.sleep")
    def test_main_retry_loop(self, mock_sleep, mock_exists, mock_config_dir, mock_engine, tmp_path):
        """Test that main() retries initial sync in update mode."""
        output_dir = tmp_path / "output"
        output_dir.mkdir()
        
        mock_exists.return_value = True
        mock_config_dir.return_value = str(tmp_path / "config")
        
        # Setup engine to fail once then succeed
        mock_engine.return_value.sync_all.side_effect = [
            requests.exceptions.ConnectionError("Failed"),
            None # Success
        ]
        # mock_engine.return_value.run_loop should be called but we'll stop it
        mock_engine.return_value.run_loop.side_effect = KeyboardInterrupt()

        test_args = ["spoolman2slicer", "--dir", str(output_dir), "--updates"]
        with patch.object(sys, "argv", test_args):
            with patch("asyncio.run"): # Don't actually run the loop
                spoolman2slicer.main()
                
        # Sync all should have been called twice
        assert mock_engine.return_value.sync_all.call_count == 2
        mock_sleep.assert_called_once_with(5)

    @patch("spoolman2slicer.spoolman2slicer.PluginManager")
    @patch("spoolman2slicer.spoolman2slicer.get_user_config_dir")
    @patch("os.path.exists")
    def test_plugin_loading(self, mock_exists, mock_config_dir, mock_plugin_mgr, tmp_path):
        """Test that plugins are loaded when requested."""
        mock_exists.return_value = True
        mock_config_dir.return_value = str(tmp_path / "config")
        
        test_args = ["spoolman2slicer", "--dir", str(tmp_path), "--with-s2k", "--with-n2k"]
        with patch.object(sys, "argv", test_args):
            with patch("spoolman2slicer.spoolman2slicer.SyncEngine"):
                spoolman2slicer.main()
                
        # Check plugin loads
        mock_plugin_mgr.return_value.load_plugin.assert_any_call("s2k")
        mock_plugin_mgr.return_value.load_plugin.assert_any_call("n2k")
