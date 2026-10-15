-- Copy rows unchanged; only admit POSIX source metadata in addition to Windows paths.
-- The runner disables FK enforcement before BEGIN and checks all relations before COMMIT.
CREATE TABLE materials_v4 (
    id TEXT PRIMARY KEY NOT NULL CHECK(length(id)=36),
    course_id TEXT NOT NULL REFERENCES courses(id) ON DELETE RESTRICT,
    name TEXT NOT NULL CHECK(length(trim(name)) BETWEEN 1 AND 500),
    material_type TEXT NOT NULL DEFAULT 'other' CHECK(material_type IN
        ('slides','textbook','assignment','lab_guide','exam_paper','code','other')),
    storage_mode TEXT NOT NULL CHECK(storage_mode IN ('managed_copy','external_reference')),
    original_path TEXT NOT NULL CHECK(
        (length(original_path)>=4 AND substr(original_path,1,1) GLOB '[A-Za-z]' AND
         substr(original_path,2,1)=':' AND substr(original_path,3,1) IN ('/','\') AND instr(substr(original_path,3),':')=0)
        OR (substr(original_path,1,1)='/' AND length(original_path)>1 AND instr(original_path,':')=0 AND instr(original_path,'\')=0)),
    reference_path TEXT CHECK(reference_path IS NULL OR
        (length(reference_path)>=4 AND substr(reference_path,1,1) GLOB '[A-Za-z]' AND
         substr(reference_path,2,1)=':' AND substr(reference_path,3,1) IN ('/','\') AND instr(substr(reference_path,3),':')=0)
        OR (substr(reference_path,1,1)='/' AND length(reference_path)>1 AND instr(reference_path,':')=0 AND instr(reference_path,'\')=0)),
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
    position INTEGER NOT NULL DEFAULT 0 CHECK(position>=0),
    CHECK((storage_mode='managed_copy' AND managed_relpath IS NOT NULL AND reference_path IS NULL)
        OR (storage_mode='external_reference' AND reference_path IS NOT NULL AND managed_relpath IS NULL)),
    CHECK(file_deleted_at IS NULL OR (storage_mode='managed_copy' AND deleted_at IS NOT NULL))
);
INSERT INTO materials_v4 (id,course_id,name,material_type,storage_mode,original_path,reference_path,managed_relpath,size_bytes,mtime_ns,baseline_sha256,observed_sha256,hash_checked_at,file_status,last_checked_at,last_error_code,import_state,deleted_at,file_deleted_at,created_at,updated_at,position) SELECT id,course_id,name,material_type,storage_mode,original_path,reference_path,managed_relpath,size_bytes,mtime_ns,baseline_sha256,observed_sha256,hash_checked_at,file_status,last_checked_at,last_error_code,import_state,deleted_at,file_deleted_at,created_at,updated_at,position FROM materials;
DROP TABLE materials;
ALTER TABLE materials_v4 RENAME TO materials;
CREATE INDEX idx_materials_course_name ON materials(course_id,name);
CREATE INDEX idx_materials_status ON materials(import_state,file_status,deleted_at);
