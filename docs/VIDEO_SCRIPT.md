# Demo video script (< 3 minutes)

Record screen + voice. Upload to YouTube or Vimeo as **public**. Target 2:00–2:45.

## Shot list

| Time | Visual | Voiceover |
|---|---|---|
| 0:00–0:15 | Title slide: StudyAI + logos | “StudyAI is a Classroom Memory Agent. CockroachDB holds durable class memory; Bedrock reasons; Lambda acts in Discord.” |
| 0:15–0:35 | Architecture diagram (`docs/architecture.svg`) | “Questions hit Lambda, Titan embeds them, CockroachDB VECTOR indexes store memory. We also used Cloud MCP and Agent Skills while building.” |
| 0:35–1:00 | Discord `/ask How does binary search guarantee O(log n)?` | “A student asks. The agent writes the question into CockroachDB and links it to syllabus topics via vector search.” |
| 1:00–1:20 | SQL/MCP: `questions`, `question_topic_links`, `agent_actions` | “Here’s the memory layer — embeddings, topic links, and an agent_actions audit trail. This is agentic memory, not a toy log.” |
| 1:20–1:45 | `/memory` response | “The agent reads coverage memory and recommends what TAs should teach next — priorities persisted back to CockroachDB.” |
| 1:45–2:15 | `/gap-report` embed in `#exam-prep` | “Weekly gap report: untouched topics, unresolved clusters, and a Bedrock TA plan with exam risk.” |
| 2:15–2:35 | ✅ resolve + show `status=resolved` | “When peers resolve a question, transactional state updates in the same database as the vectors — no consistency gap.” |
| 2:35–2:50 | Closing | “StudyAI: production-shaped agentic memory on CockroachDB and AWS. Link in description.” |

## Tips

- Use a clean demo guild with pre-seeded syllabus (`tools/seed_demo.py` optional).
- Zoom font size in Discord and SQL client.
- Say “CockroachDB Distributed Vector Indexing” and “Managed MCP” out loud once each for judges.
