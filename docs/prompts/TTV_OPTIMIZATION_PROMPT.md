# TTV 최소화 구현 프롬프트

> GraphRAG 프로젝트의 Time To Value를 최소화하기 위한 종합 최적화 구현 지시서.
> 목표: DDL 업로드 → 첫 번째 인사이트 답변까지 **20초 이내**.

---

## 1. 현재 TTV 경로 및 병목 분석

### 전체 경로 (사용자 관점)

```
[1] DDL 파일 드래그 앤 드롭
    └→ POST /api/v1/ddl/upload → ERD 파싱
[2] "Generate" 클릭
    └→ POST /api/v1/ontology/generate → FK 규칙 엔진 + (LLM enrichment)
[3] "Approve" 클릭
    └→ POST /api/v1/ontology/versions/{id}/approve
[4] "Build KG" 클릭
    └→ POST /api/v1/kg/build (202) → 백그라운드 빌드 시작
    └→ GET /api/v1/kg/build/{job_id} (2초 간격 폴링)
[5] 빌드 완료 → "Q&A" 버튼 클릭
[6] 데모 질문 클릭 → 첫 답변 표시
```

### 단계별 소요시간 (실측 기준)

```
단계                현재 (초)      이상 (초)     병목 원인
─────────────────────────────────────────────────────────────
[1] DDL 업로드        0.2           0.2         -
[2] 온톨로지 생성     0.3~8.0       0.3         LLM enrichment (skip_llm=true면 0.3초)
[3] Approve          0.1           0.1         -
[4] KG 빌드          10~30         1.5         ★★★ _ensure_name() LLM 호출이 주범
    ├ 데이터 생성     0.1           0.1
    ├ FK 검증         0.01          0.01
    ├ Neo4j 접속대기  0.5~90        0.3         neo4j_connect_timeout=90 과다
    ├ DB 정리+제약    0.3           0.3
    ├ 노드 로딩       8~27          0.5         ★ _ensure_name() → LLM 5~6회 직렬 호출
    └ 관계 로딩       0.3           0.3
[5] 페이지 전환       0.1           0.0         버튼 클릭 필요 → 자동 전환 가능
[6] 첫 Q&A 답변      0~3           0            demo_cache 히트 시 0초

총합               11~140초       2.8초
─────────────────────────────────────────────────────────────
```

### 병목 상세 분석

#### 병목 #1: `_ensure_name()` — 노드 타입당 LLM API 직렬 호출 (8~27초)

```python
# backend/app/kg_builder/loader.py:240-248
for nt in ontology.node_types:        # 9개 노드 타입
    ...
    rows = _ensure_name(nt.name, rows, prop_names)  # ← LLM 호출!
```

`_ensure_name()` → `_ask_llm_name_template()` → `_try_openai()` / `_try_anthropic()`

- `name` 속성이 없는 노드 타입(Order, Payment, Review, Address, Shipping, Coupon)마다 호출
- E-commerce 기준: **5~6회 직렬 LLM 호출** × 1.5~4.5초/회 = **8~27초**
- 캐싱 없음: 매 빌드마다 동일한 LLM 호출 반복
- 결과 예측 가능: 도메인이 같으면 템플릿도 동일

#### 병목 #2: `_wait_for_neo4j()` 타임아웃 (0~90초)

```python
# config.py
neo4j_connect_timeout: int = 90  # 90초나 기다림
```

Neo4j가 이미 떠 있으면 0.5초지만, AuraDB sleep 상태면 최대 90초 대기.
로컬 Docker 기준에서도 불필요하게 긴 타임아웃.

#### 병목 #3: 사용자 클릭 대기 (UX 마찰)

```
Approve → Build KG → (폴링 대기) → Q&A 버튼 → 질문 클릭
```

5번의 수동 클릭/대기가 필요. 일부는 자동화 가능.

---

## 2. 최적화 전략 (5가지)

### 전략 A: Display Name 템플릿 사전 정의 + 캐싱 (영향: -8~27초)

KG 빌드 시간의 80% 이상을 차지하는 `_ensure_name()` LLM 호출을 제거한다.

