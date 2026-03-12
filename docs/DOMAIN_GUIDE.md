# GraphRAG 새 도메인 추가 가이드

## 개요

새 도메인(예: healthcare)을 추가할 때 수정해야 하는 파일 목록과 절차입니다.

## 체크리스트

### 1. DDL 스키마 작성
- [ ] `examples/schemas/demo_{domain}.sql` — 10~15개 테이블, FK 포함
- 기존 예시: `demo_ecommerce.sql`, `demo_education.sql`, `demo_insurance.sql`

### 2. 도메인 힌트 등록
- [ ] `backend/app/ontology/domain_hints.py`
  - `{DOMAIN}_HINT = DomainHint(...)` 정의
  - `_DOMAIN_REGISTRY` 리스트에 추가
  - `owl_axioms`: 해당 도메인의 OWL axiom 힌트 (선택)

### 3. OWL Axiom 등록
- [ ] `backend/app/owl/axiom_registry.py`
  - `{DOMAIN}_AXIOMS: list[AxiomSpec]` 정의
  - `_AXIOM_REGISTRY` dict에 도메인 키 추가

### 4. 샘플 데이터 생성기
- [ ] `backend/app/data_generator/generator.py`
  - 테이블 세트 감지 함수: `_is_{domain}_domain(tables)`
  - 데이터 생성 함수: `_generate_{domain}_data(erd)`
  - `generate_sample_data()`에서 도메인 분기 추가

### 5. 골든 데이터 (평가용)
- [ ] `backend/app/evaluation/golden_{domain}.py` (신규)
  - `GOLDEN_NODE_NAMES`, `GOLDEN_RELATIONSHIP_SPECS` 정의
- [ ] `backend/app/evaluation/auto_golden.py`
  - `is_{domain}_domain()` 감지 함수 추가

### 6. 테스트
- [ ] `backend/tests/conftest.py` — `{domain}_ddl`, `{domain}_erd` fixture 추가
- [ ] 기존 `test_multi_domain.py`에 도메인 테스트 케이스 추가
- [ ] OWL 추론 테스트 (`test_owl_reasoning.py`에 도메인 케이스 추가)

## 검증 절차

```bash
# 1. 파서 테스트
python -m pytest tests/ -k "{domain}" --tb=short

# 2. 온톨로지 생성 확인
python -c "
from app.ddl_parser.parser import parse_ddl
from app.ontology.fk_rule_engine import build_ontology
erd = parse_ddl(open('examples/schemas/demo_{domain}.sql').read())
ont = build_ontology(erd)
print(f'Nodes: {len(ont.node_types)}, Rels: {len(ont.relationship_types)}')
"

# 3. OWL 추론 확인
python -c "
from app.owl.axiom_registry import get_axioms
axioms = get_axioms('{domain}')
print(f'Axioms: {len(axioms)}')
"

# 4. 전체 테스트
python -m pytest tests/ --tb=short -q
```

## 파일 변경 요약

| 파일 | 변경 유형 | 필수 |
|------|----------|:---:|
| `examples/schemas/demo_{domain}.sql` | 신규 | O |
| `ontology/domain_hints.py` | 수정 | O |
| `owl/axiom_registry.py` | 수정 | O |
| `data_generator/generator.py` | 수정 | O |
| `evaluation/golden_{domain}.py` | 신규 | 권장 |
| `evaluation/auto_golden.py` | 수정 | 권장 |
| `tests/conftest.py` | 수정 | 권장 |
