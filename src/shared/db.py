"""CockroachDB helpers (PostgreSQL wire protocol + VECTOR)."""

from __future__ import annotations

import json
import logging
from contextlib import contextmanager
from typing import Any, Generator, Iterable, Sequence
from uuid import UUID

import psycopg
from psycopg.rows import dict_row

from shared.config import get_settings

logger = logging.getLogger(__name__)


@contextmanager
def get_conn() -> Generator[psycopg.Connection, None, None]:
    settings = get_settings()
    with psycopg.connect(settings.database_url, row_factory=dict_row) as conn:
        yield conn


def _vector_literal(embedding: Sequence[float]) -> str:
    return "[" + ",".join(f"{v:.8f}" for v in embedding) + "]"


def get_active_course_for_guild(conn: psycopg.Connection, guild_id: str) -> dict[str, Any] | None:
    row = conn.execute(
        """
        SELECT id, guild_id, course_name, active
        FROM courses
        WHERE guild_id = %s AND active = TRUE
        ORDER BY created_at DESC
        LIMIT 1
        """,
        (guild_id,),
    ).fetchone()
    return row


def ensure_course(
    conn: psycopg.Connection, guild_id: str, course_name: str
) -> dict[str, Any]:
    row = conn.execute(
        """
        INSERT INTO courses (guild_id, course_name)
        VALUES (%s, %s)
        ON CONFLICT (guild_id, course_name)
        DO UPDATE SET active = TRUE
        RETURNING id, guild_id, course_name, active
        """,
        (guild_id, course_name),
    ).fetchone()
    conn.commit()
    return row


def insert_question(
    conn: psycopg.Connection,
    *,
    course_id: UUID | str,
    channel_id: str,
    message_id: str,
    asker_id: str,
    question_text: str,
    embedding: Sequence[float],
) -> dict[str, Any]:
    row = conn.execute(
        """
        INSERT INTO questions (
            course_id, channel_id, message_id, asker_id, question_text, embedding, status
        )
        VALUES (%s, %s, %s, %s, %s, %s::vector, 'open')
        ON CONFLICT (message_id) DO UPDATE
            SET question_text = EXCLUDED.question_text,
                embedding = EXCLUDED.embedding
        RETURNING id, message_id, status, created_at
        """,
        (
            str(course_id),
            channel_id,
            message_id,
            asker_id,
            question_text,
            _vector_literal(embedding),
        ),
    ).fetchone()
    conn.commit()
    return row


def resolve_question_by_message_id(
    conn: psycopg.Connection,
    message_id: str,
    *,
    answer_message_id: str | None = None,
    responder_id: str | None = None,
    answer_text: str | None = None,
) -> dict[str, Any] | None:
    question = conn.execute(
        """
        UPDATE questions
        SET status = 'resolved'
        WHERE message_id = %s
        RETURNING id, message_id, status, question_text, course_id
        """,
        (message_id,),
    ).fetchone()
    if not question:
        conn.rollback()
        return None

    if answer_message_id and responder_id and answer_text:
        conn.execute(
            """
            INSERT INTO answers (question_id, message_id, responder_id, answer_text)
            VALUES (%s, %s, %s, %s)
            ON CONFLICT (message_id) DO NOTHING
            """,
            (str(question["id"]), answer_message_id, responder_id, answer_text),
        )

    conn.commit()
    return question


def insert_syllabus_topic(
    conn: psycopg.Connection,
    *,
    course_id: UUID | str,
    topic_name: str,
    description: str,
    embedding: Sequence[float],
) -> dict[str, Any]:
    row = conn.execute(
        """
        INSERT INTO syllabus_topics (course_id, topic_name, description, embedding)
        VALUES (%s, %s, %s, %s::vector)
        RETURNING id, topic_name
        """,
        (str(course_id), topic_name, description, _vector_literal(embedding)),
    ).fetchone()
    conn.commit()
    return row