```python
# backend/app/kg_builder/loader.py — 수정

# 1. E-commerce 도메인 하드코딩 (LLM 호출 제로)
_ECOMMERCE_NAME_TEMPLATES: dict[str, str] = {
    "Order": "주문 #{id} ({status})",
    "Payment": "결제 #{id} ({method})",
    "Review": "리뷰 #{id} ({rating}점)",
    "Address": "{city} {district}",
    "Shipping": "배송 #{id} ({status})",
    "Coupon": "{code} ({discount_pct}%)",
}

# 2. 범용 도메인: 인메모리 캐시 (빌드 1회만 LLM 호출)
_name_template_cache: dict[str, str] = {}

def _ensure_name(label: str, rows: list[dict], prop_names: list[str]) -> list[dict]:
    if not rows:
        return rows
    if "name" in rows[0] and rows[0]["name"] is not None:
        return rows

    # Phase 1: 하드코딩 체크
    template = _ECOMMERCE_NAME_TEMPLATES.get(label)

    # Phase 2: 캐시 체크
    if template is None:
        template = _name_template_cache.get(label)

    # Phase 3: 규칙 기반 추론 (LLM 없이)
    if template is None:
        template = _infer_name_template(label, prop_names)

    # Phase 4: LLM 호출 (최후 수단, 결과 캐싱)
    if template is None:
        template = _ask_llm_name_template(label, prop_names, rows[0])
        if template:
            _name_template_cache[label] = template

    # Phase 5: 최종 폴백
    if template is None:
        template = f"{label} #{{id}}"

    # 템플릿 적용
    enriched = []
    for row in rows:
        r = dict(row)
        try:
            safe = defaultdict(str, {k: str(v) if v is not None else "" for k, v in r.items()})
            r["name"] = template.format_map(safe)
        except Exception:
            r["name"] = f"{label} #{r.get('id', '?')}"
        enriched.append(r)
    return enriched


def _infer_name_template(label: str, prop_names: list[str]) -> str | None:
    """규칙 기반 display name 추론 — LLM 호출 없이 즉시 반환."""
    # name/title/code가 있으면 그대로 사용
    for preferred in ("name", "title", "code", "이름", "제목"):
        if preferred in prop_names:
            return f"{{{preferred}}}"

    # label + id 조합
    if "id" in prop_names:
        # status나 type이 있으면 함께 표시
        for extra in ("status", "type", "method", "category"):
            if extra in prop_names:
                return f"{label} #{{id}} ({{" + extra + "}})"
        return f"{label} #{{id}}"

    return None
```

**효과**: E-commerce 빌드 시 LLM 호출 0회 → 노드 로딩 8~27초 → **0.5초**

### 전략 B: Neo4j 접속 타임아웃 축소 (영향: -0~85초)

```python
# backend/app/config.py — 수정
neo4j_connect_timeout: int = 10  # 90 → 10으로 축소 (로컬 Docker 기준)
```

로컬 환경에서는 Neo4j가 2초 안에 응답함. AuraDB 사용 시에만 환경변수로 늘리면 됨.

**효과**: 최악 케이스 90초 → 10초. 정상 시 변화 없음.

### 전략 C: Ontology Generate에서 skip_llm 기본값 변경 (영향: -0~8초)

```python
# backend/app/models/schemas.py
class OntologyGenerateRequest(BaseModel):
    erd: ERDSchema
    skip_llm: bool = True  # False → True: 데모에서는 FK 규칙만으로 충분
```

또는 프론트엔드에서 데모 모드일 때 `skip_llm=true`를 기본으로 보내기.

**효과**: 온톨로지 생성 8초 → 0.3초 (E-commerce 도메인)

### 전략 D: Auto-Flow 모드 — 클릭 자동화 (영향: -3~5초 UX 대기)

DDL 업로드 후 "데모 모드"를 선택하면 전체 파이프라인을 자동 실행:

```
DDL 업로드 → Auto Generate (skip_llm) → Auto Approve → Auto Build KG
→ 빌드 완료 시 자동으로 Q&A 페이지 전환
```

```typescript
// frontend/src/pages/UploadPage.tsx — 수정

async function handleAutoDemo(file: File) {
  // 1. DDL 업로드
  const erd = await uploadDDL(file);

  // 2. 온톨로지 생성 (skip_llm=true)
  const result = await generateOntology(erd, true);

  // 3. 자동 Approve
  if (result.version_id) {
    await approveVersion(result.version_id);
  }

  // 4. KG 빌드 시작
  const build = await startKGBuild(result.version_id!, erd);

  // 5. 빌드 완료 대기 (폴링)
  await waitForBuildComplete(build.build_job_id);

  // 6. Q&A 페이지로 자동 전환
  goToQueryPage();
}
```

**효과**: 5번의 수동 클릭/대기 → 1번 클릭으로 통합

### 전략 E: KG 빌드 진행상황 실시간 표시 (체감 TTV 단축)

빌드 중 단계별 프로그레스 바를 표시하여 **체감 대기 시간** 단축.
이미 `KGBuildProgress.current_step`이 있으므로 프론트엔드만 개선.

