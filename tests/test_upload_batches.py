"""Batch upload acceptance: synthetic workspaces, real local PDF inspection."""

from concurrent.futures import ThreadPoolExecutor
import hashlib
import json
from pathlib import Path
from threading import Barrier
from uuid import uuid4

import pytest

from plw import backups, reader_runtime, storage, uploads, workspace
from plw.materials import MaterialService
from plw.services import LearningService
from plw.workbench import Workbench


FIXTURE = storage.PROJECT_ROOT / ".sandbox/r0/968c198e-a06e-4438-8910-6cf634af2c15/sources/原生 PDF 中文课件.pdf"


def uid():
    return str(uuid4())


@pytest.fixture
def batch_env():
    root = storage.ROOTS[1] / ("upload-batches-" + uid())
    workspace.initialize_workspace(root)
    path = workspace.active_db(root)
    service = LearningService(path)
    semester = service.create_semester("合成批次学期", request_id=uid())
    course = service.create_course(semester["id"], "机器人运动学", request_id=uid())
    return path, service, semester, course, FIXTURE.read_bytes()


def run_batch(env, files=None, *, batch_id=None, course_id=None, progress=None):
    path, _, _, course, pdf = env
    return uploads.import_courseware(path, course_id or course["id"],
                                     [("中文 课件.pdf", pdf)] if files is None else files,
                                     batch_id or uid(), progress)


def test_multiple_uploads_automatically_prepare_readable_editions_and_report_progress(batch_env):
    path, _, _, course, pdf = batch_env
    progress = []
    results = run_batch(batch_env, [("第一讲.pdf", pdf), ("第二讲.PDF", pdf + b"\n% synthetic revision\n")],
                        progress=lambda current, total, result: progress.append((current, total, result["filename"])))
    assert [r["status"] for r in results] == ["ready", "ready"]
    assert progress == [(1, 2, "第一讲.pdf"), (2, 2, "第二讲.PDF")]
    wb = Workbench(path)
    assert len(wb.rows("reading_editions")) == 2
    for result in results:
        row = MaterialService(path).get_material(result["material_id"])
        assert row["course_id"] == course["id"] and row["storage_mode"] == "managed_copy"
        assert row["reference_path"] is None
        assert wb.edition_state(result["edition_id"])["page"] == 1
        assert (path.parent / f"reading/{result['edition_id']}.pdf").is_file()


def test_two_good_one_bad_continue_independently(batch_env):
    path, _, _, _, pdf = batch_env
    results = run_batch(batch_env, [("第一讲.pdf", pdf), ("bad.exe", b"blocked"), ("第二讲.pdf", pdf)])
    assert [r["status"] for r in results] == ["ready", "failed", "ready"]
    assert results[1]["material_id"] is None and results[1]["edition_id"] is None
    assert "导入未完成" in results[1]["message"]
    assert len(MaterialService(path).list_materials()) == len(Workbench(path).rows("reading_editions")) == 2


def test_unreadable_pdf_preserves_import_and_other_pdf_still_reads(batch_env):
    path, _, _, _, pdf = batch_env
    results = run_batch(batch_env, [("broken.pdf", b"not a valid PDF"), ("good.pdf", pdf)])
    assert [r["status"] for r in results] == ["saved", "ready"]
    assert results[0]["material_id"] and results[0]["edition_id"] is None
    assert "课件已保存" in results[0]["message"]
    assert len(MaterialService(path).list_materials()) == 2
    assert len(Workbench(path).rows("reading_editions")) == 1


def test_repeated_click_or_new_batch_reuses_material_and_edition(batch_env):
    path = batch_env[0]
    token = uid()
    original, = run_batch(batch_env, batch_id=token)
    same, = run_batch(batch_env, batch_id=token)
    fresh, = run_batch(batch_env)
    assert original["status"] == same["status"] == fresh["status"] == "ready"
    assert not original["reused"] and same["reused"] and fresh["reused"]
    assert original["material_id"] == same["material_id"] == fresh["material_id"]
    assert original["edition_id"] == same["edition_id"] == fresh["edition_id"]
    assert len(MaterialService(path).list_materials()) == len(Workbench(path).rows("reading_editions")) == 1


def test_same_filename_changed_content_is_separate_with_old_edition_preserved(batch_env):
    path, _, _, _, pdf = batch_env
    first, = run_batch(batch_env, [("same.pdf", pdf)])
    second, = run_batch(batch_env, [("same.pdf", pdf + b"\n% another synthetic revision\n")])
    assert first["status"] == second["status"] == "ready"
    assert first["material_id"] != second["material_id"] and first["edition_id"] != second["edition_id"]
    assert not second["reused"]
    assert len(MaterialService(path).list_materials()) == len(Workbench(path).rows("reading_editions")) == 2


def test_identical_upload_in_different_courses_has_independent_records(batch_env):
    path, learning, semester, course, _ = batch_env
    another = learning.create_course(semester["id"], "自动控制", request_id=uid())
    first, = run_batch(batch_env)
    second, = run_batch(batch_env, course_id=another["id"])
    assert first["status"] == second["status"] == "ready"
    assert first["material_id"] != second["material_id"] and first["edition_id"] != second["edition_id"]
    assert not second["reused"]
    materials = MaterialService(path)
    assert len(materials.list_materials(course["id"])) == len(materials.list_materials(another["id"])) == 1


