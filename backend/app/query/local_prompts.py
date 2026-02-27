"""B안 Local Search prompts and serialization utilities."""

from __future__ import annotations

LOCAL_SEARCH_SYSTEM_PROMPT = """\
당신은 Knowledge Graph 기반 Q&A 어시스턴트입니다.
아래 규칙을 반드시 따르세요:

1. 주어진 서브그래프 컨텍스트만 사용하여 답변하세요. 외부 지식을 사용하지 마세요.
2. 답변은 한국어로 작성하세요.
3. 답변 후 근거 경로를 포함하세요.
4. 컨텍스트에 답변할 정보가 없으면 "제공된 그래프 데이터에서 해당 정보를 찾을 수 없습니다."라고 답하세요.

답변 형식:
답변: [답변 내용]
근거 경로: [노드]-[관계]->[노드] 형태로 나열
"""


def build_local_search_messages(
    question: str, subgraph_text: str
) -> list[dict[str, str]]:
    """Build message list for Claude API call."""
    return [
        {"role": "user", "content": (
            f"서브그래프 컨텍스트:\n{subgraph_text}\n\n"
            f"질문: {question}"
        )},
    ]


def serialize_subgraph(
    anchor_label: str,
    anchor_name: str,
    hop1: list[dict],
    hop2: list[dict],
) -> str:
    """Convert subgraph records into structured text for LLM context."""
    lines: list[str] = []
    lines.append(f"[앵커 노드] {anchor_label}: {anchor_name}")
    lines.append("")

    if hop1:
        lines.append("[1홉 연결]")
        seen = set()
        for node in hop1:
            label = node.get("label", "?")
            name = node.get("name", "?")
            rel = node.get("rel", "?")
            key = f"{label}:{name}:{rel}"
            if key in seen:
                continue
            seen.add(key)
            props = node.get("props", {})
            props_str = ""
            if props:
                prop_parts = [f"{k}={v}" for k, v in props.items()
                              if k != "name" and v is not None]
                if prop_parts:
                    props_str = f" ({', '.join(prop_parts)})"
            lines.append(f"  -{rel}-> {label}({name}){props_str}")
        lines.append("")

    if hop2:
        lines.append("[2홉 연결]")
        seen = set()
        for node in hop2:
            label = node.get("label", "?")
            name = node.get("name", "?")
            rel = node.get("rel", "?")
            key = f"{label}:{name}:{rel}"
            if key in seen:
                continue
            seen.add(key)
            props = node.get("props", {})
            props_str = ""
            if props:
                prop_parts = [f"{k}={v}" for k, v in props.items()
                              if k != "name" and v is not None]
                if prop_parts:
                    props_str = f" ({', '.join(prop_parts)})"
            lines.append(f"  -{rel}-> {label}({name}){props_str}")

    return "\n".join(lines)


def serialize_aggregate_results(records: list[dict]) -> str:
    """Convert aggregate Cypher results into structured text."""
    lines: list[str] = []
    lines.append("[집계 결과]")
    for i, rec in enumerate(records, 1):
        parts = [f"{k}={v}" for k, v in rec.items() if v is not None]
        lines.append(f"  {i}. {', '.join(parts)}")
    return "\n".join(lines)


def parse_local_answer(raw: str) -> tuple[str, list[str]]:
    """Parse LLM response into (answer, paths).

    Expected format:
        답변: ...
        근거 경로: path1, path2, ...
    """
    answer = raw.strip()
    paths: list[str] = []

    if "답변:" in raw:
        parts = raw.split("답변:", 1)
        rest = parts[1].strip()
        if "근거 경로:" in rest:
            answer_part, paths_part = rest.split("근거 경로:", 1)
            answer = answer_part.strip()
            raw_paths = paths_part.strip()
            for line in raw_paths.split("\n"):
                line = line.strip().lstrip("- ").strip()
                if line:
                    paths.append(line)
        else:
            answer = rest

    return answer, paths
