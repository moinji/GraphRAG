# GraphRAG v5.0 개발 보고서 — 비정형 데이터 레이어
> 작성일: 2026-03-11 | 버전: 5.0.0

---

## 1. 요약

v5.0은 **정형 데이터(DDL/CSV) 전용 → 비정형 데이터(PDF/DOCX/MD/HTML) 지원**으로의 확장입니다. 문서를 업로드하면 자동으로 파싱·청킹·임베딩·벡터 저장·NER·KG 링킹까지 수행하며, Mode C 하이브리드 검색으로 문서+그래프를 결합한 답변을 생성합니다.

| Feature | 설명 | Sprint |
|---------|------|--------|
| **F-01** 문서 수집 파이프라인 | 5종 포맷 파서, 3종 청킹, 3단계 임베딩 폴백 | S1 |
| **F-02** pgvector 벡터 저장소 | HNSW 코사인 인덱스, 테넌트 격리, CRUD | S1 |
| **F-03** Mode C 하이브리드 검색 | 벡터+KG 컨텍스트 → LLM 합성 → 소스 인용 | S2 |
| **F-04** 2-stage NER | KG 노드명 매칭 → LLM NER 폴백 | S3 |
| **F-05** Document-KG 링커 | Document/Chunk Neo4j 노드, MENTIONS 관계 | S3 |
| **F-06** 리랭커 | 키워드 오버랩 + LLM 교차인코더 | S4 |
| **F-07** Mode C 평가 | 15개 비정형 골든 데이터, run_evaluation_c | S4 |
| **프론트엔드** | DocumentsPage, Mode C 토글, 소스 인용 UI | S3 |

**변경 규모**: 40 files changed, 4,959 insertions, 11 deletions
**테스트**: 545 전체 통과 (192 신규), 0 regression

---

## 2. F-01: 문서 수집 파이프라인

### 2.1 멀티포맷 파서 (`document/parser.py`)

```
[파일 업로드] → detect_file_type → 포맷별 파서
                                    ├── PDF: PyMuPDF → pdfplumber 폴백
                                    ├── DOCX: python-docx 문단 추출
                                    ├── MD: regex 마크다운 스트립
                                    ├── HTML: BeautifulSoup → regex 폴백
                                    └── TXT: 인코딩 자동 감지
```

- `ParsedPage(page_num, text)`, `ParsedDocument(pages, full_text, errors, page_count)`
- 한국어 인코딩 체인: utf-8-sig → utf-8 → cp949 → euc-kr
- 26개 테스트 커버리지

### 2.2 청킹 엔진 (`document/chunker.py`)

| 전략 | 설명 | 적합 문서 |
|------|------|-----------|
| **recursive** | 문단 → 문장 → 문자 계층적 분할 | 일반 텍스트 (기본값) |
| **fixed** | 고정 크기 윈도우 | 로그, 코드 |
| **sentence** | 문장 단위 분할 | 법률, 학술 |

- 기본값: chunk_size=1000, chunk_overlap=200 (문자 단위)
- `Chunk(text, index, char_start, char_end, char_count, metadata)`
- `chunk_pages()`: 페이지별 메타데이터 보존 (page_num 추적)
- 18개 테스트 커버리지

### 2.3 임베딩 서비스 (`document/embedder.py`)

```
embed_texts(texts)
  ├── Stage 1: OpenAI text-embedding-3-small (1536차원)
  ├── Stage 2: sentence-transformers 로컬 모델 (폴백)
  └── Stage 3: 제로 벡터 [0.0, ...] (최후 수단)
```

- 배치 처리: `embedding_batch_size=100`
- 각 단계 실패 시 다음 단계로 자동 전환 (non-fatal)
- 8개 테스트 커버리지

### 2.4 처리 파이프라인 (`document/pipeline.py`)

```
process_document(filename, content, tenant_id)
  → Step 1: insert_document (PG, status=processing)
  → Step 2: parse_document → ParsedDocument
  → Step 3: chunk_pages/chunk_text → Chunk[]
  → Step 4: embed_texts → embeddings[]
  → Step 5: upsert_chunks (pgvector)
  → Step 6: link_document_to_kg (Neo4j, best-effort)
  → Step 7: update_document_status → "ready"
```

