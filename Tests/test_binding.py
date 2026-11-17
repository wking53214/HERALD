"""Consumers pin to an exact build. Fixes do not propagate silently."""

import pytest

from herald import binding
from herald.binding import Binding, VERSION, code_hash, current_pin
from herald.errors import BindingError


def test_code_hash_is_stable_across_calls():
    assert code_hash() == code_hash()


def test_current_pin_verifies_against_this_build():
    current_pin("sentinel_os").verify()


def test_version_mismatch_refuses():
    with pytest.raises(BindingError) as exc:
        Binding("sentinel_os", "0.0.1", code_hash()).verify()
    assert "0.0.1" in str(exc.value)


def test_same_version_different_code_refuses():
    """The dangerous case: version says nothing moved, source says otherwise."""
    with pytest.raises(BindingError) as exc:
        Binding("ats", VERSION, "0" * 64).verify()
    assert "source changed" in str(exc.value)


def test_version_only_pin_is_refused_by_the_ordinary_check():
    pin = Binding("resume_os", VERSION)
    with pytest.raises(BindingError) as exc:
        pin.verify()
    assert "no code hash pinned" in str(exc.value)
    assert not pin.is_hash_pinned()
    assert current_pin("resume_os").is_hash_pinned()


def test_version_only_legacy_check_is_separate_and_named_as_such():
    Binding("resume_os", VERSION).verify_version_only_LEGACY()
    with pytest.raises(BindingError):
        Binding("resume_os", "0.0.1").verify_version_only_LEGACY()


def test_version_only_pin_is_refused_by_build_and_read():
    from herald import handoff
    from herald.source import SourceDocument, STANDING_RECORD
    doc = SourceDocument(source_id="d", text="Paid $5.00 today.", standing=STANDING_RECORD)
    with pytest.raises(BindingError):
        handoff.read(doc, binding_pin=Binding("c", VERSION), in_process_export=True)


def test_file_hashes_name_what_moved():
    hashes = binding.file_hashes()
    assert "boundary.py" in hashes and "extract.py" in hashes
    assert all(len(h) == 64 for h in hashes.values())
