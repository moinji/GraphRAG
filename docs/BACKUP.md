# GraphRAG 백업 & 복구 가이드

## PostgreSQL

### 백업
```bash
# 전체 덤프
docker exec graphrag-postgres pg_dump -U graphrag graphrag_meta > backup_pg_$(date +%Y%m%d).sql

# 테이블별 (ontology_versions만)
docker exec graphrag-postgres pg_dump -U graphrag -t ontology_versions graphrag_meta > backup_versions.sql
```

### 복구
```bash
# 복구 전 기존 DB 드롭/재생성
docker exec graphrag-postgres psql -U graphrag -c "DROP DATABASE IF EXISTS graphrag_meta;"
docker exec graphrag-postgres psql -U graphrag -c "CREATE DATABASE graphrag_meta;"

# 덤프 복원
cat backup_pg_20260312.sql | docker exec -i graphrag-postgres psql -U graphrag graphrag_meta
```

## Neo4j

### 백업
```bash
# 온라인 백업 (Community Edition: 서비스 중지 필요)
docker stop graphrag-neo4j
docker run --rm \
  -v graphrag_neo4j_data:/data \
  -v $(pwd)/backups:/backups \
  neo4j:5-community \
  neo4j-admin database dump neo4j --to-path=/backups
docker start graphrag-neo4j
```

### 복구
```bash
docker stop graphrag-neo4j
docker run --rm \
  -v graphrag_neo4j_data:/data \
  -v $(pwd)/backups:/backups \
  neo4j:5-community \
  neo4j-admin database load neo4j --from-path=/backups --overwrite-destination
docker start graphrag-neo4j
```

## Docker Volume 백업 (범용)

```bash
# 볼륨 → tar
docker run --rm -v graphrag_postgres_data:/data -v $(pwd):/backup alpine \
  tar czf /backup/postgres_data.tar.gz -C /data .

# tar → 볼륨 복원
docker run --rm -v graphrag_postgres_data:/data -v $(pwd):/backup alpine \
  sh -c "cd /data && tar xzf /backup/postgres_data.tar.gz"
```

## 권장 백업 주기

| 대상 | 주기 | 보관 기간 |
|------|------|----------|
| PostgreSQL (메타/벡터) | 일 1회 | 7일 |
| Neo4j (KG) | KG 빌드 성공 후 | 최근 3회 |
| Docker volumes | 주 1회 | 4주 |