- `BackgroundTasks` 호환 (비동기 처리)
- 실패 시 status="failed" 마킹 + 에러 로깅
- KG 링킹 실패는 non-fatal (문서 처리 자체는 성공)

---

## 3. F-02: pgvector 벡터 저장소

### 3.1 스키마 (`db/vector_store.py`)

```sql
CREATE TABLE documents (
    document_id SERIAL PRIMARY KEY,
    filename TEXT, file_type TEXT, file_size INT,
    page_count INT, chunk_count INT,
    status TEXT DEFAULT 'processing',  -- processing | ready | failed
    tenant_id TEXT, created_at TIMESTAMPTZ
);

CREATE TABLE chunks (
    chunk_id SERIAL PRIMARY KEY,
    document_id INT REFERENCES documents,
    chunk_index INT, text TEXT,
    embedding vector(1536),  -- pgvector
    char_count INT, metadata JSONB, tenant_id TEXT
);

CREATE INDEX idx_chunks_embedding ON chunks
    USING hnsw (embedding vector_cosine_ops);
```

### 3.2 인프라 변경

- `docker-compose.yml`: `postgres:16-alpine` → `pgvector/pgvector:pg16`
- `migrations.py`: 앱 시작 시 `ensure_vector_tables()` 자동 호출
- 테넌트 격리: 모든 쿼리에 `WHERE tenant_id = $1` 조건

### 3.3 API (`routers/documents.py`)

| Method | Endpoint | 설명 |
|--------|----------|------|
| POST | `/api/v1/documents/upload` | 멀티파트 파일 업로드 → 백그라운드 처리 |
| GET | `/api/v1/documents` | 문서 목록 (테넌트 스코프) |
| GET | `/api/v1/documents/{id}` | 문서 상세 |
| DELETE | `/api/v1/documents/{id}` | 문서 + 청크 캐스케이드 삭제 |

---

## 4. F-03: Mode C 하이브리드 검색

### 4.1 파이프라인 (`query/hybrid_search.py`)

```
run_hybrid_query(question, tenant_id)
  → Step 1:   vector search (embed → pgvector cosine similarity)
  → Step 1.5: rerank (키워드 + LLM 교차인코더)
  → Step 2:   KG context enrichment (엔티티 추출 → 1-hop 이웃)
  → Step 3:   document context formatting (top-5 청크)
  → Step 4:   LLM synthesis (OpenAI → Anthropic → 원본 폴백)
  → Step 5:   DocumentSource 인용 목록 생성
```

### 4.2 Mode A/B/C 비교

| | Mode A (템플릿) | Mode B (로컬 서치) | Mode C (하이브리드) |
|---|---|---|---|
| **데이터 소스** | KG only | KG subgraph | 문서 + KG |
| **검색** | Cypher 템플릿 | 엔티티 → 서브그래프 | 벡터 유사도 + KG |
| **LLM** | 불필요 | 요약 생성 | 합성 + 인용 |
| **적합** | 정형 질의 | 탐색적 질의 | 비정형 + 정형 혼합 |
| **인용** | Cypher 경로 | 서브그래프 | 문서 소스 + 그래프 |

### 4.3 프롬프트 설계 (`query/hybrid_prompts.py`)

- 시스템 프롬프트: 그래프+문서 컨텍스트 전용 답변, 소스 충돌 시 양쪽 인용
- 답변 형식: `답변: [내용]` + `출처: [그래프]/[문서: 파일명]`
- 언어 자동 감지: 한글 포함 여부로 한국어/영어 전환

---

## 5. F-04: 2-stage NER

### 5.1 아키텍처 (`document/ner.py`)

```
extract_entities(text, tenant_id)
  → Stage 1: _kg_match_ner
  │  └── Neo4j 노드명 로드 → 텍스트 내 정확 매칭 (대소문자 무시)
  │  └── 긴 이름 우선 매칭, 위치 정렬
  │  └── confidence: 1.0, source: "kg_match"
  │
  → Stage 2: _llm_ner (KG 매칭 < 3개일 때만)
     └── OpenAI → Anthropic JSON NER 추출
     └── confidence: 0.7, source: "llm"
     └── 실패 시 non-fatal
```

- 중복 제거: `(name, label)` 튜플 기준
- `max_entities=20` 상한
- 프로젝트 패턴 준수: "규칙 먼저 → LLM 폴백"

