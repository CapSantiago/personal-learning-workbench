"""Synthetic M2 material records and explicit, recoverable filesystem operations.

Database commits cannot be atomic with filesystem writes. Durable operation rows
record intent before bytes are copied; unfinished operations require an explicit
reconciliation. Sources are read only and all managed writes remain in a dataset.
"""

from __future__ import annotations

from contextlib import contextmanager
from datetime import UTC, datetime
import hashlib
import json
import os
from pathlib import Path
import re
import sqlite3
from typing import Any, Iterator
import unicodedata
from uuid import UUID, uuid4

from plw import db, locking, storage


class MaterialError(Exception):
    """A material operation could not safely complete."""


class MaterialValidationError(MaterialError):
    pass


class MaterialNotFoundError(MaterialError):
    pass


class MaterialConflictError(MaterialError):
    pass


class MaterialStorageError(MaterialError):
    pass


_TYPES = frozenset({"slides", "textbook", "assignment", "lab_guide", "exam_paper", "code", "other"})
_MODES = frozenset({"managed_copy", "external_reference"})
UPLOAD_MAX_BYTES = 200 * 1024 * 1024
_UPLOAD_EXTENSIONS = frozenset({".pdf", ".ppt", ".pptx"})


def _now() -> str:
    return datetime.now(UTC).isoformat(timespec="microseconds").replace("+00:00", "Z")


def _uuid(value: Any, label: str = "ID") -> str:
    try:
        if not isinstance(value, (str, UUID)):
            raise ValueError()
        return str(UUID(str(value).strip()))
    except (ValueError, AttributeError) as exc:
        raise MaterialValidationError(f"{label}必须是有效 UUID。") from exc


def _text(value: Any, label: str, *, limit: int = 500, required: bool = True) -> str:
    if not isinstance(value, str):
        raise MaterialValidationError(f"{label}必须是文本。")
    result = value.strip()
    if len(result) > limit or (required and not result) or any(ord(c) < 32 for c in result):
        raise MaterialValidationError(f"{label}为空、过长或包含控制字符。")
    return result


