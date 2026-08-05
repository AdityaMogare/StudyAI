-- StudyAI schema for CockroachDB (PostgreSQL-compatible + pgvector API)
-- VECTOR support: CockroachDB 24.2+; VECTOR INDEX: CockroachDB 25.2+

CREATE EXTENSION IF NOT EXISTS vector;

CREATE TABLE IF NOT EXISTS courses (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    guild_id VARCHAR(255) NOT NULL,
    course_name VARCHAR(255) NOT NULL,
    active BOOLEAN DEFAULT TRUE,
    created_at TIMESTAMPTZ DEFAULT current_timestamp(),
    UNIQUE (guild_id, course_name)
);

CREATE INDEX IF NOT EXISTS idx_courses_guild ON courses (guild_id) WHERE active = TRUE;

CREATE TABLE IF NOT EXISTS syllabus_topics (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    course_id UUID NOT NULL REFERENCES courses(id) ON DELETE CASCADE,
    topic_name VARCHAR(255) NOT NULL,
    description TEXT,
    embedding VECTOR(1536),
    created_at TIMESTAMPTZ DEFAULT current_timestamp(),
    VECTOR INDEX (course_id, embedding)
);

CREATE INDEX IF NOT EXISTS idx_syllabus_topics_course ON syllabus_topics (course_id);

CREATE TABLE IF NOT EXISTS questions (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    course_id UUID NOT NULL REFERENCES courses(id) ON DELETE CASCADE,
    channel_id VARCHAR(255) NOT NULL,
    message_id VARCHAR(255) UNIQUE NOT NULL,
    asker_id VARCHAR(255) NOT NULL,
    question_text TEXT NOT NULL,
    embedding VECTOR(1536),
    status VARCHAR(50) DEFAULT 'open' CHECK (status IN ('open', 'resolved')),
    created_at TIMESTAMPTZ DEFAULT current_timestamp(),
    VECTOR INDEX (course_id, embedding)
);

CREATE INDEX IF NOT EXISTS idx_questions_course_status ON questions (course_id, status);
CREATE INDEX IF NOT EXISTS idx_questions_created_at ON questions (created_at);

CREATE TABLE IF NOT EXISTS answers (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    question_id UUID NOT NULL REFERENCES questions(id) ON DELETE CASCADE,
    message_id VARCHAR(255) UNIQUE NOT NULL,
    responder_id VARCHAR(255) NOT NULL,
    answer_text TEXT NOT NULL,
    created_at TIMESTAMPTZ DEFAULT current_timestamp()
);

CREATE INDEX IF NOT EXISTS idx_answers_question ON answers (question_id);

-- Load-bearing view: gap coverage via vector similarity
-- <-> is L2 / Euclidean distance (pgvector-compatible). Threshold tunable in app queries.
CREATE OR REPLACE VIEW topic_coverage AS
SELECT
    st.course_id,
    st.id AS topic_id,
    st.topic_name,
    COUNT(q.id) AS question_count,
    COUNT(CASE WHEN q.status = 'resolved' THEN 1 END) AS resolved_count,
    COUNT(CASE WHEN q.status = 'open' THEN 1 END) AS open_count
FROM
    syllabus_topics st
LEFT JOIN
    questions q
    ON q.course_id = st.course_id
    AND q.embedding IS NOT NULL
    AND st.embedding IS NOT NULL
    AND (q.embedding <-> st.embedding) < 0.3
GROUP BY
    st.course_id, st.id, st.topic_name;
