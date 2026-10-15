-- M1 relational foundation. Only semesters/courses have implemented services.
-- Files, notes, tasks and recovery metadata are schema only, never filesystem actions.
CREATE TABLE semesters (
    id TEXT PRIMARY KEY NOT NULL CHECK(length(id) = 36),
    name TEXT NOT NULL CHECK(length(trim(name)) BETWEEN 1 AND 200),
    start_date TEXT CHECK(start_date IS NULL OR
        (length(start_date)=10 AND date(start_date,'+0 days') IS NOT NULL AND date(start_date,'+0 days')=start_date)),
    end_date TEXT CHECK(end_date IS NULL OR
        (length(end_date)=10 AND date(end_date,'+0 days') IS NOT NULL AND date(end_date,'+0 days')=end_date)),
    archived_at TEXT CHECK(archived_at IS NULL OR
        (datetime(archived_at) IS NOT NULL AND (substr(archived_at,-1)='Z' OR substr(archived_at,-6)='+00:00'))),
    created_at TEXT NOT NULL CHECK(datetime(created_at) IS NOT NULL AND
        (substr(created_at,-1)='Z' OR substr(created_at,-6)='+00:00')),
    updated_at TEXT NOT NULL CHECK(datetime(updated_at) IS NOT NULL AND
        (substr(updated_at,-1)='Z' OR substr(updated_at,-6)='+00:00')),
    revision INTEGER NOT NULL DEFAULT 1 CHECK(typeof(revision)='integer' AND revision>=1),
    CHECK(start_date IS NULL OR end_date IS NULL OR end_date>=start_date)
);

CREATE TABLE courses (
    id TEXT PRIMARY KEY NOT NULL CHECK(length(id)=36),
    semester_id TEXT NOT NULL REFERENCES semesters(id) ON DELETE RESTRICT,
    name TEXT NOT NULL CHECK(length(trim(name)) BETWEEN 1 AND 200),
    teacher TEXT NOT NULL DEFAULT '',
    credits REAL CHECK(credits IS NULL OR
        (typeof(credits) IN ('integer','real') AND credits>=0 AND credits<=100)),
    schedule_text TEXT NOT NULL DEFAULT '',
    assessment TEXT NOT NULL DEFAULT '',
    status TEXT NOT NULL DEFAULT 'planned' CHECK(status IN ('planned','active','completed','paused')),
    remarks TEXT NOT NULL DEFAULT '',
    archived_at TEXT CHECK(archived_at IS NULL OR
        (datetime(archived_at) IS NOT NULL AND (substr(archived_at,-1)='Z' OR substr(archived_at,-6)='+00:00'))),
    created_at TEXT NOT NULL CHECK(datetime(created_at) IS NOT NULL AND
        (substr(created_at,-1)='Z' OR substr(created_at,-6)='+00:00')),
    updated_at TEXT NOT NULL CHECK(datetime(updated_at) IS NOT NULL AND
        (substr(updated_at,-1)='Z' OR substr(updated_at,-6)='+00:00')),
    revision INTEGER NOT NULL DEFAULT 1 CHECK(typeof(revision)='integer' AND revision>=1)
);
CREATE INDEX idx_courses_semester_name ON courses(semester_id,name);
CREATE INDEX idx_courses_status_archived ON courses(status,archived_at);

