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
from shared.local_store import LocalConnection
from shared import local_store

logger = logging.getLogger(__name__)

Conn = psycopg.Connection | LocalConnection


def _local(conn: object) -> bool:
    return isinstance(conn, LocalConnection)


@contextmanager
def get_conn() -> Generator[Conn, None, None]:
    settings = get_settings()
    if settings.local_mode:
        with local_store.get_conn() as conn:
            yield conn
        return
    with psycopg.connect(settings.database_url, row_factory=dict_row) as conn:
        yield conn


def _vector_literal(embedding: Sequence[float]) -> str:
    return "[" + ",".join(f"{v:.8f}" for v in embedding) + "]"


def get_active_course_for_guild(conn: Conn, guild_id: str) -> dict[str, Any] | None:
    if _local(conn):
        return local_store.get_active_course_for_guild(conn, guild_id)  # type: ignore[arg-type]
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


def ensure_course(conn: Conn, guild_id: str, course_name: str) -> dict[str, Any]:
    if _local(conn):
        return local_store.ensure_course(conn, guild_id, course_name)  # type: ignore[arg-type]
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
    conn: Conn,
    *,
    course_id: UUID | str,
    channel_id: str,
    message_id: str,
    asker_id: str,
    question_text: str,
    embedding: Sequence[float],
) -> dict[str, Any]:
    if _local(conn):
        return local_store.insert_question(
            conn,  # type: ignore[arg-type]
            course_id=course_id,
            channel_id=channel_id,
            message_id=message_id,
            asker_id=asker_id,
            question_text=question_text,
            embedding=embedding,
        )
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
    conn: Conn,
    message_id: str,
    *,
    answer_message_id: str | None = None,
    responder_id: str | None = None,
    answer_text: str | None = None,
) -> dict[str, Any] | None:
    if _local(conn):
        return local_store.resolve_question_by_message_id(
            conn,  # type: ignore[arg-type]
            message_id,
            answer_message_id=answer_message_id,
            responder_id=responder_id,
            answer_text=answer_text,
        )
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
    conn: Conn,
    *,
    course_id: UUID | str,
    topic_name: str,
    description: str,
    embedding: Sequence[float],
) -> dict[str, Any]:
    if _local(conn):
        return local_store.insert_syllabus_topic(
            conn,  # type: ignore[arg-type]
            course_id=course_id,
            topic_name=topic_name,
            description=description,
            embedding=embedding,
        )
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
    conn: Conn,
    course_id: UUID | str | None = None,
    *,
    threshold: float | None = None,
) -> list[dict[str, Any]]:
    """Return coverage rows.

    Prefer the topic_coverage view. When a custom threshold is supplied,
    recompute with that distance cutoff.
    """
    if _local(conn):
        return local_store.fetch_topic_coverage(
            conn, course_id, threshold=threshold  # type: ignore[arg-type]
        )
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
    conn: Conn,
    course_id: UUID | str,
    topics: Iterable[tuple[str, str, Sequence[float]]],
) -> int:
    if _local(conn):
        return local_store.bulk_insert_topics(conn, course_id, topics)  # type: ignore[arg-type]
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
    conn: Conn,
    *,
    course_id: UUID | str,
    embedding: Sequence[float],
    limit: int = 3,
    max_distance: float | None = None,
    query_text: str | None = None,  # used by SQLite keyword matching; ignored on Cockroach
) -> list[dict[str, Any]]:
    """Distributed VECTOR nearest-neighbor lookup for a question embedding."""
    if _local(conn):
        return local_store.fetch_nearest_topics(
            conn,  # type: ignore[arg-type]
            course_id=course_id,
            embedding=embedding,
            limit=limit,
            max_distance=max_distance,
            query_text=query_text,
        )
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
    conn: Conn,
    *,
    question_id: UUID | str,
    links: list[dict[str, Any]],
) -> None:
    if _local(conn):
        local_store.replace_question_topic_links(
            conn, question_id=question_id, links=links  # type: ignore[arg-type]
        )
        return
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
    conn: Conn,
    *,
    course_id: UUID | str,
    action_type: str,
    output_summary: str,
    input_ref: str | None = None,
    payload: dict[str, Any] | None = None,
) -> dict[str, Any]:
    if _local(conn):
        return local_store.insert_agent_action(
            conn,  # type: ignore[arg-type]
            course_id=course_id,
            action_type=action_type,
            output_summary=output_summary,
            input_ref=input_ref,
            payload=payload,
        )
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
    conn: Conn,
    course_id: UUID | str,
    *,
    limit: int = 10,
) -> list[str]:
    if _local(conn):
        return local_store.fetch_recent_question_texts(
            conn, course_id, limit=limit  # type: ignore[arg-type]
        )
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
    conn: Conn,
    course_id: UUID | str,
    *,
    limit: int = 5,
) -> list[dict[str, Any]]:
    if _local(conn):
        return local_store.fetch_recent_agent_actions(
            conn, course_id, limit=limit  # type: ignore[arg-type]
        )
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