def _payload(values: dict[str, Any]) -> str:
    return json.dumps(values, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


def _upload_filename(value: Any) -> str:
    """Accept a browser's basename, never interpret a client-supplied path."""
    if (not isinstance(value, str) or not value or len(value) > 255
            or value != value.strip() or value.endswith(".")
            or any(c in value for c in '/\\<>:"|?*')
            or any(unicodedata.category(c).startswith("C") for c in value)):
        raise MaterialValidationError("上传文件名无效：请选择文件本身，不要填写路径。")
    if len(value.encode("utf-16-le")) // 2 > 255:
        raise MaterialValidationError("上传文件名过长。")
    stem = unicodedata.normalize("NFKC", value.split(".")[0]).upper()
    if stem in storage.RESERVED or stem in {"CONIN$", "CONOUT$"}:
        raise MaterialValidationError("上传文件名不能使用 Windows 设备名。")
    if Path(value).suffix.lower() not in _UPLOAD_EXTENSIONS:
        raise MaterialValidationError("请选择 PDF、PPT 或 PPTX 课件。")
    return value


class MaterialService:
    def __init__(self, db_path: str | Path):
        self.db_path = Path(db_path)
        self.root = self.db_path.parent

    @contextmanager
    def _session(self, *, write: bool = False) -> Iterator[sqlite3.Connection]:
        try:
            with db.transaction(self.db_path, write=write) as connection:
                yield connection
        except MaterialError:
            raise
        except (db.DatabaseError, sqlite3.Error, OSError, RuntimeError, ValueError) as exc:
            raise MaterialStorageError(f"资料数据库操作未完成：{exc}") from exc

    @contextmanager
    def _write(self) -> Iterator[None]:
        try:
            with locking.write_barrier(self.db_path):
                yield
        except MaterialError:
            raise
        except (db.DatabaseError, sqlite3.Error, OSError, RuntimeError, ValueError) as exc:
            raise MaterialStorageError(f"资料操作未完成：{exc}") from exc

    @staticmethod
    def _fetch(connection: sqlite3.Connection, material_id: str) -> dict[str, Any]:
        row = connection.execute("SELECT * FROM materials WHERE id=?", (material_id,)).fetchone()
        if row is None:
            raise MaterialNotFoundError("资料记录不存在。")
        return dict(row)

    def get_material(self, material_id: str | UUID) -> dict[str, Any]:
        with self._session() as connection:
            return self._fetch(connection, _uuid(material_id, "资料 ID"))

    def list_materials(self, course_id: str | UUID | None = None, query: str = "", *,
                       include_deleted: bool = False) -> list[dict[str, Any]]:
        if not isinstance(include_deleted, bool):
            raise MaterialValidationError("是否显示已移除资料必须为布尔值。")
        query = _text(query, "搜索内容", required=False)
        pattern = "%" + query.replace("!", "!!").replace("%", "!%").replace("_", "!_") + "%"
        clauses = ["name LIKE ? ESCAPE '!' COLLATE NOCASE"]
        args: list[Any] = [pattern]
        if course_id is not None:
            clauses.append("course_id=?")
            args.append(_uuid(course_id, "课程 ID"))
        if not include_deleted:
            clauses.append("deleted_at IS NULL")
        with self._session() as connection:
            return [dict(row) for row in connection.execute(
                "SELECT * FROM materials WHERE " + " AND ".join(clauses) + " ORDER BY created_at,id", args
            )]

    def find_duplicates(self, material_id: str | UUID) -> list[dict[str, Any]]:
        row = self.get_material(material_id)
        if row["baseline_sha256"] is None:
            return []
        with self._session() as connection:
            return [dict(item) for item in connection.execute(
                "SELECT * FROM materials WHERE id<>? AND baseline_sha256=? AND import_state='ready' "
                "AND deleted_at IS NULL ORDER BY created_at,id", (row["id"], row["baseline_sha256"])
            )]

    @staticmethod
    def _is_courseware(row: dict[str, Any]) -> bool:
        return Path(row["original_path"]).suffix.lower() in _UPLOAD_EXTENSIONS

    @staticmethod
    def _ordered_active(connection: sqlite3.Connection, course_id: str) -> list[dict[str, Any]]:
        rows = [dict(row) for row in connection.execute(
            "SELECT * FROM materials WHERE course_id=? AND deleted_at IS NULL", (course_id,)
        )]
        # Preserve the old shelf's tie-breaking until an explicit write normalizes
        # legacy positions; opening a shelf must never modify existing data.
        return sorted(rows, key=lambda row: (row["position"], row["name"], row["created_at"], row["id"]))

    @staticmethod
    def _write_positions(connection: sqlite3.Connection, rows: list[dict[str, Any]]) -> None:
        now = _now()
        connection.executemany("UPDATE materials SET position=?,updated_at=? WHERE id=?",
                               [(position, now, row["id"]) for position, row in enumerate(rows)
                                if row["position"] != position])

    def _append_position(self, connection: sqlite3.Connection, course_id: str) -> int:
        rows = self._ordered_active(connection, course_id)
        self._write_positions(connection, rows)
        return len(rows)

    def list_courseware(self, course_id: str | UUID) -> list[dict[str, Any]]:
        """Return the complete visible PPT/PDF order, independent of UI filters."""
        with self._session() as connection:
            return [row for row in self._ordered_active(connection, _uuid(course_id, "课程 ID"))
                    if self._is_courseware(row)]

    def move_courseware(self, course_id: str | UUID, material_id: str | UUID, destination: int, *,
                        expected_order: list[str]) -> list[dict[str, Any]]:
        """Move to a one-based courseware slot atomically, rejecting stale views.

        Non-courseware files retain their relative slots. Hidden files do not
        participate; restoring them appends them to the end of the course.
        """
        course_id, material_id = _uuid(course_id, "课程 ID"), _uuid(material_id, "资料 ID")
        if isinstance(destination, bool) or not isinstance(destination, int) or destination < 1:
            raise MaterialValidationError("目标位置必须是从 1 开始的整数。")
        if not isinstance(expected_order, list):
            raise MaterialValidationError("请提供当前课程的完整课件顺序。")
        expected = [_uuid(value, "课件 ID") for value in expected_order]
        if len(set(expected)) != len(expected):
            raise MaterialValidationError("当前课件顺序中存在重复记录。")
        with self._write(), self._session(write=True) as connection:
            self._active_course(connection, course_id)
            selected = self._fetch(connection, material_id)
            if selected["course_id"] != course_id or selected["deleted_at"] or not self._is_courseware(selected):
                raise MaterialConflictError("只能调整当前课程中尚未移除的 PPT/PDF 课件。")
            rows = self._ordered_active(connection, course_id)
            courseware = [row for row in rows if self._is_courseware(row)]
            if [row["id"] for row in courseware] != expected:
                raise MaterialConflictError("课件列表已在其他页面发生变化，请刷新后重新调整。")
            if destination > len(courseware):
                raise MaterialValidationError(f"目标位置不能超过 {len(courseware)}。")
            moved = next(row for row in courseware if row["id"] == material_id)
            courseware.remove(moved)
            courseware.insert(destination - 1, moved)
            reordered = iter(courseware)
            rows = [next(reordered) if self._is_courseware(row) else row for row in rows]
            self._write_positions(connection, rows)
            return [row for row in self._ordered_active(connection, course_id) if self._is_courseware(row)]

    def association_counts(self, material_id: str | UUID) -> dict[str, int]:
        material_id = _uuid(material_id, "资料 ID")
        with self._session() as connection:
            self._fetch(connection, material_id)
            return {kind: connection.execute(f"SELECT count(*) FROM {table} WHERE material_id=?",
                                             (material_id,)).fetchone()[0]
                    for kind, table in (("tasks", "task_materials"), ("notes", "note_materials"),
                                        ("chapters", "chapter_materials"), ("editions", "reading_editions"))}

    def _with_duplicates(self, material_id: str) -> dict[str, Any]:
        row = self.get_material(material_id)
        row["duplicate_candidates"] = self.find_duplicates(material_id)
        return row

    @staticmethod
    def _active_course(connection: sqlite3.Connection, course_id: str) -> None:
        row = connection.execute(
            "SELECT c.archived_at,s.archived_at AS semester_archived_at FROM courses c "
            "JOIN semesters s ON s.id=c.semester_id WHERE c.id=?", (course_id,)
        ).fetchone()
        if row is None:
            raise MaterialNotFoundError("所属课程不存在。")
        if row["archived_at"] or row["semester_archived_at"]:
            raise MaterialConflictError("所属课程或学期已归档，请先取消归档。")

    def _managed(self, row: dict[str, Any], *, must_exist: bool = False) -> Path:
        relpath = row["managed_relpath"]
        # A compromised record must never expand deletion/write authority.
        if not isinstance(relpath, str) or not relpath.startswith(f"managed/{row['id']}/"):
            raise MaterialValidationError("托管路径与资料 ID 不一致。")
        if len(Path(relpath).parts) != 3:
            raise MaterialValidationError("托管路径层级无效。")
        return storage.relative_file(self.root, relpath, must_exist=must_exist)

    def _operation_state(self, operation_id: str, state: str, *, error: str | None = None) -> None:
        with self._session(write=True) as connection:
            connection.execute("UPDATE file_operations SET state=?,error_code=?,updated_at=? WHERE id=?",
                               (state, error, _now(), operation_id))

    def _failed(self, operation_id: str, material_id: str, error: Exception) -> None:
        # If even this commit fails, the earlier durable intent still remains for reconciliation.
        try:
            with self._session(write=True) as connection:
                now = _now()
                connection.execute("UPDATE file_operations SET state='failed',error_code=?,updated_at=? WHERE id=?",
                                   (type(error).__name__, now, operation_id))
                connection.execute("UPDATE materials SET import_state='failed',last_error_code=?,updated_at=? "
                                   "WHERE id=? AND import_state<>'ready'", (type(error).__name__, now, material_id))
        except MaterialError:
            pass

    def _commit_import(self, operation: dict[str, Any], row: dict[str, Any], path: Path) -> None:
        size, digest = storage.hash_file(path)
        if digest != operation["expected_sha256"] or size != row["size_bytes"]:
            raise MaterialConflictError("文件校验与导入基线不一致，保留现场以便核对。")
        now = _now()
        with self._session(write=True) as connection:
            connection.execute(
                "UPDATE materials SET import_state='ready',file_status='normal',observed_sha256=?,"
                "mtime_ns=?,hash_checked_at=?,last_checked_at=?,last_error_code=NULL,updated_at=? WHERE id=?",
                (digest, path.stat().st_mtime_ns, now, now, now, row["id"])
            )
            connection.execute("UPDATE file_operations SET state='committed',error_code=NULL,updated_at=? WHERE id=?",
                               (now, operation["id"]))

    def import_file(self, course_id: str | UUID, source_path: str | Path, storage_mode: str, *,
                    name: str | None = None, material_type: str = "other", request_id: str | UUID) -> dict[str, Any]:
        course_id = _uuid(course_id, "课程 ID")
        request_id = _uuid(request_id, "请求 ID")
        if storage_mode not in _MODES or material_type not in _TYPES:
            raise MaterialValidationError("不支持的存储模式或资料类型。")
        with self._write():
            source = storage.check_source(source_path, db_path=self.db_path)
            name = _text(source.name if name is None else name, "资料名称")
            serialized = _payload({"course_id": course_id, "source_path": str(source),
                                   "storage_mode": storage_mode, "name": name, "material_type": material_type})
            with self._session() as connection:
                prior = connection.execute("SELECT * FROM file_operations WHERE request_id=?", (request_id,)).fetchone()
                if prior is not None:
                    if prior["kind"] != "import_material" or prior["payload_json"] != serialized:
                        raise MaterialConflictError("此请求 ID 已用于另一组资料参数，请生成新请求。")
                    row = self._fetch(connection, prior["entity_id"])
                    if prior["state"] != "committed" or row["import_state"] != "ready":
                        raise MaterialConflictError("此前导入未完成；请先执行文件操作核对，不会自动重复复制。")
            if prior is not None:
                return self._with_duplicates(prior["entity_id"])
            storage.safe_path(source, must_exist=True, directory=False, source_only=True)
            size, digest = storage.hash_file(source)
            mtime = source.stat().st_mtime_ns
            material_id, operation_id = str(uuid4()), str(uuid4())
            suffix = source.suffix if re.fullmatch(r"\.[A-Za-z0-9]{1,12}", source.suffix) else ""
            managed = f"managed/{material_id}/payload{suffix}" if storage_mode == "managed_copy" else None
            stage = f".staging/{operation_id}/payload.part" if managed else None
            now = _now()
            with self._session(write=True) as connection:
                self._active_course(connection, course_id)
                position = self._append_position(connection, course_id)
                connection.execute(
                    "INSERT INTO materials(id,course_id,name,material_type,storage_mode,original_path,reference_path,"
                    "managed_relpath,size_bytes,mtime_ns,baseline_sha256,import_state,created_at,updated_at,position) "
                    "VALUES(?,?,?,?,?,?,?,?,?,?,?,'pending',?,?,?)",
                    (material_id, course_id, name, material_type, storage_mode, str(source),
                     str(source) if managed is None else None, managed, size, mtime, digest, now, now, position)
                )
                connection.execute(
                    "INSERT INTO file_operations(id,request_id,kind,entity_id,state,staging_relpath,target_relpath,"
                    "expected_sha256,payload_json,created_at,updated_at) VALUES(?,?,'import_material',?,'planned',?,?,?,?,?,?)",
                    (operation_id, request_id, material_id, stage, managed, digest, serialized, now, now)
                )
            operation = {"id": operation_id, "expected_sha256": digest}
            try:
                row = self.get_material(material_id)
                target = source
                if managed:
                    staged = storage.relative_file(self.root, stage)
                    target = self._managed(row)
                    storage.copy_verified(source, staged, expected_sha256=digest)
                    self._operation_state(operation_id, "staged")
                    self._promote(staged, target)
                    self._operation_state(operation_id, "promoted")
                self._commit_import(operation, row, target)
            except Exception as exc:
                self._failed(operation_id, material_id, exc)
                if isinstance(exc, MaterialError):
                    raise
                raise MaterialStorageError(f"导入未完成，来源未修改；请核对操作日志：{exc}") from exc
            return self._with_duplicates(material_id)

    def import_upload(self, course_id: str | UUID, filename: str, content: bytes, *,
                      material_type: str = "slides", request_id: str | UUID) -> dict[str, Any]:
        """Import browser bytes as a managed file, with durable recovery intent.

        Browsers do not disclose the client's original path. The existing schema
        requires an absolute original_path, so it records this import's actual
        server destination. The operation payload explicitly identifies the
        browser source and preserves its filename; no client path is invented.
        """
        course_id = _uuid(course_id, "课程 ID")
        request_id = _uuid(request_id, "请求 ID")
        filename = _upload_filename(filename)
        if not isinstance(material_type, str) or material_type not in _TYPES:
            raise MaterialValidationError("不支持的资料类型。")
        if not isinstance(content, bytes):
            raise MaterialValidationError("上传内容必须是文件的二进制数据。")
        size = len(content)
        if not size:
            raise MaterialValidationError("上传文件为空，请重新选择课件。")
        if size > UPLOAD_MAX_BYTES:
            raise MaterialValidationError("单个课件不能超过 200 MiB，请拆分后导入。")
        digest = hashlib.sha256(content).hexdigest()
        serialized = _payload({"source_kind": "browser_upload", "course_id": course_id,
                               "filename": filename, "storage_mode": "managed_copy",
                               "material_type": material_type, "size_bytes": size, "sha256": digest})
        with self._write():
            with self._session() as connection:
                prior = connection.execute("SELECT * FROM file_operations WHERE request_id=?", (request_id,)).fetchone()
                if prior is not None:
                    if prior["kind"] != "import_material" or prior["payload_json"] != serialized:
                        raise MaterialConflictError("此请求 ID 已用于另一组资料参数，请生成新请求。")
                    row = self._fetch(connection, prior["entity_id"])
                    if prior["state"] != "committed" or row["import_state"] != "ready":
                        raise MaterialConflictError("此前导入未完成；请先执行文件操作核对，不会自动重复写入。")
            if prior is not None:
                return self._with_duplicates(prior["entity_id"])
            material_id, operation_id = str(uuid4()), str(uuid4())
            managed = f"managed/{material_id}/payload{Path(filename).suffix.lower()}"
            stage = f".staging/{operation_id}/payload.part"
            target = storage.relative_file(self.root, managed)
            now = _now()
            with self._session(write=True) as connection:
                self._active_course(connection, course_id)
                position = self._append_position(connection, course_id)
                connection.execute(
                    "INSERT INTO materials(id,course_id,name,material_type,storage_mode,original_path,reference_path,"
                    "managed_relpath,size_bytes,mtime_ns,baseline_sha256,import_state,created_at,updated_at,position) "
                    "VALUES(?,?,?,?,'managed_copy',?,NULL,?,?,NULL,?,'pending',?,?,?)",
                    (material_id, course_id, filename, material_type, str(target), managed, size, digest, now, now, position)
                )
                connection.execute(
                    "INSERT INTO file_operations(id,request_id,kind,entity_id,state,staging_relpath,target_relpath,"
                    "expected_sha256,payload_json,created_at,updated_at) VALUES(?,?,'import_material',?,'planned',?,?,?,?,?,?)",
                    (operation_id, request_id, material_id, stage, managed, digest, serialized, now, now)
                )
            try:
                row = self.get_material(material_id)
                staged = storage.relative_file(self.root, stage)
                self._stage_upload(staged, content)
                if storage.hash_file(staged) != (size, digest):
                    raise MaterialConflictError("上传暂存校验失败，保留文件供核对。")
                self._operation_state(operation_id, "staged")
                self._promote(staged, self._managed(row))
                self._operation_state(operation_id, "promoted")
                self._commit_import({"id": operation_id, "expected_sha256": digest}, row, target)
            except Exception as exc:
                self._failed(operation_id, material_id, exc)
                if isinstance(exc, MaterialError):
                    raise
                raise MaterialStorageError(f"上传未完成，已保留操作日志；请在数据与备份中核对：{exc}") from exc
            return self._with_duplicates(material_id)

    def _stage_upload(self, staged: Path, content: bytes) -> None:
        storage.safe_path(staged, root=self.root, directory=False)
        staged.parent.mkdir(parents=True, exist_ok=True)
        storage.safe_path(staged, root=self.root, directory=False)
        # Exclusive creation never overwrites a pre-existing or partially written
        # file. Chunked writes avoid a second full-size copy of browser bytes.
        with staged.open("xb") as stream:
            view = memoryview(content)
            for offset in range(0, len(view), 1024 * 1024):
                stream.write(view[offset:offset + 1024 * 1024])
            stream.flush()
            os.fsync(stream.fileno())
        storage.safe_path(staged, root=self.root, must_exist=True, directory=False)

    def _promote(self, staged: Path, target: Path) -> None:
        storage.safe_path(staged, root=self.root, must_exist=True, directory=False)
        storage.safe_path(target, root=self.root, directory=False)
        target.parent.mkdir(parents=True, exist_ok=True)
        storage.safe_path(target.parent, root=self.root, must_exist=True, directory=True)
        if target.exists():
            raise MaterialConflictError("目标文件已存在，绝不覆盖。")
        # On Windows rename fails if target exists, including a competing creator.
        staged.rename(target)

    def check_material(self, material_id: str | UUID, full_hash: bool = True) -> dict[str, Any]:
        if not isinstance(full_hash, bool):
            raise MaterialValidationError("完整校验选项必须为布尔值。")
        material_id = _uuid(material_id, "资料 ID")
        with self._write():
            row = self.get_material(material_id)
            status, error, observed, hash_at = "normal", None, row["observed_sha256"], row["hash_checked_at"]
            try:
                path = (self._managed(row, must_exist=True) if row["storage_mode"] == "managed_copy"
                        else storage.check_source(row["reference_path"], db_path=self.db_path))
                storage.safe_path(path, must_exist=True, directory=False, source_only=True)
                info = path.stat()
                if full_hash:
                    size, observed = storage.hash_file(path)
                    hash_at = _now()
                    if observed != row["baseline_sha256"] or size != row["size_bytes"]:
                        status = "possibly_changed"
                elif (info.st_size != row["size_bytes"] or info.st_mtime_ns != row["mtime_ns"]
                      or row["file_status"] in {"possibly_changed", "unchecked"}):
                    status = "possibly_changed"
            except FileNotFoundError:
                status, error = "missing", "FileNotFoundError"
            except Exception as exc:
                status, error = "inaccessible", type(exc).__name__
            now = _now()
            with self._session(write=True) as connection:
                connection.execute(
                    "UPDATE materials SET file_status=?,last_error_code=?,last_checked_at=?,observed_sha256=?,"
                    "hash_checked_at=?,updated_at=? WHERE id=?", (status, error, now, observed, hash_at, now, material_id)
                )
            return self.get_material(material_id)

    def relink_reference(self, material_id: str | UUID, new_path: str | Path, *,
                         confirm_changed: bool = False) -> dict[str, Any]:
        if not isinstance(confirm_changed, bool):
            raise MaterialValidationError("内容变化确认必须为布尔值。")
        material_id = _uuid(material_id, "资料 ID")
        with self._write():
            row = self.get_material(material_id)
            if row["storage_mode"] != "external_reference" or row["import_state"] != "ready":
                raise MaterialConflictError("仅已完成导入的外部引用可以重连。")
            target = storage.check_source(new_path, db_path=self.db_path)
            storage.safe_path(target, must_exist=True, directory=False, source_only=True)
            size, digest = storage.hash_file(target)
            changed = digest != row["baseline_sha256"] or size != row["size_bytes"]
            if changed and not confirm_changed:
                raise MaterialConflictError("新文件内容与导入基线不同，需明确确认内容变化。")
            now = _now()
            with self._session(write=True) as connection:
                connection.execute(
                    "UPDATE materials SET reference_path=?,file_status=?,observed_sha256=?,last_checked_at=?,"
                    "hash_checked_at=?,last_error_code=NULL,updated_at=? WHERE id=?",
                    (str(target), "possibly_changed" if changed else "normal", digest, now, now, now, material_id)
                )
            return self.get_material(material_id)

    def set_deleted(self, material_id: str | UUID, deleted: bool) -> dict[str, Any]:
        if not isinstance(deleted, bool):
            raise MaterialValidationError("移除状态必须为布尔值。")
        material_id = _uuid(material_id, "资料 ID")
        with self._write(), self._session(write=True) as connection:
            row = self._fetch(connection, material_id)
            if not deleted and row["file_deleted_at"]:
                raise MaterialConflictError("托管文件已物理删除，不能直接恢复资料索引。")
            if bool(row["deleted_at"]) != deleted:
                now = _now()
                position = row["position"] if deleted else self._append_position(connection, row["course_id"])
                connection.execute("UPDATE materials SET deleted_at=?,updated_at=?,position=? WHERE id=?",
                                   (now if deleted else None, now, position, material_id))
                self._write_positions(connection, self._ordered_active(connection, row["course_id"]))
            return self._fetch(connection, material_id)

    def delete_managed_file(self, material_id: str | UUID, *, confirmation: str) -> dict[str, Any]:
        material_id = _uuid(material_id, "资料 ID")
        if confirmation != material_id:
            raise MaterialValidationError("物理删除必须逐字输入资料 UUID 确认。")
        with self._write():
            row = self.get_material(material_id)
            if row["storage_mode"] != "managed_copy":
                raise MaterialConflictError("绝不能删除外部引用的原始文件。")
            if not row["deleted_at"] or row["import_state"] != "ready":
                raise MaterialConflictError("仅可物理删除已从列表移除且已完成导入的托管资料。")
            if row["file_deleted_at"]:
                return row
            if any(self.association_counts(material_id).values()):
                raise MaterialConflictError("资料仍被任务、笔记或章节引用；请先明确解除全部关联，再物理删除。")
            target = self._managed(row, must_exist=True)
            size, digest = storage.hash_file(target)
            if digest != row["baseline_sha256"] or size != row["size_bytes"]:
                raise MaterialConflictError("托管文件内容已变化，物理删除已阻止；请人工核对。")
            operation_id = str(uuid4())
            now = _now()
            with self._session(write=True) as connection:
                connection.execute(
                    "INSERT INTO file_operations(id,request_id,kind,entity_id,state,target_relpath,expected_sha256,"
                    "payload_json,created_at,updated_at) VALUES(?,?,'delete_managed_file',?,'planned',?,?,?,?,?)",
                    (operation_id, str(uuid4()), material_id, row["managed_relpath"], digest,
                     _payload({"confirmation": confirmation}), now, now)
                )
            try:
                self._managed(row, must_exist=True).unlink()
                self._commit_delete(operation_id, material_id)
            except Exception as exc:
                try:
                    self._operation_state(operation_id, "failed", error=type(exc).__name__)
                except MaterialError:
                    pass
                raise MaterialStorageError("托管删除未完整提交，请核对文件操作日志。") from exc
            return self.get_material(material_id)

    def _commit_delete(self, operation_id: str, material_id: str) -> None:
        now = _now()
        with self._session(write=True) as connection:
            connection.execute("UPDATE materials SET file_deleted_at=?,file_status='missing',last_checked_at=?,"
                               "updated_at=? WHERE id=?", (now, now, now, material_id))
            connection.execute("UPDATE file_operations SET state='committed',error_code=NULL,updated_at=? WHERE id=?",
                               (now, operation_id))

    def reconcile_operations(self) -> list[dict[str, Any]]:
        """Explicitly verify known intentions; never delete or adopt unknown files."""
        results = []
        with self._write():
            with self._session() as connection:
                pending = [dict(row) for row in connection.execute(
                    "SELECT * FROM file_operations WHERE state NOT IN ('committed','quarantined') ORDER BY created_at,id"
                )]
            for operation in pending:
                try:
                    row = self.get_material(operation["entity_id"])
                    if operation["kind"] == "delete_managed_file":
                        target = self._managed(row)
                        valid = (row["storage_mode"] == "managed_copy" and row["deleted_at"]
                                 and operation["target_relpath"] == row["managed_relpath"]
                                 and json.loads(operation["payload_json"]).get("confirmation") == row["id"])
                        if not valid:
                            raise MaterialConflictError("删除意图与资料不一致。")
                        if target.exists():
                            self._operation_state(operation["id"], "failed", error="delete_not_performed")
                        else:
                            self._commit_delete(operation["id"], row["id"])
                    elif operation["kind"] == "import_material":
                        self._reconcile_import(operation, row)
                    else:
                        continue  # Future note operations belong to the note service.
                except Exception as exc:
                    self._operation_state(operation["id"], "quarantined", error=type(exc).__name__)
                with self._session() as connection:
                    results.append(dict(connection.execute("SELECT * FROM file_operations WHERE id=?",
                                                           (operation["id"],)).fetchone()))
        return results

    def _reconcile_import(self, operation: dict[str, Any], row: dict[str, Any]) -> None:
        if operation["expected_sha256"] != row["baseline_sha256"]:
            raise MaterialConflictError("操作日志与导入基线不同。")
        if row["storage_mode"] == "external_reference":
            source = storage.check_source(row["reference_path"], db_path=self.db_path)
            if not source.exists():
                self._failed(operation["id"], row["id"], FileNotFoundError())
                return
            self._commit_import(operation, row, source)
            return
        if operation["target_relpath"] != row["managed_relpath"]:
            raise MaterialConflictError("导入操作目标与资料路径不同。")
        expected_stage = f".staging/{operation['id']}/payload.part"
        if operation["staging_relpath"] != expected_stage:
            raise MaterialConflictError("导入暂存路径与操作 ID 不同。")
        target = self._managed(row)
        staged = storage.relative_file(self.root, expected_stage)
        if target.exists() and staged.exists():
            raise MaterialConflictError("暂存与最终文件同时存在，需要人工核对；不会自动删除任何一个。")
        if not target.exists():
            if not staged.exists():
                self._failed(operation["id"], row["id"], FileNotFoundError())
                return
            size, digest = storage.hash_file(staged)
            if digest != operation["expected_sha256"] or size != row["size_bytes"]:
                raise MaterialConflictError("暂存文件不完整或内容变化。")
            self._promote(staged, target)
            self._operation_state(operation["id"], "promoted")
        self._commit_import(operation, row, target)
