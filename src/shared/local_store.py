"""SQLite classroom memory for LOCAL_MODE (no CockroachDB)."""

from __future__ import annotations

import json
import math
import re
import sqlite3
import threading
import uuid
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Generator, Iterable, Sequence
from uuid import UUID

from shared.config import get_settings

_LOCK = threading.Lock()

_SCHEMA = """
CREATE TABLE IF NOT EXISTS courses (
    id TEXT PRIMARY KEY,
    guild_id TEXT NOT NULL,
    course_name TEXT NOT NULL,
    active INTEGER DEFAULT 1,
    created_at TEXT NOT NULL,
    UNIQUE (guild_id, course_name)
);
CREATE TABLE IF NOT EXISTS syllabus_topics (
    id TEXT PRIMARY KEY,
    course_id TEXT NOT NULL REFERENCES courses(id) ON DELETE CASCADE,
    topic_name TEXT NOT NULL,
    description TEXT,
    embedding TEXT,
    created_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS questions (
    id TEXT PRIMARY KEY,
    course_id TEXT NOT NULL REFERENCES courses(id) ON DELETE CASCADE,
    channel_id TEXT NOT NULL,
    message_id TEXT UNIQUE NOT NULL,
    asker_id TEXT NOT NULL,
    question_text TEXT NOT NULL,
    embedding TEXT,
    status TEXT DEFAULT 'open',
    created_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS answers (
    id TEXT PRIMARY KEY,
    question_id TEXT NOT NULL REFERENCES questions(id) ON DELETE CASCADE,
    message_id TEXT UNIQUE NOT NULL,
    responder_id TEXT NOT NULL,
    answer_text TEXT NOT NULL,
    created_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS question_topic_links (
    id TEXT PRIMARY KEY,
    question_id TEXT NOT NULL REFERENCES questions(id) ON DELETE CASCADE,
    topic_id TEXT NOT NULL REFERENCES syllabus_topics(id) ON DELETE CASCADE,
    distance REAL NOT NULL,
    confidence REAL,
    created_at TEXT NOT NULL,
    UNIQUE (question_id, topic_id)
);
CREATE TABLE IF NOT EXISTS agent_actions (
    id TEXT PRIMARY KEY,
    course_id TEXT NOT NULL REFERENCES courses(id) ON DELETE CASCADE,
    action_type TEXT NOT NULL,
    input_ref TEXT,
    output_summary TEXT NOT NULL,
    payload TEXT,
    created_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS drill_pending (
    id TEXT PRIMARY KEY,
    course_id TEXT NOT NULL REFERENCES courses(id) ON DELETE CASCADE,
    asker_id TEXT NOT NULL,
    topic_id TEXT NOT NULL REFERENCES syllabus_topics(id) ON DELETE CASCADE,
    topic_name TEXT NOT NULL,
    question_text TEXT NOT NULL,
    hint TEXT,
    created_at TEXT NOT NULL,
    UNIQUE (course_id, asker_id)
);
CREATE TABLE IF NOT EXISTS drill_attempts (
    id TEXT PRIMARY KEY,
    course_id TEXT NOT NULL REFERENCES courses(id) ON DELETE CASCADE,
    asker_id TEXT NOT NULL,
    topic_id TEXT NOT NULL REFERENCES syllabus_topics(id) ON DELETE CASCADE,
    topic_name TEXT NOT NULL,
    question_text TEXT NOT NULL,
    attempt_text TEXT NOT NULL,
    passed INTEGER NOT NULL,
    feedback TEXT,
    created_at TEXT NOT NULL
);
"""


class LocalConnection:
    """Thin sqlite3 wrapper used by db.py in LOCAL_MODE."""

    def __init__(self, db: sqlite3.Connection) -> None:
        self.db = db
        self.backend = "sqlite"

    def execute(self, sql: str, params: Sequence[Any] = ()) -> sqlite3.Cursor:
        converted = sql.replace("%s", "?")
        return self.db.execute(converted, tuple(params))

    def commit(self) -> None:
        self.db.commit()

    def rollback(self) -> None:
        self.db.rollback()


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _new_id() -> str:
    return str(uuid.uuid4())


def _parse_vec(raw: str | None) -> list[float]:
    if not raw:
        return []
    data = json.loads(raw)
    return [float(v) for v in data]


