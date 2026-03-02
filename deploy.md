# GraphRAG GCP 배포 가이드

## 아키텍처
```
GCP Compute Engine VM (e2-medium, 2vCPU/4GB)
├── Docker Compose
│   ├── frontend  (Nginx,     port 80)
│   ├── backend   (FastAPI,   port 8000)
│   ├── neo4j     (Graph DB,  port 7474/7687)
│   ├── postgres  (Metadata,  port 5432)
│   └── redis     (Cache,     port 6379)
```

---

## 1. GCP 계정 및 프로젝트 설정

1. [Google Cloud Console](https://console.cloud.google.com/) 접속
2. 계정 생성 (신규 사용자는 $300 무료 크레딧 제공)
3. 새 프로젝트 생성: `graphrag-deploy`

---

## 2. Compute Engine VM 생성

### Google Cloud Console에서 생성
1. **Compute Engine** > **VM instances** > **CREATE INSTANCE**
2. 설정:
   - **이름:** `graphrag-vm`
   - **리전:** `asia-northeast3` (서울) 또는 가까운 리전
   - **머신 유형:** `e2-medium` (2 vCPU, 4GB RAM)
   - **부팅 디스크:** Ubuntu 22.04 LTS, 30GB SSD
   - **방화벽:** "HTTP 트래픽 허용" 체크
3. **만들기** 클릭

### 또는 gcloud CLI로 생성
```bash
gcloud compute instances create graphrag-vm \
  --zone=asia-northeast3-a \
  --machine-type=e2-medium \
  --image-family=ubuntu-2204-lts \
  --image-project=ubuntu-os-cloud \
  --boot-disk-size=30GB \
  --tags=http-server
```

---

## 3. 방화벽 규칙 설정

HTTP(80) 포트는 VM 생성 시 체크했으면 자동 설정됨. 추가 포트가 필요하면:

```bash
# HTTP 80 (이미 설정된 경우 불필요)
gcloud compute firewall-rules create allow-http \
  --allow=tcp:80 \
  --target-tags=http-server

# HTTPS 443 (SSL 사용 시)
gcloud compute firewall-rules create allow-https \
  --allow=tcp:443 \
  --target-tags=http-server
```

---

## 4. VM 접속 및 환경 설정

### SSH 접속
```bash
gcloud compute ssh graphrag-vm --zone=asia-northeast3-a
```
또는 Console에서 "SSH" 버튼 클릭

### Docker 설치
```bash
# Docker 설치
sudo apt-get update
sudo apt-get install -y ca-certificates curl gnupg

sudo install -m 0755 -d /etc/apt/keyrings
curl -fsSL https://download.docker.com/linux/ubuntu/gpg | sudo gpg --dearmor -o /etc/apt/keyrings/docker.gpg
sudo chmod a+r /etc/apt/keyrings/docker.gpg

echo "deb [arch=$(dpkg --print-architecture) signed-by=/etc/apt/keyrings/docker.gpg] https://download.docker.com/linux/ubuntu $(. /etc/os-release && echo $VERSION_CODENAME) stable" | sudo tee /etc/apt/sources.list.d/docker.list > /dev/null

sudo apt-get update
sudo apt-get install -y docker-ce docker-ce-cli containerd.io docker-compose-plugin

# 현재 사용자를 docker 그룹에 추가 (재로그인 필요)
sudo usermod -aG docker $USER
newgrp docker
```

### Docker 설치 확인
```bash
docker --version
docker compose version
```

---

## 5. 프로젝트 업로드

### 방법 A: Git 사용 (권장)
```bash
# VM에서 실행
git clone <your-repo-url> GraphRAG
cd GraphRAG
```

### 방법 B: gcloud SCP 사용
```bash
# 로컬에서 실행
gcloud compute scp --recurse ./GraphRAG graphrag-vm:~/GraphRAG \
  --zone=asia-northeast3-a
```

### 방법 C: Cloud Shell 파일 업로드
1. Console에서 Cloud Shell 열기
2. 파일 업로드 후 VM으로 SCP

---

## 6. 환경 변수 설정

```bash
cd ~/GraphRAG

# .env 파일 확인 및 수정
nano .env
```

`.env` 파일에서 확인할 사항:
- `ANTHROPIC_API_KEY`: Anthropic API 키 입력 (없으면 LLM 기능 제한)
- DB 호스트가 컨테이너 이름으로 설정되어 있는지 확인 (`neo4j`, `postgres`, `redis`)

---

## 7. 배포 실행

```bash
cd ~/GraphRAG

# 빌드 및 실행
docker compose up --build -d

# 로그 확인
docker compose logs -f

# 개별 서비스 로그
docker compose logs -f backend
docker compose logs -f frontend
```

---

## 8. 배포 확인

### VM 외부 IP 확인
```bash
# GCP Console에서 확인하거나:
curl -s http://metadata.google.internal/computeMetadata/v1/instance/network-interfaces/0/access-configs/0/external-ip -H "Metadata-Flavor: Google"
```

### 접속 테스트
- **프론트엔드:** `http://<VM_EXTERNAL_IP>`
- **API 헬스체크:** `http://<VM_EXTERNAL_IP>/api/v1/health`
- **Neo4j Browser:** `http://<VM_EXTERNAL_IP>:7474` (필요 시 방화벽 규칙 추가)

---

## 9. 유용한 명령어

```bash
# 서비스 상태 확인
docker compose ps

# 서비스 재시작
docker compose restart backend

# 전체 중지
docker compose down

# 전체 중지 + 볼륨 삭제 (데이터 초기화)
docker compose down -v

# 재빌드 후 실행
docker compose up --build -d
```

---

## 10. 트러블슈팅

### 포트 80 접속 안 됨
- GCP 방화벽 규칙에 HTTP(80) 허용 확인
- `docker compose ps`로 frontend 컨테이너 상태 확인

### Backend 시작 실패
```bash
docker compose logs backend
```
- DB 연결 오류: `docker compose ps`로 neo4j/postgres/redis healthy 상태 확인
- depends_on으로 DB 준비 후 backend 시작되도록 설정됨

### 메모리 부족
- e2-medium (4GB)에서 모든 서비스 실행 시 메모리 부족할 수 있음
- `docker stats`로 메모리 사용량 확인
- 필요 시 e2-standard-2 (8GB)로 업그레이드

### Neo4j 연결 오류
- `.env`의 `NEO4J_URI`가 `bolt://neo4j:7687`인지 확인
- `docker compose logs neo4j`로 Neo4j 시작 완료 확인
