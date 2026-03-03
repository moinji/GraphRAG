# GraphRAG

DDL 파일 하나를 업로드하면 Knowledge Graph가 자동 생성되고, 자연어로 관계 추론 질문에 근거 경로와 함께 답변하는 B2B SaaS PoC.

## Tech Stack

| Layer | Technology |
|-------|-----------|
| Backend | Python 3.11, FastAPI, SQLGlot, Anthropic Claude |
| Frontend | React 18, TypeScript, Vite, Tailwind CSS, shadcn/ui |
| Graph DB | Neo4j 5 Community |
| Metadata DB | PostgreSQL 16 |
| Cache | Redis 7 |
| Infra | Docker Compose |

## Quick Start

```bash
# 1. 인프라 실행 (Neo4j, PostgreSQL, Redis)
docker compose up -d

# 2. 백엔드
cd backend
pip install -r ../requirements.txt
uvicorn app.main:app --reload --port 8000

# 3. 프론트엔드
cd frontend
npm install
npm run dev
```

`.env.example`을 `.env`로 복사한 뒤 환경 변수를 설정하세요.

## Directory Structure

```
GraphRAG/
├── backend/           # FastAPI 서버 (DDL 파싱, 온톨로지, KG 빌드, Q&A)
├── frontend/          # React SPA (DDL 업로드, 온톨로지 리뷰, Q&A)
├── examples/
│   ├── schemas/       # 데모용 DDL 파일 (ecommerce, accounting)
│   └── data/          # 샘플 CSV 데이터
├── docs/
│   ├── PLAN.md        # PoC 개발 계획서
│   ├── deploy.md      # 배포 가이드
│   ├── reports/       # 주차별 개발 보고서
│   └── demo/          # 데모 스크립트 및 스토리보드
├── docker-compose.yml
└── requirements.txt
```

## Documentation

- [개발 계획서](docs/PLAN.md)
- [배포 가이드](docs/deploy.md)
- [PoC 목표/KPI](docs/POC_DOD_KPI.md)
- [주차별 보고서](docs/reports/)
- [데모 스크립트](docs/demo/)