@pytest.mark.parametrize("archive", ["course", "semester"])
def test_archived_course_or_semester_refuses_new_upload_and_existing_reuse(batch_env, archive):
    path, learning, semester, course, _ = batch_env
    run_batch(batch_env)
    if archive == "course":
        learning.set_course_archived(course["id"], True, course["revision"])
    else:
        learning.set_semester_archived(semester["id"], True, semester["revision"])
    result, = run_batch(batch_env)
    assert result["status"] == "failed" and result["material_id"] is None
    assert "归档" in result["message"]
    assert len(MaterialService(path).list_materials()) == len(Workbench(path).rows("reading_editions")) == 1


def test_concurrent_batches_do_not_duplicate_same_courseware(batch_env):
    path = batch_env[0]
    barrier = Barrier(2)
    def run(_):
        barrier.wait()
        return run_batch(batch_env)[0]
    with ThreadPoolExecutor(max_workers=2) as executor:
        first, second = executor.map(run, range(2))
    assert first["status"] == second["status"] == "ready"
    assert first["material_id"] == second["material_id"] and first["edition_id"] == second["edition_id"]
    assert {first["reused"], second["reused"]} == {False, True}
    assert len(MaterialService(path).list_materials()) == len(Workbench(path).rows("reading_editions")) == 1


def test_ppt_conversion_failure_can_retry_without_material_duplication_and_pdf_continues(batch_env, monkeypatch):
    path, _, _, _, pdf = batch_env
    calls = []
    def initially_fail(source, target):
        calls.append((source, target))
        if len(calls) == 1:
            raise ValueError("synthetic PowerPoint conversion failure")
        target.write_bytes(pdf)
    monkeypatch.setattr(reader_runtime, "convert_ppt", initially_fail)
    files = [("slides.pptx", b"synthetic PPTX original bytes"), ("native.pdf", pdf)]
    initial = run_batch(batch_env, files)
    assert [r["status"] for r in initial] == ["saved", "ready"]
    assert initial[0]["material_id"] and initial[0]["edition_id"] is None
    retry = run_batch(batch_env, files)
    assert [r["status"] for r in retry] == ["ready", "ready"]
    assert all(r["reused"] for r in retry)
    assert [r["material_id"] for r in retry] == [r["material_id"] for r in initial]
    assert initial[1]["edition_id"] == retry[1]["edition_id"]
    assert len(calls) == 2 and calls[0][1] != calls[1][1]
    assert len(MaterialService(path).list_materials()) == len(Workbench(path).rows("reading_editions")) == 2


def test_complete_backup_contains_uploaded_originals_and_reading_pdfs(batch_env, monkeypatch):
    path, _, _, _, pdf = batch_env
    ppt = b"synthetic original PPTX preserved exactly"
    monkeypatch.setattr(reader_runtime, "convert_ppt", lambda source, target: target.write_bytes(pdf))
    results = run_batch(batch_env, [("slides.pptx", ppt), ("handout.pdf", pdf)])
    assert all(r["status"] == "ready" for r in results)
    report = backups.create_backup(path)
    assert report["complete"] and report["external"] == []
    folder = Path(report["path"])
    manifest = json.loads((folder / "manifest.json").read_text(encoding="utf-8"))
    assert sum(entry["type"] == "reading_pdf" for entry in manifest["files"]) == 2
    for result, original in zip(results, (ppt, pdf)):
        material = MaterialService(path).get_material(result["material_id"])
        stored = folder / "payload" / material["managed_relpath"]
        assert stored.read_bytes() == original
        assert hashlib.sha256(stored.read_bytes()).hexdigest() == material["baseline_sha256"]
        assert (folder / "payload" / f"reading/{result['edition_id']}.pdf").read_bytes() == pdf
    assert backups.verify_backup(folder)["complete"]


@pytest.mark.parametrize("files", [[], [("x.pdf", b"synthetic")] * 21, [("x.pdf", "not bytes")]])
def test_invalid_batch_refused_before_any_material_or_edition(batch_env, files):
    with pytest.raises(ValueError):
        run_batch(batch_env, files)
    assert MaterialService(batch_env[0]).list_materials() == []
    assert Workbench(batch_env[0]).rows("reading_editions") == []


def test_batch_size_limit_refuses_everything_before_writes(batch_env, monkeypatch):
    monkeypatch.setattr(uploads, "MAX_BATCH_BYTES", 8)
    with pytest.raises(ValueError, match="分批"):
        run_batch(batch_env, [("x.pdf", b"12345"), ("y.pdf", b"6789")])
    assert MaterialService(batch_env[0]).list_materials() == []


def test_empty_and_oversize_individual_files_fail_without_blocking_valid_pdf(batch_env, monkeypatch):
    path, _, _, _, pdf = batch_env
    monkeypatch.setattr(uploads, "UPLOAD_MAX_BYTES", len(pdf))
    results = run_batch(batch_env, [("empty.pdf", b""), ("too-large.pdf", pdf + b"x"), ("valid.pdf", pdf)])
    assert [r["status"] for r in results] == ["failed", "failed", "ready"]
    assert results[0]["material_id"] is results[1]["material_id"] is None
    assert len(MaterialService(path).list_materials()) == len(Workbench(path).rows("reading_editions")) == 1


def test_damaged_existing_managed_copy_is_not_advertised_or_replaced(batch_env):
    path = batch_env[0]
    original, = run_batch(batch_env)
    material = MaterialService(path).get_material(original["material_id"])
    target = path.parent / material["managed_relpath"]
    target.write_bytes(b"synthetic file damage")
    retry, = run_batch(batch_env)
    assert retry["status"] == "failed" and retry["material_id"] is None
    assert "校验失败" in retry["message"]
    assert target.read_bytes() == b"synthetic file damage"
    assert len(MaterialService(path).list_materials()) == 1