def tokenize(text: str) -> set[str]:
    tokens = re.findall(r"[a-z0-9]+", (text or "").lower())
    stemmed: set[str] = set()
    stop = {
        "the", "a", "an", "and", "or", "of", "to", "in", "on", "for", "is", "are",
        "does", "do", "did", "how", "what", "why", "when", "where", "which", "who",
        "can", "could", "should", "someone", "please", "help",
    }
    for tok in tokens:
        if tok in stop or len(tok) < 3:
            continue
        for suffix in ("ing", "tion", "sion", "ies", "es", "ed", "s"):
            if len(tok) > len(suffix) + 3 and tok.endswith(suffix):
                tok = tok[: -len(suffix)]
                break
        stemmed.add(tok)
    return stemmed


def lexical_distance(left: str, right: str) -> float:
    """0 = strong keyword overlap. Uses Jaccard and topic-containment."""
    a, b = tokenize(left), tokenize(right)
    if not a or not b:
        return 1.0
    inter = len(a & b)
    jaccard = inter / len(a | b)
    containment = inter / len(b)
    return 1.0 - max(jaccard, containment)


def l2(left: Sequence[float], right: Sequence[float]) -> float:
    n = min(len(left), len(right))
    if n == 0:
        return 1.0
    return math.sqrt(sum((float(left[i]) - float(right[i])) ** 2 for i in range(n)))


def init_db(path: str) -> None:
    Path(path).parent.mkdir(parents=True, exist_ok=True)
    with sqlite3.connect(path) as db:
        db.executescript(_SCHEMA)
        db.commit()


@contextmanager
def get_conn() -> Generator[LocalConnection, None, None]:
    settings = get_settings()
    init_db(settings.sqlite_path)
    _LOCK.acquire()
    db = sqlite3.connect(settings.sqlite_path, check_same_thread=False)
    db.row_factory = sqlite3.Row
    db.execute("PRAGMA foreign_keys = ON")
    conn = LocalConnection(db)
    try:
        yield conn
        db.commit()
    except Exception:
        db.rollback()
        raise
    finally:
        db.close()
        _LOCK.release()


def get_active_course_for_guild(conn: LocalConnection, guild_id: str) -> dict[str, Any] | None:
    row = conn.execute(
        """
        SELECT id, guild_id, course_name, active
        FROM courses
        WHERE guild_id = %s AND active = 1
        ORDER BY created_at DESC
        LIMIT 1
        """,
        (guild_id,),
    ).fetchone()
    return dict(row) if row else None


def ensure_course(conn: LocalConnection, guild_id: str, course_name: str) -> dict[str, Any]:
    existing = conn.execute(
        """
        SELECT id, guild_id, course_name, active
        FROM courses
        WHERE guild_id = %s AND course_name = %s
        """,
        (guild_id, course_name),
    ).fetchone()
    if existing:
        conn.execute(
            "UPDATE courses SET active = 1 WHERE id = %s",
            (existing["id"],),
        )
        conn.commit()
        row = conn.execute(
            "SELECT id, guild_id, course_name, active FROM courses WHERE id = %s",
            (existing["id"],),
        ).fetchone()
        return dict(row)
    course_id = _new_id()
    conn.execute(
        """
        INSERT INTO courses (id, guild_id, course_name, active, created_at)
        VALUES (%s, %s, %s, 1, %s)
        """,
        (course_id, guild_id, course_name, _now()),
    )
    conn.commit()
    return {
        "id": course_id,
        "guild_id": guild_id,
        "course_name": course_name,
        "active": 1,
    }


def insert_question(
    conn: LocalConnection,
    *,
    course_id: UUID | str,
    channel_id: str,
    message_id: str,
    asker_id: str,
    question_text: str,
    embedding: Sequence[float],
) -> dict[str, Any]:
    emb = json.dumps(list(embedding))
    existing = conn.execute(
        "SELECT id FROM questions WHERE message_id = %s",
        (message_id,),
    ).fetchone()
    if existing:
        conn.execute(
            """
            UPDATE questions
            SET question_text = %s, embedding = %s
            WHERE message_id = %s
            """,
            (question_text, emb, message_id),
        )
        conn.commit()
        row = conn.execute(
            "SELECT id, message_id, status, created_at FROM questions WHERE message_id = %s",
            (message_id,),
        ).fetchone()
        return dict(row)
    qid = _new_id()
    created = _now()
    conn.execute(
        """
        INSERT INTO questions (
            id, course_id, channel_id, message_id, asker_id, question_text, embedding, status, created_at
        )
        VALUES (%s, %s, %s, %s, %s, %s, %s, 'open', %s)
        """,
        (qid, str(course_id), channel_id, message_id, asker_id, question_text, emb, created),
    )
    conn.commit()
    return {"id": qid, "message_id": message_id, "status": "open", "created_at": created}


