-- Reading editions are immutable snapshots. Marks never follow a changing source.
ALTER TABLE materials ADD COLUMN position INTEGER NOT NULL DEFAULT 0 CHECK(position>=0);
ALTER TABLE tasks ADD COLUMN revision INTEGER NOT NULL DEFAULT 1 CHECK(revision>=1);
ALTER TABLE chapters ADD COLUMN revision INTEGER NOT NULL DEFAULT 1 CHECK(revision>=1);
ALTER TABLE knowledge_points ADD COLUMN revision INTEGER NOT NULL DEFAULT 1 CHECK(revision>=1);
CREATE TABLE reading_editions (
 id TEXT PRIMARY KEY NOT NULL CHECK(length(id)=36),
 material_id TEXT NOT NULL REFERENCES materials(id) ON DELETE RESTRICT,
 source_sha256 TEXT NOT NULL CHECK(length(source_sha256)=64),
 pdf_relpath TEXT NOT NULL UNIQUE,
 pdf_sha256 TEXT NOT NULL CHECK(length(pdf_sha256)=64),
 size_bytes INTEGER NOT NULL CHECK(size_bytes>=0),
 page_count INTEGER NOT NULL CHECK(page_count>0),
 converter TEXT NOT NULL,
 created_at TEXT NOT NULL
);
CREATE TABLE edition_pages (
 edition_id TEXT NOT NULL REFERENCES reading_editions(id) ON DELETE RESTRICT,
 page INTEGER NOT NULL CHECK(page>=1),
 PRIMARY KEY(edition_id,page)
);
CREATE TABLE reading_progress (
 edition_id TEXT PRIMARY KEY NOT NULL REFERENCES reading_editions(id) ON DELETE RESTRICT,
 page INTEGER NOT NULL,
 revision INTEGER NOT NULL DEFAULT 0 CHECK(revision>=0),
 updated_at TEXT NOT NULL,
 FOREIGN KEY(edition_id,page) REFERENCES edition_pages(edition_id,page)
);
CREATE TABLE annotations (
 id TEXT PRIMARY KEY NOT NULL CHECK(length(id)=36),
 edition_id TEXT NOT NULL,
 page INTEGER NOT NULL,
 kind TEXT NOT NULL CHECK(kind IN ('bookmark','comment','important','question','highlight','rectangle','ink')),
 body TEXT NOT NULL DEFAULT '',
 geometry_json TEXT NOT NULL DEFAULT '[]' CHECK(json_valid(geometry_json)),
 resolved INTEGER NOT NULL DEFAULT 0 CHECK(resolved IN (0,1)),
 deleted_at TEXT,
 created_at TEXT NOT NULL,
 updated_at TEXT NOT NULL,
 revision INTEGER NOT NULL DEFAULT 1 CHECK(revision>=1),
 FOREIGN KEY(edition_id,page) REFERENCES edition_pages(edition_id,page)
);
CREATE INDEX idx_annotations_edition_page ON annotations(edition_id,page,deleted_at);
CREATE TABLE workbench_requests (
 id TEXT PRIMARY KEY NOT NULL CHECK(length(id)=36),
 payload TEXT NOT NULL CHECK(json_valid(payload)),
 result_id TEXT NOT NULL,
 created_at TEXT NOT NULL
);
CREATE TABLE content_operations (
 id TEXT PRIMARY KEY NOT NULL CHECK(length(id)=36),
 kind TEXT NOT NULL CHECK(kind IN ('edition','note')),
 state TEXT NOT NULL CHECK(state IN ('planned','committed','failed')),
 target_relpath TEXT NOT NULL,
 payload_json TEXT NOT NULL CHECK(json_valid(payload_json)),
 created_at TEXT NOT NULL,
 error TEXT
);
CREATE TRIGGER editions_immutable BEFORE UPDATE ON reading_editions
BEGIN SELECT RAISE(ABORT,'reading editions are immutable'); END;
CREATE TRIGGER pages_immutable BEFORE UPDATE ON edition_pages
BEGIN SELECT RAISE(ABORT,'edition pages are immutable'); END;