### 5.2 ExtractedEntity

```python
@dataclass
class ExtractedEntity:
    name: str           # "김민수"
    label: str          # "Customer"
    confidence: float   # 0.0-1.0
    source: str         # "kg_match" | "llm"
    char_start: int     # 텍스트 내 시작 위치
    char_end: int       # 텍스트 내 끝 위치
```

---

## 6. F-05: Document-KG 링커

### 6.1 링킹 파이프라인 (`document/linker.py`)

```
link_document_to_kg(document_id, chunks, tenant_id)
  → Step 1: Document 노드 생성 (MERGE)
  → Step 2: 청크별 Chunk 노드 + HAS_CHUNK 관계
  → Step 3: 청크별 NER → ExtractedEntity[]
  → Step 4: confidence ≥ threshold → MENTIONS 관계 생성
```

### 6.2 Neo4j 그래프 확장

```
기존:  (Customer)-[PLACED]->(Order)-[CONTAINS]->(Product)
                                                    ↑
v5.0:  (Document)-[HAS_CHUNK]->(Chunk)-[MENTIONS]──┘
```

- `Document {doc_id, filename, file_type, tenant_id}`
- `Chunk {doc_id, chunk_index, text_preview, page_num}`
- `MENTIONS {confidence, source}` — NER 결과 기반
- `unlink_document_from_kg()`: 문서 삭제 시 Neo4j 정리

---

## 7. F-06: 리랭커

### 7.1 2-stage 리랭킹 (`query/reranker.py`)

```
rerank(question, results, top_k)
  → Stage 1: _keyword_rerank (항상 실행)
  │  └── 질문 키워드 추출 (불용어 제거, 한/영 지원)
  │  └── 결합 점수 = 벡터유사도×0.7 + 키워드비율×0.3
  │
  → Stage 2: _llm_rerank (결과 > 3개 + API 키 존재 시)
     └── LLM에 청크 프리뷰 전달 → 0-10 관련도 점수
     └── 기존 점수×0.5 + LLM 점수×0.5 블렌딩
```

- 불용어 필터링: 한국어 18개, 영어 20개
- LLM 리랭킹은 top-10 청크만 대상 (비용 제어)
- `hybrid_search.py` Step 1.5에 통합 (벡터 검색 직후, KG 보강 직전)

---

## 8. F-07: Mode C 평가

### 8.1 골든 데이터 (`evaluation/qa_golden_unstructured.py`)

| 카테고리 | 건수 | 설명 |
|----------|------|------|
| **doc_only** | 5 | 문서에만 존재하는 정보 (배터리, 반품 정책 등) |
| **hybrid** | 5 | 문서 + KG 결합 필요 (구매 이력 + 사양) |
| **doc_entity** | 5 | NER로 발견된 엔티티 관련 질의 |
| **합계** | **15** | |

### 8.2 평가 API

| Method | Endpoint | 설명 |
|--------|----------|------|
| GET | `/api/v1/evaluation/golden/unstructured` | 비정형 15개 골든 반환 |
| POST | `/api/v1/evaluation/run-c` | Mode C 전체 평가 실행 |

- `run_evaluation_c()`: 기존 `evaluate_single()` 재사용 (keyword/entity 점수)
- 기존 A/B 평가와 동일한 `QASingleResult` 스키마

---

## 9. 프론트엔드

### 9.1 DocumentsPage (`pages/DocumentsPage.tsx`)

- 파일 업로드: 드래그&드롭 스타일, PDF/DOCX/MD/HTML/TXT
- 문서 목록: 파일명, 타입, 크기, 청크 수, 상태, 삭제
- 3초 폴링: 처리 중 문서 자동 새로고침
- 상태 배지: 완료(초록), 처리중(노랑 펄스), 실패(빨강)
- "Q&A (Mode C)" 버튼: 준비된 문서 존재 시 활성화

### 9.2 QueryPage Mode C 확장

- Mode 토글: A(파랑), B(주황), C(보라)
- 문서 소스 접기/펼치기: 파일명, 페이지, 관련도%, 청크 미리보기
- Mode C는 일반 fetch 사용 (Mode A와 동일, SSE 아님)

### 9.3 네비게이션

