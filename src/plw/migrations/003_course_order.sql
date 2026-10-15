-- Preserve the former course order once, without changing user timestamps.
ALTER TABLE courses ADD COLUMN position INTEGER NOT NULL DEFAULT 0
    CHECK(typeof(position)='integer' AND position>=0);
WITH ordered AS (
    SELECT id, ROW_NUMBER() OVER (ORDER BY updated_at DESC, name COLLATE NOCASE, id)-1 AS position
    FROM courses
)
UPDATE courses SET position=(SELECT position FROM ordered WHERE ordered.id=courses.id);
CREATE INDEX idx_courses_position ON courses(position);