def fetch_topic_coverage(
    conn: psycopg.Connection,
    course_id: UUID | str | None = None,
    *,
    threshold: float | None = None,
) -> list[dict[str, Any]]:
    """Return coverage rows.

    Prefer the topic_coverage view. When a custom threshold is supplied,
    recompute with that distance cutoff.
    """
    if threshold is None:
        if course_id:
            rows = conn.execute(
                """
                SELECT topic_id, topic_name, question_count, resolved_count, open_count
                FROM topic_coverage
                WHERE course_id = %s
                ORDER BY topic_name
                """,
                (str(course_id),),
            ).fetchall()
        else:
            rows = conn.execute(
                """
                SELECT course_id, topic_id, topic_name, question_count,
                       resolved_count, open_count
                FROM topic_coverage
                ORDER BY course_id, topic_name
                """
            ).fetchall()
        return list(rows)

    sql = """
        SELECT
            st.course_id,
            st.id AS topic_id,
            st.topic_name,
            COUNT(q.id) AS question_count,
            COUNT(CASE WHEN q.status = 'resolved' THEN 1 END) AS resolved_count,
            COUNT(CASE WHEN q.status = 'open' THEN 1 END) AS open_count
        FROM syllabus_topics st
        LEFT JOIN questions q
            ON q.course_id = st.course_id
            AND q.embedding IS NOT NULL
            AND st.embedding IS NOT NULL
            AND (q.embedding <-> st.embedding) < %s
        WHERE (%s::uuid IS NULL OR st.course_id = %s::uuid)
        GROUP BY st.course_id, st.id, st.topic_name
        ORDER BY st.topic_name
    """
    rows = conn.execute(
        sql,
        (threshold, str(course_id) if course_id else None, str(course_id) if course_id else None),
    ).fetchall()
    return list(rows)


def bulk_insert_topics(
    conn: psycopg.Connection,
    course_id: UUID | str,
    topics: Iterable[tuple[str, str, Sequence[float]]],
) -> int:
    count = 0
    for topic_name, description, embedding in topics:
        conn.execute(
            """
            INSERT INTO syllabus_topics (course_id, topic_name, description, embedding)
            VALUES (%s, %s, %s, %s::vector)
            """,
            (str(course_id), topic_name, description, _vector_literal(embedding)),
        )
        count += 1
    conn.commit()
    return count


def fetch_nearest_topics(
    conn: psycopg.Connection,
    *,
    course_id: UUID | str,
    embedding: Sequence[float],
    limit: int = 3,
    max_distance: float | None = None,
) -> list[dict[str, Any]]:
    """Distributed VECTOR nearest-neighbor lookup for a question embedding."""
    sql = """
        SELECT
            st.id AS topic_id,
            st.topic_name,
            st.description,
            (st.embedding <-> %s::vector) AS distance
        FROM syllabus_topics st
        WHERE st.course_id = %s
          AND st.embedding IS NOT NULL
        ORDER BY st.embedding <-> %s::vector
        LIMIT %s
    """
    vec = _vector_literal(embedding)
    rows = conn.execute(sql, (vec, str(course_id), vec, limit)).fetchall()
    results = list(rows)
    if max_distance is not None:
        results = [r for r in results if float(r["distance"]) <= max_distance]
    return results


def replace_question_topic_links(
    conn: psycopg.Connection,
    *,
    question_id: UUID | str,
    links: list[dict[str, Any]],
) -> None:
    conn.execute(
        "DELETE FROM question_topic_links WHERE question_id = %s",
        (str(question_id),),
    )
    for link in links:
        conn.execute(
            """
            INSERT INTO question_topic_links (
                question_id, topic_id, distance, confidence
            )
            VALUES (%s, %s, %s, %s)
            ON CONFLICT (question_id, topic_id) DO UPDATE
                SET distance = EXCLUDED.distance,
                    confidence = EXCLUDED.confidence
            """,
            (
                str(question_id),
                str(link["topic_id"]),
                float(link["distance"]),
                float(link.get("confidence") or 0.0),
            ),
        )
    conn.commit()


def insert_agent_action(
    conn: psycopg.Connection,
    *,
    course_id: UUID | str,
    action_type: str,
    output_summary: str,
    input_ref: str | None = None,
    payload: dict[str, Any] | None = None,
) -> dict[str, Any]:
    row = conn.execute(
        """
        INSERT INTO agent_actions (
            course_id, action_type, input_ref, output_summary, payload
        )
        VALUES (%s, %s, %s, %s, %s::jsonb)
        RETURNING id, action_type, created_at
        """,
        (
            str(course_id),
            action_type,
            input_ref,
            output_summary,
            json.dumps(payload or {}),
        ),
    ).fetchone()
    conn.commit()
    return row


def fetch_recent_question_texts(
    conn: psycopg.Connection,
    course_id: UUID | str,
    *,
    limit: int = 10,
) -> list[str]:
    rows = conn.execute(
        """
        SELECT question_text
        FROM questions
        WHERE course_id = %s
        ORDER BY created_at DESC
        LIMIT %s
        """,
        (str(course_id), limit),
    ).fetchall()
    return [r["question_text"] for r in rows]


def fetch_recent_agent_actions(
    conn: psycopg.Connection,
    course_id: UUID | str,
    *,
    limit: int = 5,
) -> list[dict[str, Any]]:
    rows = conn.execute(
        """
        SELECT action_type, output_summary, created_at
        FROM agent_actions
        WHERE course_id = %s
        ORDER BY created_at DESC
        LIMIT %s
        """,
        (str(course_id), limit),
    ).fetchall()
    return list(rows)
