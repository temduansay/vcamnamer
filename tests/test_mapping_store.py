"""
Tests for vcamnamer.mapping_store
"""

from __future__ import annotations

import json
import os
import tempfile
from pathlib import Path

import pytest

from vcamnamer.mapping_store import MappingStore, validate_name


# ---------------------------------------------------------------------------
# validate_name tests
# ---------------------------------------------------------------------------


class TestValidateName:
    def test_valid_name(self):
        validate_name("OBS Studio Camera")  # should not raise

    def test_valid_name_with_numbers(self):
        validate_name("Camera 1")

    def test_valid_name_with_hyphens_and_dots(self):
        validate_name("My-Cam.1")

    def test_empty_string_raises(self):
        with pytest.raises(ValueError, match="empty"):
            validate_name("")

    def test_whitespace_only_raises(self):
        with pytest.raises(ValueError, match="empty"):
            validate_name("   ")

    def test_too_long_raises(self):
        with pytest.raises(ValueError, match="maximum length"):
            validate_name("A" * 65)

    def test_exactly_max_length_ok(self):
        validate_name("A" * 64)

    def test_slash_raises(self):
        with pytest.raises(ValueError, match="invalid characters"):
            validate_name("My/Camera")

    def test_backslash_raises(self):
        with pytest.raises(ValueError, match="invalid characters"):
            validate_name("My\\Camera")

    def test_control_char_raises(self):
        with pytest.raises(ValueError, match="invalid characters"):
            validate_name("Cam\x01")

    def test_null_byte_raises(self):
        with pytest.raises(ValueError, match="invalid characters"):
            validate_name("Cam\x00")

    def test_reserved_dot_raises(self):
        with pytest.raises(ValueError, match="reserved"):
            validate_name(".")

    def test_reserved_dotdot_raises(self):
        with pytest.raises(ValueError, match="reserved"):
            validate_name("..")

    def test_non_string_raises(self):
        with pytest.raises(ValueError, match="string"):
            validate_name(123)  # type: ignore[arg-type]


# ---------------------------------------------------------------------------
# MappingStore tests
# ---------------------------------------------------------------------------


@pytest.fixture()
def store(tmp_path: Path) -> MappingStore:
    """Return a MappingStore backed by a temp directory."""
    return MappingStore(path=tmp_path / "mappings.json")


class TestMappingStore:
    def test_starts_empty(self, store: MappingStore):
        assert store.all() == {}
        assert len(store) == 0

    def test_set_and_get(self, store: MappingStore):
        store.set("/dev/video0", "OBS Cam")
        assert store.get("/dev/video0") == "OBS Cam"

    def test_get_missing_returns_none(self, store: MappingStore):
        assert store.get("/dev/video99") is None

    def test_set_trims_whitespace(self, store: MappingStore):
        store.set("/dev/video0", "  Trimmed  ")
        assert store.get("/dev/video0") == "Trimmed"

    def test_duplicate_name_different_node_raises(self, store: MappingStore):
        store.set("/dev/video0", "MyCamera")
        with pytest.raises(ValueError, match="already assigned"):
            store.set("/dev/video1", "MyCamera")

    def test_overwrite_same_node_ok(self, store: MappingStore):
        store.set("/dev/video0", "First")
        store.set("/dev/video0", "Second")
        assert store.get("/dev/video0") == "Second"

    def test_remove_mapping(self, store: MappingStore):
        store.set("/dev/video0", "Cam")
        store.remove("/dev/video0")
        assert store.get("/dev/video0") is None

    def test_remove_missing_no_error(self, store: MappingStore):
        store.remove("/dev/video99")  # should not raise

    def test_clear(self, store: MappingStore):
        store.set("/dev/video0", "A")
        store.set("/dev/video1", "B")
        store.clear()
        assert store.all() == {}

    def test_len(self, store: MappingStore):
        store.set("/dev/video0", "A")
        store.set("/dev/video1", "B")
        assert len(store) == 2

    def test_all_returns_copy(self, store: MappingStore):
        store.set("/dev/video0", "A")
        copy = store.all()
        copy["/dev/video0"] = "modified"
        assert store.get("/dev/video0") == "A"  # original unchanged

    # ------------------------------------------------------------------
    # Persistence
    # ------------------------------------------------------------------

    def test_save_and_load(self, tmp_path: Path):
        path = tmp_path / "mappings.json"
        s1 = MappingStore(path=path)
        s1.set("/dev/video0", "OBS Camera")
        s1.save()

        s2 = MappingStore(path=path)
        assert s2.get("/dev/video0") == "OBS Camera"

    def test_load_missing_file_starts_empty(self, tmp_path: Path):
        s = MappingStore(path=tmp_path / "nonexistent.json")
        assert s.all() == {}

    def test_load_corrupt_file_starts_empty(self, tmp_path: Path):
        path = tmp_path / "mappings.json"
        path.write_text("NOT_JSON_{{{{", encoding="utf-8")
        s = MappingStore(path=path)
        assert s.all() == {}

    def test_load_invalid_structure_starts_empty(self, tmp_path: Path):
        path = tmp_path / "mappings.json"
        path.write_text("[1, 2, 3]", encoding="utf-8")
        s = MappingStore(path=path)
        assert s.all() == {}

    def test_save_atomic_write(self, tmp_path: Path):
        """save() must not leave a .tmp file behind."""
        path = tmp_path / "mappings.json"
        s = MappingStore(path=path)
        s.set("/dev/video0", "Cam")
        s.save()
        assert not (tmp_path / "mappings.tmp").exists()
        assert path.exists()

    def test_persisted_json_is_valid(self, tmp_path: Path):
        path = tmp_path / "mappings.json"
        s = MappingStore(path=path)
        s.set("/dev/video0", "Cam One")
        s.save()
        data = json.loads(path.read_text(encoding="utf-8"))
        assert data == {"/dev/video0": "Cam One"}
