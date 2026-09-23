-- Personal interview-prep drills (not classroom question capture)

CREATE TABLE IF NOT EXISTS drill_pending (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    course_id UUID NOT NULL REFERENCES courses(id) ON DELETE CASCADE,
    asker_id VARCHAR(255) NOT NULL,
    topic_id UUID NOT NULL REFERENCES syllabus_topics(id) ON DELETE CASCADE,
    topic_name VARCHAR(255) NOT NULL,
    question_text TEXT NOT NULL,
    hint TEXT,
    created_at TIMESTAMPTZ DEFAULT current_timestamp(),
    UNIQUE (course_id, asker_id)
);

CREATE TABLE IF NOT EXISTS drill_attempts (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    course_id UUID NOT NULL REFERENCES courses(id) ON DELETE CASCADE,
    asker_id VARCHAR(255) NOT NULL,
    topic_id UUID NOT NULL REFERENCES syllabus_topics(id) ON DELETE CASCADE,
    topic_name VARCHAR(255) NOT NULL,
    question_text TEXT NOT NULL,
    attempt_text TEXT NOT NULL,
    passed BOOLEAN NOT NULL,
    feedback TEXT,
    created_at TIMESTAMPTZ DEFAULT current_timestamp()
);

CREATE INDEX IF NOT EXISTS idx_drill_attempts_asker
    ON drill_attempts (course_id, asker_id, created_at DESC);
CREATE INDEX IF NOT EXISTS idx_drill_attempts_topic
    ON drill_attempts (course_id, asker_id, topic_id);