- App.tsx: `/documents` 라우트 + "문서 관리" 보라색 네비 버튼
- `DocumentsPage` lazy import (코드 스플리팅)

---

## 10. 설정 변경

### 10.1 config.py 추가 설정 (7개)

| 설정 | 기본값 | 설명 |
|------|--------|------|
| `embedding_model` | text-embedding-3-small | 임베딩 모델 |
| `embedding_batch_size` | 100 | 배치 크기 |
| `doc_max_file_size_mb` | 50 | 최대 파일 크기 |
| `doc_max_files` | 10 | 최대 동시 업로드 |
| `doc_chunk_size` | 1000 | 청크 크기 (문자) |
| `doc_chunk_overlap` | 200 | 청크 오버랩 |
| `doc_chunk_strategy` | recursive | 청킹 전략 |

### 10.2 인프라

- Docker: `pgvector/pgvector:pg16` (pgvector 확장 내장)
- 예외: `DocumentValidationError(422)`, `DocumentNotFoundError(404)`, `EmbeddingError(502)`

---

## 11. 테스트 현황

| 테스트 파일 | 건수 | 범위 |
|------------|------|------|
| test_document_parser.py | 26 | 5종 포맷 파싱, 인코딩, 에러 |
| test_chunker.py | 18 | 3종 전략, 오버랩, 페이지 |
| test_embedder.py | 8 | 3단계 폴백, 배치, 제로벡터 |
| test_document_pipeline.py | 8 | 파이프라인 성공/실패/에지케이스 |
| test_document_api.py | 14 | 4개 엔드포인트 CRUD |
| test_vector_search.py | 10 | 유사도 검색, 포맷팅 |
| test_hybrid_search.py | 19 | Mode C 파이프라인, LLM 폴백 |
| test_ner.py | 22 | KG 매칭, LLM NER, 중복 제거 |
| test_linker.py | 12 | 노드 생성, MENTIONS, 언링크 |
| test_reranker.py | 16 | 키워드 리랭킹, LLM 점수, 파싱 |
| test_e2e_hybrid.py | 18 | 업로드→검색→링킹→평가 E2E |
| **v5.0 신규 합계** | **171** | |
| **기존 테스트** | **374** | |
| **전체** | **545** | 0 regression |

---

## 12. 아키텍처 전체도

```
┌─────────────────── 프론트엔드 ───────────────────┐
│  UploadPage → ReviewPage → QueryPage             │
│                               ↑                  │
│  DocumentsPage ───────────────┘                  │
│   (업로드/관리/Mode C)                            │
└─────────────────────┬────────────────────────────┘
                      │ REST API
┌─────────────────────▼────────────────────────────┐
│                  FastAPI 백엔드                    │
│                                                   │
│  ┌─ 정형 파이프라인 ─┐   ┌─ 비정형 파이프라인 ─┐  │
│  │ DDL → Ontology    │   │ 문서 → Parse       │  │
│  │ → KG Build        │   │ → Chunk → Embed    │  │
│  │ → Mode A/B Query  │   │ → pgvector Store   │  │
│  └───────────────────┘   │ → NER → KG Link    │  │
│           ↕               └────────┬──────────┘  │
│      Mode C 하이브리드 ←───────────┘              │
│      (벡터 + KG → 리랭크 → LLM → 인용)           │
└───────┬──────────────────┬───────────────────────┘
        │                  │
   ┌────▼────┐       ┌────▼─────┐
   │  Neo4j  │       │ PG+pgvec │
   │   KG    │       │ 문서/임베딩│
   └─────────┘       └──────────┘
```

---

## 13. 핵심 설계 원칙

| 원칙 | 적용 |
|------|------|
| **규칙 먼저, LLM 폴백** | NER(KG매칭→LLM), 리랭킹(키워드→LLM), 임베딩(OpenAI→로컬→제로) |
| **Non-fatal 외부 의존성** | KG 링킹 실패 → 문서 처리 계속, LLM 실패 → 원본 반환 |
| **테넌트 격리** | 벡터 검색, NER, 링킹 모두 tenant_id 필터 |
| **기존 코드 최소 변경** | pipeline.py +6줄, query.py +1줄, 기존 A/B 완전 무영향 |
| **점진적 확장** | Mode A(v0.5) → B(v0.6) → C(v5.0), 동일 QueryResponse 스키마 |
