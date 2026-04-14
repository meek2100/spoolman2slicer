# SPDX-FileCopyrightText: 2025 Sebastian Andersson <sebastian@bittr.nu>
#
# SPDX-License-Identifier: GPL-3.0-or-later

"""Tests for the SpoolmanClient class."""

import json
import pytest
import requests
from unittest.mock import Mock, patch
from spoolman2slicer.spoolman_common.api import SpoolmanClient

class TestSpoolmanClient:
    """Test suite for the Spoolman API client."""

    def test_decode_extra_fields(self):
        """Test recursive JSON decoding of 'extra' fields."""
        client = SpoolmanClient("http://test:7912")
        
        # Sample data where extra fields are JSON strings
        data = {
            "id": 1,
            "extra": '{"pressure_advance": "0.045", "notes": "test"}', # Wait, Spoolman usually gives 'extra' as a dict where VALUES are strings
            "filament": {
                "extra": {"nested_key": '{"val": 123}'}
            }
        }
        
        # Correcting the sample to match Spoolman's actual structure
        data = {
            "extra": {"pa": "0.045"},
            "filament": {
                "extra": {"density": "1.24", "raw": '{"valid": true}'}
            }
        }
        
        client._decode_extra_fields(data)
        
        # PA isn't a valid JSON object (it's a string representing a float), 
        # but our logic tries json.loads on strings. 0.045 is a valid JSON float.
        assert data["extra"]["pa"] == 0.045
        assert data["filament"]["extra"]["density"] == 1.24
        assert data["filament"]["extra"]["raw"]["valid"] is True

    @patch("requests.Session.get")
    def test_get_json_retries(self, mock_get):
        """Test that get_json retries on connection error."""
        client = SpoolmanClient("http://test:7912")
        
        # Setup mock to fail twice then succeed
        mock_get.side_effect = [
            requests.exceptions.ConnectionError("Failed"),
            requests.exceptions.ConnectionError("Failed"),
            Mock(status_code=200, json=lambda: {"id": 123}, text='{"id": 123}')
        ]
        
        with patch("time.sleep"): # Skip waiting
            result = client._get_json("test")
            
        assert result == {"id": 123}
        assert mock_get.call_count == 3

    @patch("requests.Session.get")
    def test_get_active_spools(self, mock_get, sample_spoolman_response):
        """Test fetching and decoding active spools."""
        client = SpoolmanClient("http://test:7912")
        
        # Match the sample response structure
        mock_get.return_value = Mock(
            status_code=200, 
            json=lambda: sample_spoolman_response,
            text=json.dumps(sample_spoolman_response)
        )
        
        spools = client.get_active_spools()
        assert len(spools) == len(sample_spoolman_response)
        mock_get.assert_called()
    @patch("requests.Session.get")
    def test_get_json_http_error(self, mock_get):
        """Test that get_json raises HTTPError for 4xx/5xx responses."""
        client = SpoolmanClient("http://test:7912")
        mock_get.return_value = Mock(status_code=404)
        mock_get.return_value.raise_for_status.side_effect = requests.exceptions.HTTPError("Not Found", response=mock_get.return_value)
        
        with pytest.raises(requests.exceptions.HTTPError):
            client._get_json("test")

    @patch("requests.Session.get")
    def test_get_json_invalid_json(self, mock_get):
        """Test that get_json raises ValueError on malformed JSON response."""
        client = SpoolmanClient("http://test:7912")
        mock_get.return_value = Mock(status_code=200)
        mock_get.return_value.json.side_effect = json.JSONDecodeError("Expecting value", "", 0)
        
        with pytest.raises(json.JSONDecodeError):
            client._get_json("test")

    @patch("requests.Session.get")
    def test_get_json_retries_exhausted(self, mock_get):
        """Test that get_json eventually raises the last exception after retries."""
        client = SpoolmanClient("http://test:7912")
        mock_get.side_effect = requests.exceptions.Timeout("Timed out")
        
        with patch("time.sleep"):
            with pytest.raises(requests.exceptions.Timeout):
                client._get_json("test", max_retries=2)
        
        assert mock_get.call_count == 2
