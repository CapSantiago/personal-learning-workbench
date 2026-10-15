"""Real SQLite integration tests using only fresh project-local synthetic M1 data."""

from contextlib import closing
import hashlib
import os
from pathlib import Path
import sqlite3
import uuid

import pytest

from plw import db


NOW = "2026-10-11T00:00:00+00:00"


@pytest.fixture(autouse=True)
def core_migration_contract(monkeypatch):
    """Keep original M1 migration/older-app tests against the immutable v1 schema.

    Current-schema and v1-to-current restore tests live in test_workbench.py.
    """
    original = db._load_migrations
    monkeypatch.setattr(db, '_load_migrations', lambda: original()[:1])


def uid():
    return str(uuid.uuid4())


@pytest.fixture
def db_path():
    return db.PROJECT_ROOT / ".sandbox" / "test-runs" / ("m1-db-" + uid()) / "合成 学习.sqlite3"


@pytest.fixture
def initialized(db_path):
    assert db.initialize(db_path) == 1
    return db_path


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def insert_semester(connection):
    identity = uid()
    connection.execute(
        "INSERT INTO semesters(id,name,created_at,updated_at) VALUES (?,?,?,?)",
        (identity, "合成学期", NOW, NOW),
    )
    return identity


def insert_course(connection, semester):
    identity = uid()
    connection.execute(
        "INSERT INTO courses(id,semester_id,name,created_at,updated_at) VALUES (?,?,?,?,?)",
        (identity, semester, "合成课程", NOW, NOW),
    )
    return identity


def setup_courses(path):
    with db.transaction(path) as connection:
        semester = insert_semester(connection)
        return semester, insert_course(connection, semester), insert_course(connection, semester)


def insert_chapter(connection, course, parent=None):
    identity = uid()
    connection.execute(
        "INSERT INTO chapters(id,course_id,parent_id,title,created_at,updated_at) VALUES (?,?,?,?,?,?)",
        (identity, course, parent, "合成章节", NOW, NOW),
    )
    return identity


def insert_note(connection, course, *, chapter=None, revision=None):
    identity = uid()
    connection.execute(
        """INSERT INTO notes(id,course_id,chapter_id,title,current_revision_id,created_at,updated_at)
           VALUES (?,?,?,?,?,?,?)""",
        (identity, course, chapter, "合成笔记", revision, NOW, NOW),
    )
    return identity


def insert_revision(connection, note, identity=None, number=1, source=None):
    identity = identity or uid()
    connection.execute(
        """INSERT INTO note_revisions
           (id,note_id,revision_no,body_relpath,sha256,size_bytes,created_at,source_revision_id)
           VALUES (?,?,?,?,?,?,?,?)""",
        (identity, note, number, f"notes/{note}/{identity}.md", "a" * 64, 12, NOW, source),
    )
    return identity


def insert_material(connection, course):
    identity = uid()
    connection.execute(
        """INSERT INTO materials
           (id,course_id,name,storage_mode,original_path,managed_relpath,created_at,updated_at)
           VALUES (?,?,?,'managed_copy',?,?,?,?)""",
        (identity, course, "合成资料", "E:/synthetic/source.txt", f"managed/{identity}/sample.txt", NOW, NOW),
    )
    return identity


def migration(version, sql):
    return db.Migration(version, f"{version:03d}_synthetic.sql", sql,
                        hashlib.sha256(sql.encode("utf-8")).hexdigest())


def test_read_absent_database_creates_nothing(db_path):
    with pytest.raises(db.DatabaseNotInitializedError):
        db.connect(db_path, read_only=True)
    with pytest.raises(db.DatabaseNotInitializedError):
        with db.transaction(db_path, write=False):
            pass
    assert not db_path.parent.exists()


@pytest.mark.parametrize("path", [
    Path("E:/PLW-Data/plw.sqlite3"),
    db.PROJECT_ROOT / ".sandbox" / "m0" / "probe.sqlite3",
    db.PROJECT_ROOT / "outside-m1.sqlite3",
    Path(".sandbox/m1/relative.sqlite3"),
])
def test_unapproved_database_path_rejected(path):
    with pytest.raises(db.DatabasePathError):
        db.initialize(path)


