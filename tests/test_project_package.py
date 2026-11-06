import hashlib
import json
from pathlib import Path
from types import SimpleNamespace

import pytest

from kompas_mcp import project_package as package


def plan_for(tmp_path, contents=(b"part", b"assembly")):
    source = tmp_path / "source"
    source.mkdir()
    rows = []
    for index, value in enumerate(contents):
        path = source / f"source-{index}.bin"
        path.write_bytes(value)
        rows.append({
            "source": str(path),
            "source_sha256": hashlib.sha256(value).hexdigest(),
            "source_bytes": len(value),
            "destination_relative": f"assets/file-{index}.bin",
        })
    return {"copy_mapping": rows}


def test_preflight_does_not_create_output_and_marks_native_proof_missing(tmp_path):
    plan = plan_for(tmp_path)
    target = tmp_path / "copy"
    report = package.preflight_package(plan, target)
    assert not target.exists()
    assert report["file_count"] == 2
    assert report["phase"] == "preflight_pass_not_rebound"
    assert report["dependency_graph"]["status"] == "not_scanned"
    assert report["dependency_graph"]["missing_engineering_dependencies"] is None
    assert report["portable"] is False
    assert report["references_rewritten"] is False


def test_success_preserves_pinned_bytes_and_requires_native_followup(tmp_path):
    plan = plan_for(tmp_path)
    target = tmp_path / "copy"
    report = package.materialize_package(plan, target)
    assert report["phase"] == "files_staged_not_rebound"
    assert report["portable"] is False
    assert report["all_source_SHA_rechecked"]
    assert report["all_copied_SHA_verified"]
    manifest = json.loads((target / ".cad-package/manifest.json").read_text())
    owner = json.loads((target / ".cad-package/owner.json").read_text())
    assert owner["owner_id"] == manifest["owner_id"] == report["owner_id"]
    for row in plan["copy_mapping"]:
        assert (target / row["destination_relative"]).read_bytes() == Path(row["source"]).read_bytes()
    with pytest.raises(ValueError, match="already exists"):
        package.materialize_package(plan, target)


@pytest.mark.parametrize("relative", [
    "../escape.m3d", "assets/../escape.m3d", "/absolute.m3d", "C:\\absolute.m3d",
    "C:drive-relative.m3d", "\\\\server\\share\\file.m3d", "a//empty", "./dot",
    "a/CON.m3d", "a/lpt1", "a/NUL .txt", "a/COM1 .m3d", "a/COM\u00b9.txt",
    "a/CONOUT$", "a/trailing.",
    "a/trailing ", "a/stream:alternate",
    ".cad-package/manifest.json", "a/line\nbreak", "a/question?.m3d",
])
def test_unsafe_destination_fails_before_any_write(tmp_path, relative):
    plan = plan_for(tmp_path)
    plan["copy_mapping"][1]["destination_relative"] = relative
    target = tmp_path / "copy"
    with pytest.raises(ValueError):
        package.materialize_package(plan, target)
    assert not target.exists()


@pytest.mark.parametrize("replacement", ["ASSETS/FILE-0.BIN", "assets/file-0.bin/child"])
def test_casefold_collision_and_file_directory_conflict_reject(tmp_path, replacement):
    plan = plan_for(tmp_path)
    plan["copy_mapping"][1]["destination_relative"] = replacement
    with pytest.raises(ValueError, match="conflicting|Conflicting"):
        package.preflight_package(plan, tmp_path / "copy")


def test_unicode_normalization_collision_rejects_cross_platform_alias(tmp_path):
    plan = plan_for(tmp_path)
    plan["copy_mapping"][0]["destination_relative"] = "assets/caf\u00e9.m3d"
    plan["copy_mapping"][1]["destination_relative"] = "assets/cafe\u0301.m3d"
    with pytest.raises(ValueError, match="conflicting"):
        package.preflight_package(plan, tmp_path / "copy")


@pytest.mark.parametrize("fault", ["missing", "hash", "size", "duplicate_source"])
def test_entire_source_set_validated_before_destination_creation(tmp_path, fault):
    plan = plan_for(tmp_path)
    row = plan["copy_mapping"][1]
    if fault == "missing":
        Path(row["source"]).unlink()
    elif fault == "hash":
        Path(row["source"]).write_bytes(b"unexpected revision")
    elif fault == "size":
        row["source_bytes"] += 1
    else:
        row["source"] = plan["copy_mapping"][0]["source"]
    target = tmp_path / "copy"
    with pytest.raises(ValueError):
        package.materialize_package(plan, target)
    assert not target.exists()


