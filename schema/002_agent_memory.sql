-- Agent memory extensions for StudyAI Classroom Memory Agent
-- Apply after schema/001_init.sql

CREATE TABLE IF NOT EXISTS question_topic_links (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    question_id UUID NOT NULL REFERENCES questions(id) ON DELETE CASCADE,
    topic_id UUID NOT NULL REFERENCES syllabus_topics(id) ON DELETE CASCADE,
    distance FLOAT8 NOT NULL,
    confidence FLOAT8,
    created_at TIMESTAMPTZ DEFAULT current_timestamp(),
    UNIQUE (question_id, topic_id)
);

CREATE INDEX IF NOT EXISTS idx_question_topic_links_topic
    ON question_topic_links (topic_id);
CREATE INDEX IF NOT EXISTS idx_question_topic_links_question
    ON question_topic_links (question_id);

CREATE TABLE IF NOT EXISTS agent_actions (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    course_id UUID NOT NULL REFERENCES courses(id) ON DELETE CASCADE,
    action_type VARCHAR(100) NOT NULL,
    -- topic_link | gap_recommendation | syllabus_ingest | resolve
    input_ref VARCHAR(255),
    output_summary TEXT NOT NULL,
    payload JSONB,
    created_at TIMESTAMPTZ DEFAULT current_timestamp()
);

CREATE INDEX IF NOT EXISTS idx_agent_actions_course_created
    ON agent_actions (course_id, created_at DESC);
CREATE INDEX IF NOT EXISTS idx_agent_actions_type
    ON agent_actions (action_type);