def test_every_connection_configuration_and_explicit_initialization(initialized):
    before = sha(initialized)
    assert db.initialize(initialized) == 1
    assert sha(initialized) == before
    for readonly in (False, True):
        with closing(db.connect(initialized, read_only=readonly)) as connection:
            assert connection.autocommit is True
            assert connection.row_factory is sqlite3.Row
            assert connection.execute("PRAGMA foreign_keys").fetchone()[0] == 1
            assert connection.execute("PRAGMA journal_mode").fetchone()[0] == "delete"
            assert connection.execute("PRAGMA synchronous").fetchone()[0] == 2
            assert connection.execute("PRAGMA busy_timeout").fetchone()[0] == 3000
            assert connection.execute("PRAGMA user_version").fetchone()[0] == 1
            assert connection.execute("PRAGMA application_id").fetchone()[0] == db.APPLICATION_ID
            assert connection.execute("PRAGMA foreign_key_check").fetchall() == []
            assert connection.execute("PRAGMA integrity_check").fetchone()[0] == "ok"


def test_complete_core_schema_and_reverse_indexes(initialized):
    with closing(db.connect(initialized, read_only=True)) as connection:
        tables = {row[0] for row in connection.execute("SELECT name FROM sqlite_schema WHERE type='table'")}
        assert tables == {
            "schema_migrations", "semesters", "courses", "materials", "tasks", "chapters",
            "knowledge_points", "notes", "note_revisions", "task_materials", "note_materials",
            "chapter_materials", "file_operations", "create_requests",
        }
        indexes = {row[0] for row in connection.execute("SELECT name FROM sqlite_schema WHERE type='index'")}
        assert {"idx_task_materials_material", "idx_note_materials_material",
                "idx_chapter_materials_material", "idx_chapters_course_parent",
                "idx_note_revisions_source"}.issubset(indexes)
        history = connection.execute("SELECT * FROM schema_migrations").fetchone()
        script = db._load_migrations()[0]
        assert history["version"] == 1
        assert history["name"] == script.name
        assert history["checksum"] == script.checksum
        assert history["app_version"] == db.APP_VERSION


def test_transaction_commit_rollback_and_connection_close(initialized):
    with db.transaction(initialized) as connection:
        assert connection.in_transaction
        semester = insert_semester(connection)
    with pytest.raises(sqlite3.ProgrammingError, match="closed"):
        connection.execute("SELECT 1")
    with pytest.raises(RuntimeError, match="synthetic failure"):
        with db.transaction(initialized) as connection:
            connection.execute("UPDATE semesters SET name='must rollback' WHERE id=?", (semester,))
            raise RuntimeError("synthetic failure")
    with db.transaction(initialized, write=False) as connection:
        assert connection.execute("SELECT name FROM semesters WHERE id=?", (semester,)).fetchone()[0] == "合成学期"
        with pytest.raises(sqlite3.OperationalError, match="readonly"):
            connection.execute("UPDATE semesters SET name='not permitted'")


def test_foreign_key_and_check_error_rollback_prior_changes(initialized):
    with pytest.raises(sqlite3.IntegrityError):
        with db.transaction(initialized) as connection:
            insert_semester(connection)
            insert_course(connection, uid())
    with db.transaction(initialized, write=False) as connection:
        assert connection.execute("SELECT count(*) FROM semesters").fetchone()[0] == 0


def test_competing_writer_times_out_without_changes(initialized, monkeypatch):
    monkeypatch.setattr(db, "BUSY_TIMEOUT_MS", 20)
    with closing(db.connect(initialized)) as owner:
        owner.execute("BEGIN IMMEDIATE")
        try:
            with pytest.raises(sqlite3.OperationalError, match="locked"):
                with db.transaction(initialized) as connection:
                    insert_semester(connection)
        finally:
            owner.execute("ROLLBACK")
    with db.transaction(initialized, write=False) as connection:
        assert connection.execute("SELECT count(*) FROM semesters").fetchone()[0] == 0