def clear_syllabus_topics(conn: Conn, course_id: UUID | str) -> None:
    if _local(conn):
        local_store.clear_syllabus_topics(conn, course_id)  # type: ignore[arg-type]
        return
    conn.execute("DELETE FROM syllabus_topics WHERE course_id = %s", (str(course_id),))
    conn.commit()


def insert_answer(
    conn: Conn,
    *,
    question_id: UUID | str,
    message_id: str,
    responder_id: str,
    answer_text: str,
) -> None:
    if _local(conn):
        local_store.insert_answer(
            conn,  # type: ignore[arg-type]
            question_id=question_id,
            message_id=message_id,
            responder_id=responder_id,
            answer_text=answer_text,
        )
        return
    conn.execute(
        """
        INSERT INTO answers (question_id, message_id, responder_id, answer_text)
        VALUES (%s, %s, %s, %s)
        ON CONFLICT (message_id) DO UPDATE
            SET answer_text = EXCLUDED.answer_text
        """,
        (str(question_id), message_id, responder_id, answer_text),
    )
    conn.commit()


def fetch_syllabus_topics(conn: Conn, course_id: UUID | str) -> list[dict[str, Any]]:
    if _local(conn):
        return local_store.fetch_syllabus_topics(conn, course_id)  # type: ignore[arg-type]
    rows = conn.execute(
        """
        SELECT id, topic_name, description
        FROM syllabus_topics
        WHERE course_id = %s
        ORDER BY topic_name
        """,
        (str(course_id),),
    ).fetchall()
    return list(rows)


def fetch_learner_coverage(
    conn: Conn,
    course_id: UUID | str,
    *,
    asker_id: str | None = None,
) -> list[dict[str, Any]]:
    if _local(conn):
        return local_store.fetch_learner_coverage(
            conn, course_id, asker_id=asker_id  # type: ignore[arg-type]
        )
    rows = conn.execute(
        """
        SELECT
            st.id AS topic_id,
            st.topic_name,
            COUNT(DISTINCT q.id) AS question_count,
            COUNT(DISTINCT CASE WHEN q.status = 'open' THEN q.id END) AS open_count,
            COUNT(DISTINCT CASE WHEN q.status = 'resolved' THEN q.id END) AS resolved_count,
            COUNT(DISTINCT CASE WHEN a.id IS NOT NULL THEN q.id END) AS explained_count,
            COUNT(DISTINCT CASE WHEN q.asker_id = %s THEN q.id END) AS mine_count
        FROM syllabus_topics st
        LEFT JOIN question_topic_links l ON l.topic_id = st.id
        LEFT JOIN questions q ON q.id = l.question_id
        LEFT JOIN answers a ON a.question_id = q.id
        WHERE st.course_id = %s
        GROUP BY st.id, st.topic_name
        ORDER BY st.topic_name
        """,
        (asker_id or "", str(course_id)),
    ).fetchall()
    return list(rows)


def fetch_topic_question_texts(
    conn: Conn,
    *,
    course_id: UUID | str,
    topic_id: UUID | str,
    limit: int = 8,
) -> list[str]:
    if _local(conn):
        return local_store.fetch_topic_question_texts(
            conn, course_id=course_id, topic_id=topic_id, limit=limit  # type: ignore[arg-type]
        )
    rows = conn.execute(
        """
        SELECT q.question_text
        FROM questions q
        JOIN question_topic_links l ON l.question_id = q.id
        WHERE q.course_id = %s AND l.topic_id = %s
        ORDER BY q.created_at DESC
        LIMIT %s
        """,
        (str(course_id), str(topic_id), limit),
    ).fetchall()
    return [r["question_text"] for r in rows]


def count_live_tutor_answers_today(
    conn: Conn,
    *,
    course_id: UUID | str,
    asker_id: str,
) -> int:
    """How many Bedrock tutor answers this student has used since UTC midnight."""
    if _local(conn):
        from datetime import datetime, timezone

        day_start = datetime.now(timezone.utc).replace(
            hour=0, minute=0, second=0, microsecond=0
        ).isoformat()
        return local_store.count_live_tutor_answers_today(
            conn,  # type: ignore[arg-type]
            course_id=course_id,
            asker_id=asker_id,
            day_start_iso=day_start,
        )
    row = conn.execute(
        """
        SELECT COUNT(*) AS n
        FROM agent_actions
        WHERE course_id = %s
          AND action_type = 'tutor_answer'
          AND payload->>'asker_id' = %s
          AND payload->>'source' = 'live'
          AND created_at >= (date_trunc('day', (now() AT TIME ZONE 'utc')) AT TIME ZONE 'utc')
        """,
        (str(course_id), asker_id),
    ).fetchone()
    if row is None:
        return 0
    return int(row["n"])
