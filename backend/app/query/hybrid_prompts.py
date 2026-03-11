"""Prompts for Mode C hybrid search (vector + KG combined)."""

from __future__ import annotations

HYBRID_SYSTEM_PROMPT = """\
당신은 Knowledge Graph + 문서 검색 기반 Q&A 어시스턴트입니다.
아래 규칙을 반드시 따르세요:

1. 주어진 "그래프 컨텍스트"와 "문서 컨텍스트"만 사용하여 답변하세요. 외부 지식을 사용하지 마세요.
2. 두 가지 소스의 정보를 종합하여 답변하세요.
3. 답변은 질문의 언어(한국어/영어)에 맞춰 작성하세요.
4. 각 주장의 출처를 명시하세요 (그래프/문서).
5. 소스가 충돌하면 두 소스를 모두 인용하고 불확실성을 명시하세요.
6. 컨텍스트에 답변할 정보가 없으면 "제공된 데이터에서 해당 정보를 찾을 수 없습니다."라고 답하세요.

답변 형식:
답변: [답변 내용]
출처:
- [그래프] 또는 [문서: 파일명] 형태로 나열
"""


def build_hybrid_messages(
    question: str,
    document_context: str,
    graph_context: str,
) -> list[dict[str, str]]:
    """Build message list for hybrid LLM call."""
    parts: list[str] = []

    if graph_context:
        parts.append(f"=== 그래프 컨텍스트 ===\n{graph_context}")

    if document_context:
        parts.append(f"=== 문서 컨텍스트 ===\n{document_context}")

    if not parts:
        parts.append("(검색된 컨텍스트가 없습니다)")

    context = "\n\n".join(parts)

    return [
        {"role": "user", "content": f"{context}\n\n질문: {question}"},
    ]


def parse_hybrid_answer(raw: str) -> tuple[str, list[str]]:
    """Parse LLM response into (answer, sources).

    Expected format:
        답변: ...
        출처:
        - [그래프] ...
        - [문서: file.pdf] ...
    """
    answer = raw.strip()
    sources: list[str] = []

    if "답변:" in raw:
        parts = raw.split("답변:", 1)
        rest = parts[1].strip()
        if "출처:" in rest:
            answer_part, sources_part = rest.split("출처:", 1)
            answer = answer_part.strip()
            for line in sources_part.strip().split("\n"):
                line = line.strip().lstrip("- ").strip()
                if line:
                    sources.append(line)
        else:
            answer = rest

    return answer, sources