@pytest.mark.parametrize("field,value", [
    ("credits", -1), ("credits", 101), ("credits", float("inf")),
    ("status", "unknown"), ("revision", 0), ("name", "   "),
])
def test_course_checks(initialized, field, value):
    _, course, _ = setup_courses(initialized)
    with pytest.raises(sqlite3.IntegrityError):
        with db.transaction(initialized) as connection:
            connection.execute(f"UPDATE courses SET {field}=? WHERE id=?", (value, course))


def test_semester_date_checks_and_course_delete_restrict(initialized):
    semester, _, _ = setup_courses(initialized)
    with pytest.raises(sqlite3.IntegrityError):
        with db.transaction(initialized) as connection:
            connection.execute("UPDATE semesters SET start_date='2026-02-30' WHERE id=?", (semester,))
    with pytest.raises(sqlite3.IntegrityError):
        with db.transaction(initialized) as connection:
            connection.execute(
                "UPDATE semesters SET start_date='2026-10-11',end_date='2026-10-10' WHERE id=?", (semester,))
    with pytest.raises(sqlite3.IntegrityError):
        with db.transaction(initialized) as connection:
            connection.execute("DELETE FROM semesters WHERE id=?", (semester,))


def test_chapter_knowledge_note_same_course_and_cycles(initialized):
    _, course_a, course_b = setup_courses(initialized)
    with db.transaction(initialized) as connection:
        parent = insert_chapter(connection, course_a)
        child = insert_chapter(connection, course_a, parent)
    with pytest.raises(sqlite3.IntegrityError):
        with db.transaction(initialized) as connection:
            insert_chapter(connection, course_b, parent)
    with pytest.raises(sqlite3.IntegrityError, match="chapter cycle"):
        with db.transaction(initialized) as connection:
            connection.execute("UPDATE chapters SET parent_id=? WHERE id=?", (child, parent))
    with pytest.raises(sqlite3.IntegrityError):
        with db.transaction(initialized) as connection:
            connection.execute(
                "INSERT INTO knowledge_points(id,course_id,chapter_id,title,created_at,updated_at) VALUES (?,?,?,?,?,?)",
                (uid(), course_b, parent, "wrong course", NOW, NOW),
            )
    with pytest.raises(sqlite3.IntegrityError):
        with db.transaction(initialized) as connection:
            insert_note(connection, course_b, chapter=parent)
    with db.transaction(initialized) as connection:
        insert_note(connection, course_a, chapter=child)


def test_deferred_note_pointer_supports_atomic_first_revision(initialized):
    _, course, _ = setup_courses(initialized)
    revision = uid()
    with db.transaction(initialized) as connection:
        note = insert_note(connection, course, revision=revision)
        assert connection.in_transaction
        insert_revision(connection, note, identity=revision)
    with db.transaction(initialized, write=False) as connection:
        assert connection.execute("SELECT current_revision_id FROM notes WHERE id=?", (note,)).fetchone()[0] == revision
        assert connection.execute("PRAGMA foreign_key_check").fetchall() == []


def test_actual_failed_deferred_commit_rolls_back_whole_work_unit(initialized):
    _, course, _ = setup_courses(initialized)
    with pytest.raises(sqlite3.IntegrityError, match="FOREIGN KEY"):
        with db.transaction(initialized) as connection:
            note = insert_note(connection, course, revision=uid())
            connection.execute("UPDATE courses SET name='must rollback' WHERE id=?", (course,))
            # No error until transaction() explicitly executes SQL COMMIT.
    with db.transaction(initialized, write=False) as connection:
        assert connection.execute("SELECT 1 FROM notes WHERE id=?", (note,)).fetchone() is None
        assert connection.execute("SELECT name FROM courses WHERE id=?", (course,)).fetchone()[0] == "合成课程"


