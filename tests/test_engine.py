# SPDX-FileCopyrightText: 2025 Sebastian Andersson <sebastian@bittr.nu>
#
# SPDX-License-Identifier: GPL-3.0-or-later

"""Tests for the SyncEngine orchestration logic."""

import os
from pathlib import Path
from unittest.mock import MagicMock, patch
import pytest
from spoolman2slicer.engine import SyncEngine

class TestSyncEngine:
    """Test suite for the central synchronization engine."""

    def test_sync_all_renders_files(self, sync_engine, mock_spoolman_client, sample_spoolman_response, temp_output_dir):
        """Test that sync_all fetches spools and triggers rendering."""
        # Setup mock client response
        mock_spoolman_client.get_active_spools.return_value = sample_spoolman_response
        
        # Run sync
        sync_engine.sync_all(tidy=True)
        
        # Verify call to client
        mock_spoolman_client.get_active_spools.assert_called_once()
        
        # Verify files were created (sample_spoolman_response from conftest has several spools)
        # Based on filename.template: "{{vendor.name}} - {{name}}.{{sm2s.slicer_suffix}}"
        # Example from filaments.json: "TestVendor - Test PLA Black.ini"
        out_files = os.listdir(temp_output_dir)
        assert len(out_files) > 0
        assert any("Test PLA Black" in f for f in out_files)

    def test_usage_tracking_and_deletion(self, sync_engine, mock_spoolman_client, temp_output_dir):
        """Test that the engine tracks file usage and deletes when orphan."""
        spool_a = {
            "id": 101,
            "filament": {
                "id": 1, "name": "F1", "material": "PLA", "color_hex": "000000",
                "price": 20.0, "density": 1.24, "diameter": 1.75,
                "settings_extruder_temp": 200, "settings_bed_temp": 60,
                "vendor": {"name": "V1"}
            }
        }
        
        # First write
        sync_engine.write_spool_profile(spool_a)
        filenames = sync_engine.spool_id_to_filenames[101]
        filename = list(filenames)[0]
        assert os.path.exists(filename)
        assert sync_engine.filename_usage[filename] == 1
        
        # Change the spool's filament (causing filename change)
        spool_a["filament"] = {
            "id": 2, "name": "F2", "material": "ABS", "color_hex": "FF0000",
            "price": 30.0, "density": 1.04, "diameter": 1.75,
            "settings_extruder_temp": 240, "settings_bed_temp": 100,
            "vendor": {"name": "V2"}
        }
        sync_engine.write_spool_profile(spool_a)
        
        # Old filename should be deleted (usage dropped to 0)
        assert not os.path.exists(filename)
        # New filename should exist
        new_filenames = sync_engine.spool_id_to_filenames[101]
        new_filename = list(new_filenames)[0]
        assert os.path.exists(new_filename)
        assert sync_engine.filename_usage[new_filename] == 1

    def test_create_per_spool_all(self, mock_spoolman_client, filament_renderer, sample_spoolman_response, temp_output_dir):
        """Test the 'all' mode for per-spool file creation."""
        engine = SyncEngine(
            client=mock_spoolman_client,
            renderer=filament_renderer,
            variants=[""],
            create_per_spool="all"
        )
        
        mock_spoolman_client.get_active_spools.return_value = sample_spoolman_response
        engine.sync_all()
        
        # In 'all' mode, cache key should use spool ID
        # filename_for_spool.template appends the spool ID
        out_files = os.listdir(temp_output_dir)
        # Expected filenames should contain numeric IDs like "V - N - 1.ini", "V - N - 2.ini" etc.
        assert any("- 1.ini" in f for f in out_files)
        assert any("- 2.ini" in f for f in out_files)

    def test_event_handling_updated(self, sync_engine, mock_spoolman_client):
        """Test that WebSocket updated events trigger re-rendering."""
        event = {
            "resource": "spool",
            "type": "updated",
            "payload": {
                "id": 101,
                "filament_id": 1,
                "filament": {"id": 1, "name": "F1", "vendor": {"name": "V1"}}
            }
        }
        
        with patch.object(sync_engine, "write_spool_profile") as mock_write:
            sync_engine.handle_event(event)
            mock_write.assert_called_once_with(event["payload"])
        
        assert sync_engine.spools_cache[101] == event["payload"]
    def test_ranking_least_left(self, mock_spoolman_client, filament_renderer):
        """Test that 'least-left' correctly picks the spool with smallest weight."""
        engine = SyncEngine(mock_spoolman_client, filament_renderer, [""], create_per_spool="least-left")
        
        spool1 = {"id": 1, "remaining_weight": 500, "filament": {"id": 10, "name": "F1", "vendor": {"name": "V"}}}
        spool2 = {"id": 2, "remaining_weight": 100, "filament": {"id": 10, "name": "F1", "vendor": {"name": "V"}}}
        
        mock_spoolman_client.get_active_spools.return_value = [spool1, spool2]
        
        with patch.object(engine, "write_spool_profile") as mock_write:
            engine.sync_all()
            # Should have called write for spool2 (100g < 500g)
            mock_write.assert_called_once_with(spool2)

    def test_ranking_most_recent(self, mock_spoolman_client, filament_renderer):
        """Test that 'most-recent' correctly picks the spool with latest usage."""
        engine = SyncEngine(mock_spoolman_client, filament_renderer, [""], create_per_spool="most-recent")
        
        spool1 = {"id": 1, "last_used": "2024-01-01T12:00:00Z", "filament": {"id": 10, "name": "F1", "vendor": {"name": "V"}}}
        spool2 = {"id": 2, "last_used": "2024-02-01T12:00:00Z", "filament": {"id": 10, "name": "F1", "vendor": {"name": "V"}}}
        
        mock_spoolman_client.get_active_spools.return_value = [spool1, spool2]
        
        with patch.object(engine, "write_spool_profile") as mock_write:
            engine.sync_all()
            # Should have called write for spool2 (Feb > Jan)
            mock_write.assert_called_once_with(spool2)

    def test_handle_deleted_event(self, sync_engine):
        """Test that deletion events remove spools from cache."""
        sync_engine.spools_cache[101] = {"id": 101}
        event = {
            "resource": "spool",
            "type": "deleted",
            "payload": {"id": 101}
        }
        sync_engine.handle_event(event)
        assert 101 not in sync_engine.spools_cache