def resolve_question_by_message_id(
    conn: LocalConnection,
    message_id: str,
    *,
    answer_message_id: str | None = None,
    responder_id: str | None = None,
    answer_text: str | None = None,
) -> dict[str, Any] | None:
    question = conn.execute(
        """
        SELECT id, message_id, status, question_text, course_id
        FROM questions
        WHERE message_id = %s
        """,
        (message_id,),
    ).fetchone()
    if not question:
        return None
    conn.execute(
        "UPDATE questions SET status = 'resolved' WHERE message_id = %s",
        (message_id,),
    )
    if answer_message_id and responder_id and answer_text:
        conn.execute(
            """
            INSERT OR IGNORE INTO answers (id, question_id, message_id, responder_id, answer_text, created_at)
            VALUES (%s, %s, %s, %s, %s, %s)
            """,
            (_new_id(), question["id"], answer_message_id, responder_id, answer_text, _now()),
        )
    conn.commit()
    data = dict(question)
    data["status"] = "resolved"
    return data


def insert_syllabus_topic(
    conn: LocalConnection,
    *,
    course_id: UUID | str,
    topic_name: str,
    description: str,
    embedding: Sequence[float],
) -> dict[str, Any]:
    topic_id = _new_id()
    conn.execute(
        """
        INSERT INTO syllabus_topics (id, course_id, topic_name, description, embedding, created_at)
        VALUES (%s, %s, %s, %s, %s, %s)
        """,
        (topic_id, str(course_id), topic_name, description, json.dumps(list(embedding)), _now()),
    )
    conn.commit()
    return {"id": topic_id, "topic_name": topic_name}


def bulk_insert_topics(
    conn: LocalConnection,
    course_id: UUID | str,
    topics: Iterable[tuple[str, str, Sequence[float]]],
) -> int:
    count = 0
    for topic_name, description, embedding in topics:
        conn.execute(
            """
            INSERT INTO syllabus_topics (id, course_id, topic_name, description, embedding, created_at)
            VALUES (%s, %s, %s, %s, %s, %s)
            """,
            (
                _new_id(),
                str(course_id),
                topic_name,
                description,
                json.dumps(list(embedding)),
                _now(),
            ),
        )
        count += 1
    conn.commit()
    return count


def clear_syllabus_topics(conn: LocalConnection, course_id: UUID | str) -> None:
    conn.execute("DELETE FROM syllabus_topics WHERE course_id = %s", (str(course_id),))
    conn.commit()


def fetch_nearest_topics(
    conn: LocalConnection,
    *,
    course_id: UUID | str,
    embedding: Sequence[float],
    limit: int = 3,
    max_distance: float | None = None,
    query_text: str | None = None,
) -> list[dict[str, Any]]:
    rows = conn.execute(
        """
        SELECT id AS topic_id, topic_name, description, embedding
        FROM syllabus_topics
        WHERE course_id = %s AND embedding IS NOT NULL
        """,
        (str(course_id),),
    ).fetchall()
    scored: list[dict[str, Any]] = []
    for row in rows:
        topic = dict(row)
        blob = f"{topic['topic_name']}\n{topic.get('description') or ''}"
        if query_text:
            distance = min(
                lexical_distance(query_text, str(topic["topic_name"])),
                lexical_distance(query_text, blob),
            )
        else:
            distance = l2(embedding, _parse_vec(topic.get("embedding")))
        topic["distance"] = distance
        del topic["embedding"]
        if max_distance is not None and distance > max_distance:
            continue
        scored.append(topic)
    scored.sort(key=lambda r: float(r["distance"]))
    return scored[:limit]