def test_revision_pointer_and_restore_source_cannot_cross_notes(initialized):
    _, course, _ = setup_courses(initialized)
    with db.transaction(initialized) as connection:
        note_a = insert_note(connection, course)
        note_b = insert_note(connection, course)
        revision = insert_revision(connection, note_a)
    with pytest.raises(sqlite3.IntegrityError):
        with db.transaction(initialized) as connection:
            connection.execute("UPDATE notes SET current_revision_id=? WHERE id=?", (revision, note_b))
    with pytest.raises(sqlite3.IntegrityError):
        with db.transaction(initialized) as connection:
            insert_revision(connection, note_b, source=revision)


def test_material_associations_allow_cross_course_and_prevent_duplicates(initialized):
    _, course_a, course_b = setup_courses(initialized)
    with db.transaction(initialized) as connection:
        material = insert_material(connection, course_a)
        chapter = insert_chapter(connection, course_b)
        note = insert_note(connection, course_b, chapter=chapter)
        task = uid()
        connection.execute(
            "INSERT INTO tasks(id,course_id,title,task_type,created_at,updated_at) VALUES (?,?,?,?,?,?)",
            (task, course_b, "synthetic cross-course task", "lab", NOW, NOW),
        )
        for table, left in (("task_materials", task), ("note_materials", note), ("chapter_materials", chapter)):
            connection.execute(f"INSERT INTO {table} VALUES (?,?)", (left, material))
            with pytest.raises(sqlite3.IntegrityError):
                connection.execute(f"INSERT INTO {table} VALUES (?,?)", (left, material))
    with db.transaction(initialized, write=False) as connection:
        assert connection.execute("PRAGMA foreign_key_check").fetchall() == []
        for table in ("task_materials", "note_materials", "chapter_materials"):
            assert connection.execute(f"SELECT count(*) FROM {table}").fetchone()[0] == 1


@pytest.mark.parametrize("relative", ["../escape", "managed/../../escape", "/absolute", "E:/absolute", r"managed\sample", "managed//sample"])
def test_managed_path_constraint(initialized, relative):
    _, course, _ = setup_courses(initialized)
    with pytest.raises(sqlite3.IntegrityError):
        with db.transaction(initialized) as connection:
            material = insert_material(connection, course)
            connection.execute("UPDATE materials SET managed_relpath=? WHERE id=?", (relative, material))


def test_storage_mode_hash_and_file_deletion_checks(initialized):
    _, course, _ = setup_courses(initialized)
    with db.transaction(initialized) as connection:
        material = insert_material(connection, course)
    for statement in (
        "UPDATE materials SET storage_mode='external_reference'",
        "UPDATE materials SET baseline_sha256=''",
        "UPDATE materials SET size_bytes=-1",
        "UPDATE materials SET file_deleted_at='2026-10-11T00:00:00Z'",
    ):
        with pytest.raises(sqlite3.IntegrityError):
            with db.transaction(initialized) as connection:
                connection.execute(statement + " WHERE id=?", (material,))


def test_task_deadline_and_duration_checks(initialized):
    _, course, _ = setup_courses(initialized)
    task = uid()
    with db.transaction(initialized) as connection:
        connection.execute(
            "INSERT INTO tasks(id,course_id,title,task_type,created_at,updated_at) VALUES (?,?,?,?,?,?)",
            (task, course, "synthetic task", "exam", NOW, NOW),
        )
    invalid = [
        ("due_kind='date'", ()),
        ("due_kind='date',due_date=?", ("2026-02-30",)),
        ("due_kind='datetime',due_at_utc=?", (NOW,)),
        ("actual_minutes=-1", ()),
        ("estimated_minutes=0.5", ()),
        ("status='done'", ()),
    ]
    for assignment, parameters in invalid:
        with pytest.raises(sqlite3.IntegrityError):
            with db.transaction(initialized) as connection:
                connection.execute(f"UPDATE tasks SET {assignment} WHERE id=?", (*parameters, task))
    with db.transaction(initialized) as connection:
        connection.execute("UPDATE tasks SET due_kind='date',due_date='2026-10-11' WHERE id=?", (task,))
        connection.execute(
            "UPDATE tasks SET due_kind='datetime',due_date=NULL,due_at_utc=?,due_timezone='Asia/Shanghai' WHERE id=?",
            (NOW, task),
        )


