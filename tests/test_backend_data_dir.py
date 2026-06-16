import sys
from pathlib import Path
from unittest.mock import patch


def test_parse_data_dir_returns_none_when_not_provided():
    from backend.main import _parse_data_dir
    with patch.object(sys, "argv", ["backend.exe", "--port", "8765"]):
        result = _parse_data_dir()
    assert result is None


def test_parse_data_dir_extracts_path():
    from backend.main import _parse_data_dir
    with patch.object(sys, "argv", ["backend.exe", "--data-dir", "/tmp/stdir"]):
        result = _parse_data_dir()
    assert result == Path("/tmp/stdir")


def test_parse_data_dir_ignores_unknown_args():
    from backend.main import _parse_data_dir
    with patch.object(sys, "argv", ["backend.exe", "--foo", "--data-dir", "/tmp/stdir", "--bar"]):
        result = _parse_data_dir()
    assert result == Path("/tmp/stdir")