def fetch_topic_coverage(
    conn: LocalConnection,
    course_id: UUID | str | None = None,
    *,
    threshold: float | None = None,
) -> list[dict[str, Any]]:
    """Coverage from persisted question_topic_links (local keyword matches)."""
    del threshold  # links already filtered at write time
    params: list[Any] = []
    sql = """
        SELECT
            st.course_id,
            st.id AS topic_id,
            st.topic_name,
            COUNT(q.id) AS question_count,
            SUM(CASE WHEN q.status = 'resolved' THEN 1 ELSE 0 END) AS resolved_count,
            SUM(CASE WHEN q.status = 'open' THEN 1 ELSE 0 END) AS open_count
        FROM syllabus_topics st
        LEFT JOIN question_topic_links l
            ON l.topic_id = st.id
        LEFT JOIN questions q
            ON q.id = l.question_id
    """
    if course_id:
        sql += " WHERE st.course_id = %s"
        params.append(str(course_id))
    sql += " GROUP BY st.course_id, st.id, st.topic_name ORDER BY st.topic_name"
    rows = conn.execute(sql, params).fetchall()
    results = []
    for row in rows:
        item = dict(row)
        item["question_count"] = int(item["question_count"] or 0)
        item["resolved_count"] = int(item["resolved_count"] or 0)
        item["open_count"] = int(item["open_count"] or 0)
        results.append(item)
    return results


def replace_question_topic_links(
    conn: LocalConnection,
    *,
    question_id: UUID | str,
    links: list[dict[str, Any]],
) -> None:
    conn.execute("DELETE FROM question_topic_links WHERE question_id = %s", (str(question_id),))
    for link in links:
        conn.execute(
            """
            INSERT INTO question_topic_links (
                id, question_id, topic_id, distance, confidence, created_at
            )
            VALUES (%s, %s, %s, %s, %s, %s)
            """,
            (
                _new_id(),
                str(question_id),
                str(link["topic_id"]),
                float(link["distance"]),
                float(link.get("confidence") or 0.0),
                _now(),
            ),
        )
    conn.commit()


def insert_agent_action(
    conn: LocalConnection,
    *,
    course_id: UUID | str,
    action_type: str,
    output_summary: str,
    input_ref: str | None = None,
    payload: dict[str, Any] | None = None,
) -> dict[str, Any]:
    action_id = _new_id()
    created = _now()
    conn.execute(
        """
        INSERT INTO agent_actions (
            id, course_id, action_type, input_ref, output_summary, payload, created_at
        )
        VALUES (%s, %s, %s, %s, %s, %s, %s)
        """,
        (
            action_id,
            str(course_id),
            action_type,
            input_ref,
            output_summary,
            json.dumps(payload or {}),
            created,
        ),
    )
    conn.commit()
    return {"id": action_id, "action_type": action_type, "created_at": created}


def fetch_recent_question_texts(
    conn: LocalConnection,
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
    conn: LocalConnection,
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
    return [dict(r) for r in rows]


def insert_answer(
    conn: LocalConnection,
    *,
    question_id: UUID | str,
    message_id: str,
    responder_id: str,
    answer_text: str,
) -> None:
    existing = conn.execute(
        "SELECT id FROM answers WHERE message_id = %s",
        (message_id,),
    ).fetchone()
    if existing:
        conn.execute(
            "UPDATE answers SET answer_text = %s, responder_id = %s WHERE message_id = %s",
            (answer_text, responder_id, message_id),
        )
    else:
        conn.execute(
            """
            INSERT INTO answers (id, question_id, message_id, responder_id, answer_text, created_at)
            VALUES (%s, %s, %s, %s, %s, %s)
            """,
            (_new_id(), str(question_id), message_id, responder_id, answer_text, _now()),
        )
    conn.commit()


def fetch_syllabus_topics(conn: LocalConnection, course_id: UUID | str) -> list[dict[str, Any]]:
    rows = conn.execute(
        """
        SELECT id, topic_name, description
        FROM syllabus_topics
        WHERE course_id = %s
        ORDER BY topic_name
        """,
        (str(course_id),),
    ).fetchall()
    return [dict(r) for r in rows]


def fetch_learner_coverage(
    conn: LocalConnection,
    course_id: UUID | str,
    *,
    asker_id: str | None = None,
) -> list[dict[str, Any]]:
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
    results = []
    for row in rows:
        item = dict(row)
        for key in ("question_count", "open_count", "resolved_count", "explained_count", "mine_count"):
            item[key] = int(item.get(key) or 0)
        results.append(item)
    return results


def fetch_topic_question_texts(
    conn: LocalConnection,
    *,
    course_id: UUID | str,
    topic_id: UUID | str,
    limit: int = 8,
) -> list[str]:
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
    conn: LocalConnection,
    *,
    course_id: UUID | str,
    asker_id: str,
    day_start_iso: str,
) -> int:
    row = conn.execute(
        """
        SELECT COUNT(*) AS n
        FROM agent_actions
        WHERE course_id = %s
          AND action_type = 'tutor_answer'
          AND json_extract(payload, '$.asker_id') = %s
          AND json_extract(payload, '$.source') = 'live'
          AND created_at >= %s
        """,
        (str(course_id), asker_id, day_start_iso),
    ).fetchone()
    if row is None:
        return 0
    return int(row["n"])