def test_new_database_failed_migration_leaves_no_partial_schema_or_metadata(db_path, monkeypatch):
    real = db._load_migrations()
    broken = migration(1, real[0].sql + "\nCREATE TABLE partial_work(id INTEGER);\nINVALID SYNTHETIC SQL;\n")
    with monkeypatch.context() as patch:
        patch.setattr(db, "_load_migrations", lambda: (broken,))
        with pytest.raises(db.SchemaError, match="rolled back"):
            db.initialize(db_path)
    with closing(sqlite3.connect(db_path, autocommit=True)) as connection:
        assert connection.execute("SELECT name FROM sqlite_schema WHERE name NOT GLOB 'sqlite_*'").fetchall() == []
        assert connection.execute("PRAGMA application_id").fetchone()[0] == 0
        assert connection.execute("PRAGMA user_version").fetchone()[0] == 0
    assert db.initialize(db_path) == 1


def test_upgrade_failure_rolls_back_ddl_data_history_and_version(initialized, monkeypatch):
    semester, _, _ = setup_courses(initialized)
    real = db._load_migrations()
    broken = migration(2, """CREATE TABLE partial_upgrade(id INTEGER);
        INSERT INTO partial_upgrade VALUES(1);
        UPDATE semesters SET name='must rollback';
        INVALID SYNTHETIC SQL;""")
    with monkeypatch.context() as patch:
        patch.setattr(db, "_load_migrations", lambda: (*real, broken))
        with pytest.raises(db.SchemaError, match="rolled back"):
            db.initialize(initialized)
    with db.transaction(initialized, write=False) as connection:
        assert connection.execute("SELECT 1 FROM sqlite_schema WHERE name='partial_upgrade'").fetchone() is None
        assert connection.execute("SELECT name FROM semesters WHERE id=?", (semester,)).fetchone()[0] == "合成学期"
        assert connection.execute("SELECT count(*) FROM schema_migrations").fetchone()[0] == 1
        assert connection.execute("PRAGMA user_version").fetchone()[0] == 1


@pytest.mark.parametrize("escape_sql", [
    "COMMIT;", "ROLLBACK;", "SAVEPOINT escaped;", "PRAGMA user_version=99;",
    "ATTACH DATABASE ':memory:' AS forbidden;",
])
def test_migration_cannot_escape_transaction(initialized, monkeypatch, escape_sql):
    real = db._load_migrations()
    broken = migration(2, "CREATE TABLE must_not_escape(id INTEGER);\n" + escape_sql)
    with monkeypatch.context() as patch:
        patch.setattr(db, "_load_migrations", lambda: (*real, broken))
        with pytest.raises(db.SchemaError, match="rolled back"):
            db.initialize(initialized)
    with db.transaction(initialized, write=False) as connection:
        assert connection.execute("SELECT 1 FROM sqlite_schema WHERE name='must_not_escape'").fetchone() is None
        assert connection.execute("PRAGMA user_version").fetchone()[0] == 1


def test_successful_upgrade_and_older_app_rejection(initialized, monkeypatch):
    real = db._load_migrations()
    second = migration(2, "CREATE TABLE synthetic_upgrade(id INTEGER);INSERT INTO synthetic_upgrade VALUES(1);")
    with monkeypatch.context() as patch:
        patch.setattr(db, "_load_migrations", lambda: (*real, second))
        # A read connection never silently applies pending upgrades.
        with pytest.raises(db.DatabaseNotInitializedError, match="Pending"):
            db.connect(initialized, read_only=True)
        assert db.initialize(initialized) == 2
        with db.transaction(initialized, write=False) as connection:
            assert connection.execute("SELECT count(*) FROM schema_migrations").fetchone()[0] == 2
            assert connection.execute("PRAGMA user_version").fetchone()[0] == 2
    before = sha(initialized)
    with pytest.raises(db.SchemaError, match="newer"):
        db.initialize(initialized)
    assert sha(initialized) == before


