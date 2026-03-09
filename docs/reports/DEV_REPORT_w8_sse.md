# GraphRAG - SSE 스트리밍 + 프로덕션 안정성 (Week 8+)

## 구현 요약

### 1. SSE (Server-Sent Events) 실시간 스트리밍

#### 아키텍처

```
[Frontend]                         [Backend]

ReviewPage.tsx                     GET /kg/build/{id}/stream
  EventSource ──── SSE ──────────> _kg_build_event_generator
  onProgress/onDone                  asyncio.sleep(0.5) polling
                                     _jobs dict (thread-safe)

QueryPage.tsx                      POST /api/v1/query/stream
  fetch + ReadableStream ── SSE -> _query_stream_generator
  onMetadata/onToken/onComplete      Mode A: single 'complete' event
                                     Mode B: metadata → token* → complete
                                       ↓
                                     _stream_llm_tokens()
                                       asyncio.Queue bridge
                                       sync LLM → async tokens
```

#### KG 빌드 SSE (`GET /api/v1/kg/build/{job_id}/stream`)
- `EventSource` (native GET) — 커스텀 헤더 불가 → `?api_key=` 쿼리 파라미터 지원
- 0.5초 간격 async polling (기존 2초 setInterval 대체)
- 이벤트: `progress` (상태 변경 시) → `done` (succeeded/failed)
- 클라이언트 disconnect 감지: `request.is_disconnected()`

#### Q&A 토큰 스트리밍 (`POST /api/v1/query/stream`)
- `fetch + ReadableStream` (POST 지원 필요)
- Mode A: `run_query()` → 단일 `complete` 이벤트 (빠름, <100ms)
- Mode B: `run_local_query_stream()` → `metadata` → `token`* → `complete`
- LLM 브릿지: `asyncio.Queue` + `run_in_executor`로 sync→async 변환

#### Token 추적 Race Condition 해결
- **Before**: `_stream_llm_tokens._last_usage` 함수 속성 (전역 공유, 동시 요청 시 덮어쓰기)
- **After**: `_StreamResult` 인스턴스를 호출자가 생성 → per-call 격리

```python
class _StreamResult:
    __slots__ = ("input_tokens", "output_tokens")
    def __init__(self): ...

# 호출 시:
usage = _StreamResult()
async for token in _stream_llm_tokens(question, subgraph_text, usage):
    yield token
tokens = usage.total  # thread-safe, per-call
```

### 2. 에러 핸들러 보강

| Exception | HTTP | 상태 |
|-----------|------|------|
| `LLMEnrichmentError` | 502 | 기존 정의 → **핸들러 등록 누락** → 수정 |
| `WisdomError` (신규) | 502 | `LocalSearchError` 오용 → 전용 타입 분리 |
| `MappingValidationError` | 422 | 신규 매핑 검증 |

### 3. Neo4j 인덱스 확장

**Before**: key property UNIQUE constraint + name 인덱스만
**After**: 전체 non-key property에 인덱스 자동 생성

```python
for prop in nt.properties:
    if prop.name != key_prop:
        session.execute_write(_create_index, lbl, prop.name)
```

효과: email, phone, price, stock, status 등 자주 검색되는 속성의 local search / template query 성능 향상

### 4. 의존성 수정

- `requirements.txt`에 `sse-starlette>=2.0.0` 추가 (Docker/CI 빌드 시 필수)

---

## 파일 변경 내역

### 신규 파일
| 파일 | 설명 |
|------|------|
| `backend/app/routers/sse.py` | SSE 엔드포인트 2개 (KG build stream + query stream) |
| `backend/tests/test_sse.py` | SSE 테스트 7개 (asyncio-only) |
| `frontend/src/api/sse.ts` | SSE 클라이언트 (EventSource + fetch ReadableStream) |

### 수정 파일
| 파일 | 변경 |
|------|------|
| `backend/app/main.py` | SSE 라우터 등록, LLMEnrichmentError/WisdomError 핸들러 등록 |
| `backend/app/exceptions.py` | WisdomError 클래스 + 핸들러 추가 |
| `backend/app/query/local_search.py` | `_StreamResult` + `_stream_llm_tokens` + `run_local_query_stream` |
| `backend/app/query/wisdom_engine.py` | `LocalSearchError` → `WisdomError` 교체 |
| `backend/app/kg_builder/loader.py` | 전체 property 인덱스 자동 생성 |
| `backend/tests/test_wisdom.py` | Wisdom API 통합 테스트 4개 추가 |
| `frontend/src/pages/ReviewPage.tsx` | setInterval → SSE streamKGBuild 교체 |
| `frontend/src/pages/QueryPage.tsx` | Mode B SSE 스트리밍 + 타이핑 커서 |
| `frontend/src/types/ontology.ts` | ChatMessage.streaming 필드 |
| `requirements.txt` | sse-starlette 추가 |
| `README.md` | 신규 API 엔드포인트 6개 + 프로젝트 구조 갱신 |

---

## 테스트 현황

| 카테고리 | 테스트 수 |
|---------|----------|
| 기존 테스트 | 299 |
| SSE 테스트 (신규) | 7 |
| Wisdom 통합 테스트 (신규) | 4 |
| 기타 추가 | 8 |
| **합계** | **318 passed** |

---

## 프론트엔드 SSE UX

### KG 빌드 실시간 진행률
- `EventSource` → `onProgress` 콜백으로 `setBuildJob` 직접 업데이트
- 2초 폴링 → 0.5초 SSE push (지연 75% 감소)
- `onDone` 시 자동 연결 종료 + 성공/실패 메시지

### Q&A 토큰 스트리밍 (Mode B)
- placeholder 메시지 추가 → `onToken`마다 content append
- 타이핑 커서 (`animate-pulse` span) — streaming 상태 시 표시
- `onComplete` 시 최종 QueryResponse로 교체 (메타데이터 + 배지 표시)
- Mode A/W는 기존 fetch 유지 (빠르므로 스트리밍 불필요)
