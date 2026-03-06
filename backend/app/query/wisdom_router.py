"""Wisdom intent classifier — regex-based routing for DIKW Wisdom queries."""

from __future__ import annotations

import re
from enum import Enum


class WisdomIntent(str, Enum):
    LOOKUP = "lookup"
    PATTERN = "pattern"
    CAUSAL = "causal"
    RECOMMENDATION = "recommendation"
    WHAT_IF = "what_if"
    DIKW_TRACE = "dikw_trace"


_WISDOM_PATTERNS: dict[WisdomIntent, list[re.Pattern]] = {
    WisdomIntent.DIKW_TRACE: [
        re.compile(r"DIKW", re.IGNORECASE),
        re.compile(r"(전체|종합).*(분석|보고서|리포트)"),
        re.compile(r"(데이터부터|처음부터).*(분석|추적)"),
    ],
    WisdomIntent.WHAT_IF: [
        re.compile(r"(만약|만일)"),
        re.compile(r"(중단|제거|이탈|없어지면|빠지면|중지)"),
        re.compile(r"~?면\s*(어떻게|어떤|무슨)"),
        re.compile(r"(영향|리스크|위험).*있"),
    ],
    WisdomIntent.RECOMMENDATION: [
        re.compile(r"(추천|제안|권장)"),
        re.compile(r"어떤.*좋을까"),
        re.compile(r"뭘.*해야"),
        re.compile(r"(강화|개선|최적화).*해야"),
        re.compile(r"(주의|관리).*해야"),
    ],
    WisdomIntent.CAUSAL: [
        re.compile(r"왜\s"),
        re.compile(r"(원인|이유|인과)"),
        re.compile(r"(영향.*미치|때문|덕분)"),
        re.compile(r"(상관관계|상관)"),
    ],
    WisdomIntent.PATTERN: [
        re.compile(r"(패턴|트렌드|경향|특징|분포|세그먼트|클러스터)"),
        re.compile(r"(자주|많이).*같이.*(구매|주문)"),
        re.compile(r"어떤.*(특징|차이|공통점)"),
        re.compile(r"(분석|인사이트|통찰)"),
    ],
}


def classify_wisdom_intent(question: str) -> WisdomIntent:
    """Classify question into a Wisdom intent.

    Checks in priority order: dikw_trace > what_if > recommendation > causal > pattern > lookup.
    """
    for intent, patterns in _WISDOM_PATTERNS.items():
        for pat in patterns:
            if pat.search(question):
                return intent
    return WisdomIntent.LOOKUP