def test_source_and_destination_ancestor_symlinks_rejected(tmp_path):
    plan = plan_for(tmp_path)
    source = tmp_path / "source"
    alias = tmp_path / "source-link"
    try:
        alias.symlink_to(source, target_is_directory=True)
    except OSError:
        pytest.skip("Symlinks unavailable in this test account")
    plan["copy_mapping"][0]["source"] = str(alias / "source-0.bin")
    with pytest.raises(ValueError, match="Symlink"):
        package.preflight_package(plan, tmp_path / "copy")
    plan["copy_mapping"][0]["source"] = str(source / "source-0.bin")
    with pytest.raises(ValueError, match="Symlink"):
        package.preflight_package(plan, alias / "copy")


def test_runtime_resources_are_named_exceptions_not_copied_or_verified(tmp_path):
    plan = plan_for(tmp_path)
    plan["runtime_resources"] = [{"name": "STYLE.LYT", "policy": "installed resource required"}]
    files = plan["copy_mapping"]
    plan["dependency_graph"] = {
        files[0]["source"]: ["resource:STYLE.LYT"],
        files[1]["source"]: [files[0]["source"]],
    }
    plan["roots"] = [files[0]["source"], files[1]["source"]]
    report = package.materialize_package(plan, tmp_path / "copy")
    assert len(report["copied"]) == 2
    assert report["runtime_resources"][0]["native_verified"] is False
    assert report["dependency_graph"]["status"] == "supplied_complete_graph"
    assert report["dependency_graph"]["native_closure_verified"] is False


def test_cycles_reported_explicitly_without_claiming_bottom_up_rebind(tmp_path):
    plan = plan_for(tmp_path)
    a, b = [row["source"] for row in plan["copy_mapping"]]
    plan["roots"] = [a, b]
    plan["dependency_graph"] = {a: [b], b: [a]}
    report = package.preflight_package(plan, tmp_path / "copy")
    assert report["dependency_graph"]["cycles"] == [[a, b, a]]
    assert report["dependency_graph"]["bottom_up_order"] is None
    assert report["dependency_graph"]["native_closure_verified"] is False


def test_partial_graph_is_not_promoted_to_complete(tmp_path):
    plan = plan_for(tmp_path)
    a, b = [row["source"] for row in plan["copy_mapping"]]
    plan["dependency_graph"] = {a: [b]}
    report = package.preflight_package(plan, tmp_path / "copy")
    assert report["dependency_graph"]["status"] == "supplied_partial_graph"


def test_missing_graph_link_rejected_before_copy(tmp_path):
    plan = plan_for(tmp_path)
    plan["dependency_graph"] = {plan["copy_mapping"][0]["source"]: ["not-in-plan.m3d"]}
    target = tmp_path / "copy"
    with pytest.raises(ValueError, match="Missing engineering dependencies"):
        package.materialize_package(plan, target)
    assert not target.exists()


def test_changed_source_between_preflight_and_copy_keeps_failed_owned_manifest(tmp_path, monkeypatch):
    plan = plan_for(tmp_path)
    original = package._copy_file
    second = Path(plan["copy_mapping"][1]["source"])

    def mutate_next_source(row, target):
        original(row, target)
        if row["source"] != str(second):
            second.write_bytes(b"changed after preflight")

    monkeypatch.setattr(package, "_copy_file", mutate_next_source)
    target = tmp_path / "copy"
    with pytest.raises(package.PackageMaterializationError) as failure:
        package.materialize_package(plan, target)
    report = failure.value.report
    assert report["phase"] == "files_staging_failed"
    assert report["portable"] is False
    assert report["inspect_before_retry"]
    saved = json.loads((target / ".cad-package/manifest.json").read_text())
    assert saved["owner_id"] == report["owner_id"]
    assert saved["copied"][0]["state"] == "copied_sha_verified"
    assert saved["copied"][1]["state"] == "copying"
    with pytest.raises(ValueError, match="already exists"):
        package.materialize_package(plan, target)


def test_change_to_previously_copied_source_caught_by_final_sweep(tmp_path, monkeypatch):
    plan = plan_for(tmp_path)
    original = package._copy_file
    first, second = [Path(row["source"]) for row in plan["copy_mapping"]]

    def mutate_earlier_source(row, target):
        original(row, target)
        if row["source"] == str(second):
            first.write_bytes(b"later revision")

    monkeypatch.setattr(package, "_copy_file", mutate_earlier_source)
    with pytest.raises(package.PackageMaterializationError, match="Source identity changed"):
        package.materialize_package(plan, tmp_path / "copy")