```typescript
// 단계별 메시지 + 프로그레스 바
const STEP_MESSAGES = {
  starting: { label: "준비 중...", pct: 0 },
  data_generation: { label: "샘플 데이터 생성 중...", pct: 25 },
  fk_verification: { label: "FK 무결성 검증 중...", pct: 50 },
  neo4j_load: { label: "Neo4j에 그래프 적재 중...", pct: 75 },
  completed: { label: "완료!", pct: 100 },
};
```

**효과**: 실제 시간 단축 없지만, 진행감 표시로 이탈 방지

---

## 3. 최적화 후 예상 TTV

```
단계                  현재        최적화 후     적용 전략
──────────────────────────────────────────────────────────
[1] DDL 업로드         0.2초       0.2초         -
[2] 온톨로지 생성      0.3~8초     0.3초         C (skip_llm 기본)
[3] Approve           0.1초       0초           D (자동)
[4] KG 빌드           10~30초     1.5초         A (LLM 제거) + B (타임아웃)
    ├ 데이터 생성      0.1         0.1
    ├ FK 검증          0.01        0.01
    ├ Neo4j 접속       0.5         0.3           B
    ├ DB 정리+제약     0.3         0.3
    ├ 노드 로딩        8~27        0.5           A ★★★
    └ 관계 로딩        0.3         0.3
[5] 페이지 전환        0.1초       0초           D (자동)
[6] 첫 Q&A 답변       0초         0초           (demo_cache)

총합                 11~39초      2.0초
──────────────────────────────────────────────────────────
```

---

## 4. 구현 파일 및 변경 사항

```
수정 (7개):
  backend/app/kg_builder/loader.py
    - _ECOMMERCE_NAME_TEMPLATES 하드코딩 추가
    - _name_template_cache 인메모리 캐시 추가
    - _infer_name_template() 규칙 기반 추론 함수 추가
    - _ensure_name() 4단계 워터폴 로직으로 교체

  backend/app/config.py
    - neo4j_connect_timeout: 90 → 10

  backend/app/models/schemas.py
    - OntologyGenerateRequest.skip_llm 기본값 True로 변경

  frontend/src/pages/UploadPage.tsx
    - "Auto Demo" 버튼 추가 → 전체 파이프라인 1-click 실행

  frontend/src/pages/ReviewPage.tsx
    - 빌드 프로그레스 바 개선 (단계별 메시지 + 퍼센트)

  frontend/src/components/review/BuildKGActions.tsx
    - 프로그레스 바 UI 컴포넌트 개선

  backend/tests/test_kg_build.py
    - _ensure_name 캐싱/폴백 테스트 추가

신규 (0개): 기존 파일 수정만으로 달성
```

---

## 5. 구현 우선순위

```
Phase 1 — 즉시 효과 (KG 빌드 10x 단축):
  [A] _ensure_name() LLM 호출 제거 + 하드코딩 + 규칙 기반 추론
  [B] neo4j_connect_timeout 90 → 10

Phase 2 — UX 개선 (데모 편의성):
  [D] Auto-Flow 1-click 데모 모드
  [E] 프로그레스 바 개선

Phase 3 — 선택적:
  [C] skip_llm 기본값 변경 (기존 동작 깨뜨릴 수 있어 주의)
```

---

## 6. 테스트 검증 항목

```python
# 1. E-commerce 도메인: LLM 호출 없이 빌드 완료
def test_ecommerce_build_no_llm_calls():
    """_ensure_name이 하드코딩 템플릿을 사용하는지 검증."""

# 2. 범용 도메인: _infer_name_template 규칙 우선
def test_generic_infer_name_template():
    """name/title/code 속성이 있으면 LLM 호출 없이 템플릿 생성."""

# 3. 캐시 동작
def test_name_template_cache_hit():
    """두 번째 빌드에서는 캐시 히트로 LLM 호출 스킵."""

# 4. TTV 10초 이내
def test_ttv_under_10_seconds():
    """DDL→generate→approve→build→first_query 전체 파이프라인 10초 이내."""

# 5. Display name 품질 유지
def test_display_name_quality():
    """하드코딩/규칙 추론된 display name이 사람이 읽을 수 있는 형태인지 검증."""
    assert "주문 #1 (delivered)" == template.format_map(order_row)
```

---

## 7. 핵심 원칙

**"데모에서 LLM을 기다리는 시간은 고객이 이탈하는 시간이다."**

- KG 빌드는 **구조 변환**이지 **지능 작업**이 아니다
- Display name 생성은 규칙으로 95% 해결 가능
- LLM은 Wisdom 계층(인사이트/추천)에서만 호출 — 사용자가 기대하는 순간
- 데모의 TTV는 2초를 목표로 하되, 10초 이내를 KPI로 설정