def get_drill_pending(
    conn: LocalConnection,
    *,
    course_id: UUID | str,
    asker_id: str,
) -> dict[str, Any] | None:
    row = conn.execute(
        """
        SELECT id, course_id, asker_id, topic_id, topic_name, question_text, hint, created_at
        FROM drill_pending
        WHERE course_id = %s AND asker_id = %s
        """,
        (str(course_id), asker_id),
    ).fetchone()
    return dict(row) if row else None


def upsert_drill_pending(
    conn: LocalConnection,
    *,
    course_id: UUID | str,
    asker_id: str,
    topic_id: UUID | str,
    topic_name: str,
    question_text: str,
    hint: str = "",
) -> dict[str, Any]:
    conn.execute(
        "DELETE FROM drill_pending WHERE course_id = %s AND asker_id = %s",
        (str(course_id), asker_id),
    )
    pending_id = _new_id()
    created = _now()
    conn.execute(
        """
        INSERT INTO drill_pending (
            id, course_id, asker_id, topic_id, topic_name, question_text, hint, created_at
        )
        VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
        """,
        (
            pending_id,
            str(course_id),
            asker_id,
            str(topic_id),
            topic_name,
            question_text,
            hint,
            created,
        ),
    )
    conn.commit()
    return {
        "id": pending_id,
        "topic_id": str(topic_id),
        "topic_name": topic_name,
        "question_text": question_text,
        "hint": hint,
    }


def clear_drill_pending(
    conn: LocalConnection,
    *,
    course_id: UUID | str,
    asker_id: str,
) -> None:
    conn.execute(
        "DELETE FROM drill_pending WHERE course_id = %s AND asker_id = %s",
        (str(course_id), asker_id),
    )
    conn.commit()


def insert_drill_attempt(
    conn: LocalConnection,
    *,
    course_id: UUID | str,
    asker_id: str,
    topic_id: UUID | str,
    topic_name: str,
    question_text: str,
    attempt_text: str,
    passed: bool,
    feedback: str,
) -> dict[str, Any]:
    attempt_id = _new_id()
    created = _now()
    conn.execute(
        """
        INSERT INTO drill_attempts (
            id, course_id, asker_id, topic_id, topic_name,
            question_text, attempt_text, passed, feedback, created_at
        )
        VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
        """,
        (
            attempt_id,
            str(course_id),
            asker_id,
            str(topic_id),
            topic_name,
            question_text,
            attempt_text,
            1 if passed else 0,
            feedback,
            created,
        ),
    )
    conn.commit()
    return {"id": attempt_id, "passed": passed, "created_at": created}


def fetch_drill_stats(
    conn: LocalConnection,
    *,
    course_id: UUID | str,
    asker_id: str,
) -> list[dict[str, Any]]:
    rows = conn.execute(
        """
        SELECT
            topic_id,
            topic_name,
            COUNT(*) AS attempts,
            SUM(CASE WHEN passed = 1 THEN 1 ELSE 0 END) AS passes,
            SUM(CASE WHEN passed = 0 THEN 1 ELSE 0 END) AS fails
        FROM drill_attempts
        WHERE course_id = %s AND asker_id = %s
        GROUP BY topic_id, topic_name
        """,
        (str(course_id), asker_id),
    ).fetchall()
    results = []
    for row in rows:
        item = dict(row)
        for key in ("attempts", "passes", "fails"):
            item[key] = int(item.get(key) or 0)
        results.append(item)
    return results


def fetch_recent_drill_questions(
    conn: LocalConnection,
    *,
    course_id: UUID | str,
    asker_id: str,
    topic_id: UUID | str,
    limit: int = 8,
) -> list[str]:
    rows = conn.execute(
        """
        SELECT question_text
        FROM drill_attempts
        WHERE course_id = %s AND asker_id = %s AND topic_id = %s
        ORDER BY created_at DESC
        LIMIT %s
        """,
        (str(course_id), asker_id, str(topic_id), limit),
    ).fetchall()
    return [r["question_text"] for r in rows]
