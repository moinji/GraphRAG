"""Prompts for Text2Cypher (Mode D) — NL → Cypher → answer."""

from __future__ import annotations

import json

TEXT2CYPHER_SYSTEM = """\
You are a Cypher query generator for Neo4j.
Given a graph schema and a user question, generate a single valid Cypher READ query.

Rules:
- Output ONLY the Cypher query. No markdown, no backticks, no explanation.
- Use ONLY READ operations: MATCH, OPTIONAL MATCH, RETURN, WITH, WHERE, ORDER BY, LIMIT, SKIP, UNWIND, UNION, CALL (read-only).
- NEVER use write operations: CREATE, MERGE, SET, DELETE, REMOVE, DROP, FOREACH, LOAD CSV.
- Use ONLY the node labels, relationship types, and properties listed in the schema.
- Always RETURN meaningful results with descriptive aliases.
- For Korean questions, match Korean property values when appropriate.
- Use count(), sum(), avg(), collect(), DISTINCT, etc. for aggregate questions.
- Use shortestPath() or allShortestPaths() for path questions.
- Limit results to 20 unless the user asks for more.
"""

TEXT2CYPHER_ANSWER_SYSTEM = """\
You are a helpful assistant. Given a user question and Neo4j query results, \
provide a clear, concise natural language answer.
- Answer in the SAME LANGUAGE as the question (Korean → Korean, English → English).
- If results are empty, state that no matching data was found.
- Format numbers with commas for readability.
- Keep the answer under 3 sentences unless complexity demands more.
"""

_FEW_SHOT_EXAMPLES = [
    {
        "question": "고객 김민수가 주문한 상품은?",
        "cypher": (
            "MATCH (c:Customer {name: '김민수'})-[:PLACED]->(o:Order)-[:CONTAINS]->(p:Product) "
            "RETURN DISTINCT p.name AS product"
        ),
    },
    {
        "question": "How many orders are there?",
        "cypher": "MATCH (o:Order) RETURN count(o) AS total_orders",
    },
    {
        "question": "가장 많은 주문을 한 고객 Top 3는?",
        "cypher": (
            "MATCH (c:Customer)-[:PLACED]->(o:Order) "
            "RETURN c.name AS customer, count(o) AS order_count "
            "ORDER BY order_count DESC LIMIT 3"
        ),
    },
    {
        "question": "Electronics 카테고리 상품을 공급하는 공급업체는?",
        "cypher": (
            "MATCH (s:Supplier)<-[:SUPPLIED_BY]-(p:Product)-[:BELONGS_TO]->(c:Category {name: 'Electronics'}) "
            "RETURN DISTINCT s.name AS supplier"
        ),
    },
]


def build_cypher_messages(question: str, schema_text: str) -> list[dict]:
    """Build message list for Cypher generation with few-shot examples."""
    messages: list[dict] = []

    # Few-shot examples
    for ex in _FEW_SHOT_EXAMPLES:
        messages.append({"role": "user", "content": f"Schema:\n{schema_text}\n\nQuestion: {ex['question']}"})
        messages.append({"role": "assistant", "content": ex["cypher"]})

    # Actual question
    messages.append({"role": "user", "content": f"Schema:\n{schema_text}\n\nQuestion: {question}"})
    return messages


def build_answer_messages(
    question: str, cypher: str, results: list[dict], max_results: int = 20,
) -> list[dict]:
    """Build message list for answer synthesis from query results."""
    truncated = results[:max_results]
    # Serialize results safely
    try:
        results_text = json.dumps(truncated, ensure_ascii=False, default=str, indent=2)
    except Exception:
        results_text = str(truncated)

    content = (
        f"Question: {question}\n\n"
        f"Cypher query executed:\n{cypher}\n\n"
        f"Results ({len(results)} total, showing first {len(truncated)}):\n{results_text}"
    )
    return [{"role": "user", "content": content}]