@pytest.mark.parametrize("tamper", [
    "PRAGMA user_version=99",
    "UPDATE schema_migrations SET checksum='aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa'",
    "UPDATE schema_migrations SET name='001_edited.sql'",
    "DELETE FROM schema_migrations",
    "PRAGMA user_version=0",
])
def test_schema_tampering_refused_without_writes(initialized, tamper):
    with closing(sqlite3.connect(initialized, autocommit=True)) as connection:
        connection.execute(tamper)
    before = sha(initialized)
    for action in (db.initialize, lambda path: db.connect(path, read_only=True), db.connect):
        with pytest.raises(db.SchemaError):
            action(initialized)
        assert sha(initialized) == before


def test_edited_applied_script_refused_before_write(initialized, monkeypatch):
    script = db._load_migrations()[0]
    edited = db.Migration(script.version, script.name, script.sql + "\n-- edited\n", "b" * 64)
    monkeypatch.setattr(db, "_load_migrations", lambda: (edited,))
    before = sha(initialized)
    with pytest.raises(db.SchemaError, match="checksum"):
        db.initialize(initialized)
    assert sha(initialized) == before


def test_missing_bundled_migration_version_rejected_before_database_creation(db_path, monkeypatch):
    directory = db_path.parent / "synthetic-migrations"
    directory.mkdir(parents=True)
    (directory / "001_first.sql").write_text("CREATE TABLE first(id INTEGER);", encoding="utf-8")
    (directory / "003_gap.sql").write_text("CREATE TABLE third(id INTEGER);", encoding="utf-8")
    monkeypatch.setattr(db, "_MIGRATIONS_DIR", directory)
    with pytest.raises(db.SchemaError, match="contiguous"):
        db.initialize(db_path)
    assert not db_path.exists()


def test_history_gap_rejected_without_modifying_database(initialized, monkeypatch):
    real = db._load_migrations()
    second = migration(2, "CREATE TABLE synthetic_second(id INTEGER);")
    monkeypatch.setattr(db, "_load_migrations", lambda: (*real, second))
    assert db.initialize(initialized) == 2
    with closing(sqlite3.connect(initialized, autocommit=True)) as connection:
        connection.execute("DELETE FROM schema_migrations WHERE version=1")
    before = sha(initialized)
    with pytest.raises(db.SchemaError, match="missing"):
        db.initialize(initialized)
    assert sha(initialized) == before


def test_unknown_database_and_wal_not_converted(db_path):
    db_path.parent.mkdir(parents=True)
    with closing(sqlite3.connect(db_path, autocommit=True)) as connection:
        connection.execute("CREATE TABLE unrelated_synthetic_data(id INTEGER)")
        connection.execute("PRAGMA journal_mode=WAL")
    before = sha(db_path)
    with pytest.raises(db.SchemaError):
        db.initialize(db_path)
    assert sha(db_path) == before
    with closing(sqlite3.connect(db_path, autocommit=True)) as connection:
        assert connection.execute("PRAGMA journal_mode").fetchone()[0] == "wal"


def test_database_hardlink_rejected(initialized):
    linked = initialized.with_name("linked.sqlite3")
    os.link(initialized, linked)
    for path in (initialized, linked):
        with pytest.raises(db.DatabasePathError, match="one link"):
            db.connect(path)


def test_database_junction_and_sidecar_hardlink_rejected(db_path):
    if os.name != "nt":
        pytest.skip("Actual Windows junction boundary")
    import _winapi

    db_path.parent.mkdir(parents=True)
    target = db_path.parent / "synthetic-target"
    target.mkdir()
    junction = db_path.parent / "synthetic-junction"
    _winapi.CreateJunction(str(target), str(junction))
    with pytest.raises(db.DatabasePathError, match="Reparse"):
        db.initialize(junction / "not-created.sqlite3")
    assert not (target / "not-created.sqlite3").exists()
    source = db_path.parent / "synthetic-sidecar-source"
    source.write_bytes(b"synthetic only")
    os.link(source, db_path.with_name(db_path.name + "-journal"))
    with pytest.raises(db.DatabasePathError, match="one link"):
        db.initialize(db_path)
    assert not db_path.exists()