def test_copy_failure_preserves_own_directory_and_never_changes_other_files(tmp_path, monkeypatch):
    plan = plan_for(tmp_path)
    unrelated = tmp_path / "user-document.bin"
    unrelated.write_bytes(b"keep")

    def disk_failure(row, target):
        raise OSError("synthetic disk failure")

    monkeypatch.setattr(package, "_copy_file", disk_failure)
    target = tmp_path / "copy"
    with pytest.raises(package.PackageMaterializationError, match="synthetic disk failure"):
        package.materialize_package(plan, target)
    assert target.is_dir()
    assert unrelated.read_bytes() == b"keep"
    assert all(Path(row["source"]).exists() for row in plan["copy_mapping"])


def test_previously_copied_file_corruption_is_caught_before_final_success(tmp_path, monkeypatch):
    plan = plan_for(tmp_path)
    original = package._copy_file
    first, second = plan["copy_mapping"]

    def corrupt_earlier_copy(row, target):
        original(row, target)
        if row["source"] == second["source"]:
            (target / first["destination_relative"]).write_bytes(b"corrupt")

    monkeypatch.setattr(package, "_copy_file", corrupt_earlier_copy)
    with pytest.raises(package.PackageMaterializationError, match="Copied file changed"):
        package.materialize_package(plan, tmp_path / "copy")


def test_empty_or_unbounded_plan_rejected(tmp_path):
    with pytest.raises(ValueError, match="copy_mapping"):
        package.preflight_package({"copy_mapping": []}, tmp_path / "copy")
    plan = plan_for(tmp_path)
    with pytest.raises(ValueError, match="bounded"):
        package.preflight_package(plan, tmp_path / "copy", max_files=1)


def test_unknown_runtime_resource_requires_explicit_policy(tmp_path):
    plan = plan_for(tmp_path)
    plan["runtime_resources"] = [{"name": "STYLE.LYT"}]
    with pytest.raises(ValueError, match="name and policy"):
        package.preflight_package(plan, tmp_path / "copy")


def _stat_with(value, **changes):
    fields = {name: getattr(value, name) for name in (
        "st_dev", "st_ino", "st_size", "st_mtime_ns", "st_ctime_ns", "st_mode"
    )}
    return SimpleNamespace(**(fields | changes))


def test_stat_and_fstat_ctime_channels_may_differ_without_false_source_change(tmp_path, monkeypatch):
    """NTFS after fsync can report fd ctime differently from the named path."""
    plan = plan_for(tmp_path)
    original = package.os.fstat

    def different_fd_ctime(descriptor):
        value = original(descriptor)
        return _stat_with(value, st_ctime_ns=value.st_ctime_ns + 123456)

    monkeypatch.setattr(package.os, "fstat", different_fd_ctime)
    report = package.materialize_package(plan, tmp_path / "copy")
    assert report["phase"] == "files_staged_not_rebound"
    assert report["all_source_SHA_rechecked"] and report["all_copied_SHA_verified"]
    assert report["files"][0]["source_identity"]["ctime_ns"] == Path(
        plan["copy_mapping"][0]["source"]
    ).stat().st_ctime_ns


@pytest.mark.parametrize("field", ["st_dev", "st_ino"])
def test_path_handle_device_and_inode_must_still_match(tmp_path, monkeypatch, field):
    plan = plan_for(tmp_path)
    original = package.os.fstat

    def different_handle_identity(descriptor):
        value = original(descriptor)
        return _stat_with(value, **{field: getattr(value, field) + 1})

    monkeypatch.setattr(package.os, "fstat", different_handle_identity)
    target = tmp_path / "copy"
    with pytest.raises(ValueError, match="path/handle identity mismatch"):
        package.materialize_package(plan, target)
    assert not target.exists()


def test_change_within_fd_ctime_channel_still_rejects(tmp_path, monkeypatch):
    plan = plan_for(tmp_path)
    original = package.os.fstat
    calls = 0

    def changing_fd_ctime(descriptor):
        nonlocal calls
        calls += 1
        value = original(descriptor)
        return _stat_with(value, st_ctime_ns=value.st_ctime_ns + calls)

    monkeypatch.setattr(package.os, "fstat", changing_fd_ctime)
    target = tmp_path / "copy"
    with pytest.raises(ValueError, match="Source changed while reading"):
        package.materialize_package(plan, target)
    assert not target.exists()