CREATE TABLE materials (
    id TEXT PRIMARY KEY NOT NULL CHECK(length(id)=36),
    course_id TEXT NOT NULL REFERENCES courses(id) ON DELETE RESTRICT,
    name TEXT NOT NULL CHECK(length(trim(name)) BETWEEN 1 AND 500),
    material_type TEXT NOT NULL DEFAULT 'other' CHECK(material_type IN
        ('slides','textbook','assignment','lab_guide','exam_paper','code','other')),
    storage_mode TEXT NOT NULL CHECK(storage_mode IN ('managed_copy','external_reference')),
    original_path TEXT NOT NULL CHECK(length(original_path)>=4 AND
        substr(original_path,1,1) GLOB '[A-Za-z]' AND substr(original_path,2,1)=':' AND
        substr(original_path,3,1) IN ('/','\') AND instr(substr(original_path,3),':')=0),
    reference_path TEXT CHECK(reference_path IS NULL OR
        (length(reference_path)>=4 AND substr(reference_path,1,1) GLOB '[A-Za-z]' AND
        substr(reference_path,2,1)=':' AND substr(reference_path,3,1) IN ('/','\') AND
        instr(substr(reference_path,3),':')=0)),
    managed_relpath TEXT UNIQUE CHECK(managed_relpath IS NULL OR
        (length(managed_relpath)>0 AND substr(managed_relpath,1,1)<>'/' AND
        instr(managed_relpath,'\')=0 AND instr(managed_relpath,':')=0 AND
        managed_relpath NOT IN ('.','..') AND managed_relpath NOT LIKE '../%' AND
        managed_relpath NOT LIKE '%/../%' AND managed_relpath NOT LIKE '%/..' AND
        managed_relpath NOT LIKE './%' AND managed_relpath NOT LIKE '%/./%' AND
        managed_relpath NOT LIKE '%/.' AND managed_relpath NOT LIKE '%//%')),
    size_bytes INTEGER CHECK(size_bytes IS NULL OR (typeof(size_bytes)='integer' AND size_bytes>=0)),
    mtime_ns INTEGER CHECK(mtime_ns IS NULL OR (typeof(mtime_ns)='integer' AND mtime_ns>=0)),
    baseline_sha256 TEXT CHECK(baseline_sha256 IS NULL OR
        (length(baseline_sha256)=64 AND baseline_sha256 NOT GLOB '*[^0-9a-f]*')),
    observed_sha256 TEXT CHECK(observed_sha256 IS NULL OR
        (length(observed_sha256)=64 AND observed_sha256 NOT GLOB '*[^0-9a-f]*')),
    hash_checked_at TEXT,
    file_status TEXT NOT NULL DEFAULT 'unchecked' CHECK(file_status IN
        ('normal','missing','inaccessible','possibly_changed','unchecked')),
    last_checked_at TEXT,
    last_error_code TEXT,
    import_state TEXT NOT NULL DEFAULT 'pending' CHECK(import_state IN ('pending','ready','failed')),
    deleted_at TEXT,
    file_deleted_at TEXT,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL,
    CHECK((storage_mode='managed_copy' AND managed_relpath IS NOT NULL AND reference_path IS NULL)
        OR (storage_mode='external_reference' AND reference_path IS NOT NULL AND managed_relpath IS NULL)),
    CHECK(file_deleted_at IS NULL OR (storage_mode='managed_copy' AND deleted_at IS NOT NULL))
);
CREATE INDEX idx_materials_course_name ON materials(course_id,name);
CREATE INDEX idx_materials_status ON materials(import_state,file_status,deleted_at);

CREATE TABLE tasks (
    id TEXT PRIMARY KEY NOT NULL CHECK(length(id)=36),
    course_id TEXT NOT NULL REFERENCES courses(id) ON DELETE RESTRICT,
    title TEXT NOT NULL CHECK(length(trim(title)) BETWEEN 1 AND 500),
    task_type TEXT NOT NULL CHECK(task_type IN ('assignment','lab','exam','preview','review','project')),
    due_kind TEXT NOT NULL DEFAULT 'none' CHECK(due_kind IN ('none','date','datetime')),
    due_date TEXT CHECK(due_date IS NULL OR
        (length(due_date)=10 AND date(due_date,'+0 days') IS NOT NULL AND date(due_date,'+0 days')=due_date)),
    due_at_utc TEXT CHECK(due_at_utc IS NULL OR
        (datetime(due_at_utc) IS NOT NULL AND (substr(due_at_utc,-1)='Z' OR substr(due_at_utc,-6)='+00:00'))),
    due_timezone TEXT CHECK(due_timezone IS NULL OR length(trim(due_timezone)) BETWEEN 1 AND 100),
    planned_date TEXT CHECK(planned_date IS NULL OR
        (length(planned_date)=10 AND date(planned_date,'+0 days') IS NOT NULL AND date(planned_date,'+0 days')=planned_date)),
    priority TEXT NOT NULL DEFAULT 'normal' CHECK(priority IN ('low','normal','high')),
    status TEXT NOT NULL DEFAULT 'todo' CHECK(status IN ('todo','doing','done','cancelled')),
    estimated_minutes INTEGER CHECK(estimated_minutes IS NULL OR
        (typeof(estimated_minutes)='integer' AND estimated_minutes>=0)),
    actual_minutes INTEGER NOT NULL DEFAULT 0 CHECK(typeof(actual_minutes)='integer' AND actual_minutes>=0),
    remarks TEXT NOT NULL DEFAULT '',
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL,
    completed_at TEXT,
    CHECK((due_kind='none' AND due_date IS NULL AND due_at_utc IS NULL AND due_timezone IS NULL)
        OR (due_kind='date' AND due_date IS NOT NULL AND due_at_utc IS NULL AND due_timezone IS NULL)
        OR (due_kind='datetime' AND due_date IS NULL AND due_at_utc IS NOT NULL AND due_timezone IS NOT NULL)),
    CHECK((status='done' AND completed_at IS NOT NULL) OR (status<>'done' AND completed_at IS NULL))
);
CREATE INDEX idx_tasks_course ON tasks(course_id);
CREATE INDEX idx_tasks_status_date ON tasks(status,due_date);
CREATE INDEX idx_tasks_status_instant ON tasks(status,due_at_utc);
CREATE INDEX idx_tasks_planned ON tasks(planned_date);

CREATE TABLE chapters (
    id TEXT PRIMARY KEY NOT NULL CHECK(length(id)=36),
    course_id TEXT NOT NULL REFERENCES courses(id) ON DELETE RESTRICT,
    parent_id TEXT,
    title TEXT NOT NULL CHECK(length(trim(title)) BETWEEN 1 AND 500),
    position INTEGER NOT NULL DEFAULT 0 CHECK(typeof(position)='integer' AND position>=0),
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL,
    UNIQUE(course_id,id),
    FOREIGN KEY(course_id,parent_id) REFERENCES chapters(course_id,id) ON DELETE RESTRICT,
    CHECK(parent_id IS NULL OR parent_id<>id)
);
CREATE INDEX idx_chapters_course_parent ON chapters(course_id,parent_id);

CREATE TRIGGER chapters_no_cycle_insert BEFORE INSERT ON chapters
WHEN NEW.parent_id IS NOT NULL
BEGIN
    SELECT RAISE(ABORT,'chapter cycle')
    WHERE NEW.parent_id=NEW.id OR EXISTS (
        WITH RECURSIVE ancestors(id,parent_id) AS (
            SELECT id,parent_id FROM chapters WHERE course_id=NEW.course_id AND id=NEW.parent_id
            UNION
            SELECT c.id,c.parent_id FROM chapters c JOIN ancestors a ON c.id=a.parent_id
            WHERE c.course_id=NEW.course_id
        ) SELECT 1 FROM ancestors WHERE id=NEW.id
    );
END;

CREATE TRIGGER chapters_no_cycle_update BEFORE UPDATE OF parent_id,course_id ON chapters
WHEN NEW.parent_id IS NOT NULL
BEGIN
    SELECT RAISE(ABORT,'chapter cycle')
    WHERE NEW.parent_id=NEW.id OR EXISTS (
        WITH RECURSIVE ancestors(id,parent_id) AS (
            SELECT id,parent_id FROM chapters WHERE course_id=NEW.course_id AND id=NEW.parent_id
            UNION
            SELECT c.id,c.parent_id FROM chapters c JOIN ancestors a ON c.id=a.parent_id
            WHERE c.course_id=NEW.course_id
        ) SELECT 1 FROM ancestors WHERE id=NEW.id
    );
END;

CREATE TABLE knowledge_points (
    id TEXT PRIMARY KEY NOT NULL CHECK(length(id)=36),
    course_id TEXT NOT NULL REFERENCES courses(id) ON DELETE RESTRICT,
    chapter_id TEXT,
    title TEXT NOT NULL CHECK(length(trim(title)) BETWEEN 1 AND 500),
    learning_state TEXT NOT NULL DEFAULT 'not_started' CHECK(learning_state IN
        ('not_started','learning','understood_not_applied','mastered')),
    remarks TEXT NOT NULL DEFAULT '',
    updated_at TEXT NOT NULL,
    created_at TEXT NOT NULL,
    FOREIGN KEY(course_id,chapter_id) REFERENCES chapters(course_id,id) ON DELETE RESTRICT
);
CREATE INDEX idx_knowledge_course_chapter ON knowledge_points(course_id,chapter_id);

CREATE TABLE notes (
    id TEXT PRIMARY KEY NOT NULL CHECK(length(id)=36),
    course_id TEXT NOT NULL REFERENCES courses(id) ON DELETE RESTRICT,
    chapter_id TEXT,
    title TEXT NOT NULL CHECK(length(trim(title)) BETWEEN 1 AND 500),
    current_revision_id TEXT,
    version INTEGER NOT NULL DEFAULT 1 CHECK(typeof(version)='integer' AND version>=1),
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL,
    deleted_at TEXT,
    FOREIGN KEY(course_id,chapter_id) REFERENCES chapters(course_id,id) ON DELETE RESTRICT,
    FOREIGN KEY(id,current_revision_id) REFERENCES note_revisions(note_id,id)
        DEFERRABLE INITIALLY DEFERRED
);
CREATE INDEX idx_notes_course_chapter ON notes(course_id,chapter_id);
CREATE INDEX idx_notes_updated ON notes(updated_at);
CREATE INDEX idx_notes_current_revision ON notes(id,current_revision_id);

CREATE TABLE note_revisions (
    id TEXT PRIMARY KEY NOT NULL CHECK(length(id)=36),
    note_id TEXT NOT NULL REFERENCES notes(id) ON DELETE RESTRICT,
    revision_no INTEGER NOT NULL CHECK(typeof(revision_no)='integer' AND revision_no>=1),
    body_relpath TEXT NOT NULL UNIQUE CHECK(
        length(body_relpath)>0 AND substr(body_relpath,1,1)<>'/' AND
        instr(body_relpath,'\')=0 AND instr(body_relpath,':')=0 AND
        body_relpath NOT IN ('.','..') AND body_relpath NOT LIKE '../%' AND
        body_relpath NOT LIKE '%/../%' AND body_relpath NOT LIKE '%/..' AND
        body_relpath NOT LIKE './%' AND body_relpath NOT LIKE '%/./%' AND
        body_relpath NOT LIKE '%/.' AND body_relpath NOT LIKE '%//%'),
    sha256 TEXT NOT NULL CHECK(length(sha256)=64 AND sha256 NOT GLOB '*[^0-9a-f]*'),
    size_bytes INTEGER NOT NULL CHECK(typeof(size_bytes)='integer' AND size_bytes>=0),
    created_at TEXT NOT NULL,
    source_revision_id TEXT,
    UNIQUE(note_id,revision_no),
    UNIQUE(note_id,id),
    FOREIGN KEY(note_id,source_revision_id) REFERENCES note_revisions(note_id,id) ON DELETE RESTRICT,
    CHECK(source_revision_id IS NULL OR source_revision_id<>id)
);
CREATE INDEX idx_note_revisions_source ON note_revisions(note_id,source_revision_id);

CREATE TABLE task_materials (
    task_id TEXT NOT NULL REFERENCES tasks(id) ON DELETE CASCADE,
    material_id TEXT NOT NULL REFERENCES materials(id) ON DELETE CASCADE,
    PRIMARY KEY(task_id,material_id)
);
CREATE INDEX idx_task_materials_material ON task_materials(material_id);
CREATE TABLE note_materials (
    note_id TEXT NOT NULL REFERENCES notes(id) ON DELETE CASCADE,
    material_id TEXT NOT NULL REFERENCES materials(id) ON DELETE CASCADE,
    PRIMARY KEY(note_id,material_id)
);
CREATE INDEX idx_note_materials_material ON note_materials(material_id);
CREATE TABLE chapter_materials (
    chapter_id TEXT NOT NULL REFERENCES chapters(id) ON DELETE CASCADE,
    material_id TEXT NOT NULL REFERENCES materials(id) ON DELETE CASCADE,
    PRIMARY KEY(chapter_id,material_id)
);
CREATE INDEX idx_chapter_materials_material ON chapter_materials(material_id);

CREATE TABLE file_operations (
    id TEXT PRIMARY KEY NOT NULL CHECK(length(id)=36),
    request_id TEXT NOT NULL UNIQUE CHECK(length(request_id)=36),
    kind TEXT NOT NULL CHECK(kind IN ('import_material','save_note','delete_managed_file')),
    entity_id TEXT NOT NULL CHECK(length(entity_id)=36),
    state TEXT NOT NULL CHECK(state IN ('planned','staged','promoted','committed','failed','quarantined')),
    staging_relpath TEXT CHECK(staging_relpath IS NULL OR
        (length(staging_relpath)>0 AND substr(staging_relpath,1,1)<>'/' AND
        instr(staging_relpath,'\')=0 AND instr(staging_relpath,':')=0 AND
        staging_relpath NOT IN ('.','..') AND staging_relpath NOT LIKE '../%' AND
        staging_relpath NOT LIKE '%/../%' AND staging_relpath NOT LIKE '%/..' AND
        staging_relpath NOT LIKE './%' AND staging_relpath NOT LIKE '%/./%' AND
        staging_relpath NOT LIKE '%/.' AND staging_relpath NOT LIKE '%//%')),
    target_relpath TEXT CHECK(target_relpath IS NULL OR
        (length(target_relpath)>0 AND substr(target_relpath,1,1)<>'/' AND
        instr(target_relpath,'\')=0 AND instr(target_relpath,':')=0 AND
        target_relpath NOT IN ('.','..') AND target_relpath NOT LIKE '../%' AND
        target_relpath NOT LIKE '%/../%' AND target_relpath NOT LIKE '%/..' AND
        target_relpath NOT LIKE './%' AND target_relpath NOT LIKE '%/./%' AND
        target_relpath NOT LIKE '%/.' AND target_relpath NOT LIKE '%//%')),
    expected_sha256 TEXT CHECK(expected_sha256 IS NULL OR
        (length(expected_sha256)=64 AND expected_sha256 NOT GLOB '*[^0-9a-f]*')),
    payload_json TEXT NOT NULL DEFAULT '{}' CHECK(json_valid(payload_json)),
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL,
    error_code TEXT
);
CREATE INDEX idx_file_operations_state ON file_operations(state,updated_at);
CREATE INDEX idx_file_operations_entity ON file_operations(entity_id);

-- Initial normalized request payload survives subsequent entity edits.
-- The service inserts both rows in one transaction; this polymorphic key has no FK.
CREATE TABLE create_requests (
    request_id TEXT PRIMARY KEY NOT NULL CHECK(length(request_id)=36),
    entity_kind TEXT NOT NULL CHECK(entity_kind IN ('semester','course')),
    payload_json TEXT NOT NULL CHECK(json_valid(payload_json)),
    payload_hash TEXT NOT NULL CHECK(length(payload_hash)=64 AND payload_hash NOT GLOB '*[^0-9a-f]*'),
    entity_id TEXT NOT NULL CHECK(entity_id=request_id),
    created_at TEXT NOT NULL,
    UNIQUE(entity_kind,entity_id)
);
