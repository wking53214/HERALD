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


def _copy_package(tmp_path):
    import shutil
    dest = tmp_path / "herald_copy"
    shutil.copytree(binding._PACKAGE_DIR, dest, ignore=shutil.ignore_patterns("__pycache__"))
    return str(dest)


def test_hash_of_a_clean_copy_matches_the_real_package(tmp_path):
    assert code_hash(_copy_package(tmp_path)) == code_hash()


def test_adding_a_nested_module_changes_the_hash(tmp_path):
    import os
    copy = _copy_package(tmp_path)
    before = code_hash(copy)
    os.makedirs(os.path.join(copy, "sub"))
    with open(os.path.join(copy, "sub", "extra.py"), "w") as handle:
        handle.write("X = 1\n")
    assert code_hash(copy) != before
    assert "sub/extra.py" in binding.file_hashes(copy)


def test_editing_a_nested_module_changes_the_hash(tmp_path):
    import os
    copy = _copy_package(tmp_path)
    os.makedirs(os.path.join(copy, "sub"))
    path = os.path.join(copy, "sub", "extra.py")
    with open(path, "w") as handle:
        handle.write("X = 1\n")
    before = code_hash(copy)
    with open(path, "w") as handle:
        handle.write("X = 2\n")
    assert code_hash(copy) != before


def test_moving_a_module_changes_the_hash_even_if_its_text_does_not(tmp_path):
    import os
    copy = _copy_package(tmp_path)
    os.makedirs(os.path.join(copy, "sub"))
    src = os.path.join(copy, "lineage.py")
    before = code_hash(copy)
    os.replace(src, os.path.join(copy, "sub", "lineage.py"))
    assert code_hash(copy) != before


def test_non_python_files_are_outside_the_hash(tmp_path):
    import os
    copy = _copy_package(tmp_path)
    before = code_hash(copy)
    with open(os.path.join(copy, "settings.cfg"), "w") as handle:
        handle.write("x=1\n")
    assert code_hash(copy) == before
