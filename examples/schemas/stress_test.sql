-- ========================================
-- 종합대학교 관리 시스템 (30 테이블)
-- 스트레스 테스트용 대규모 스키마
-- ========================================

-- ──────────── 조직 ────────────

CREATE TABLE 단과대학 (
    id          INT PRIMARY KEY,
    이름        VARCHAR(100) NOT NULL,
    설립년도    INT
);

CREATE TABLE 학과 (
    id          INT PRIMARY KEY,
    이름        VARCHAR(100) NOT NULL,
    단과대학_id INT NOT NULL REFERENCES 단과대학(id),
    정원        INT
);

-- ──────────── 사람 ────────────

CREATE TABLE 교수 (
    id          INT PRIMARY KEY,
    이름        VARCHAR(50) NOT NULL,
    이메일      VARCHAR(100),
    학과_id     INT NOT NULL REFERENCES 학과(id),
    직급        VARCHAR(30),
    입사일      DATE
);

CREATE TABLE 학생 (
    id          INT PRIMARY KEY,
    이름        VARCHAR(50) NOT NULL,
    학번        VARCHAR(20) NOT NULL,
    이메일      VARCHAR(100),
    학과_id     INT NOT NULL REFERENCES 학과(id),
    학년        INT,
    입학일      DATE
);

CREATE TABLE 교직원 (
    id          INT PRIMARY KEY,
    이름        VARCHAR(50) NOT NULL,
    부서        VARCHAR(50),
    학과_id     INT REFERENCES 학과(id),
    직책        VARCHAR(30)
);

-- ──────────── 수업 ────────────

CREATE TABLE 강의 (
    id          INT PRIMARY KEY,
    과목명      VARCHAR(100) NOT NULL,
    학점        INT,
    학과_id     INT NOT NULL REFERENCES 학과(id),
    교수_id     INT NOT NULL REFERENCES 교수(id),
    학기        VARCHAR(20)
);

CREATE TABLE 수강 (
    id          INT PRIMARY KEY,
    학생_id     INT NOT NULL REFERENCES 학생(id),
    강의_id     INT NOT NULL REFERENCES 강의(id),
    중간성적    DECIMAL(5,2),
    기말성적    DECIMAL(5,2),
    학점결과    VARCHAR(5)
);

CREATE TABLE 선수과목 (
    id          INT PRIMARY KEY,
    강의_id     INT NOT NULL REFERENCES 강의(id),
    선수강의_id INT NOT NULL REFERENCES 강의(id)
);

-- ──────────── 시설 ────────────

CREATE TABLE 건물 (
    id          INT PRIMARY KEY,
    이름        VARCHAR(100) NOT NULL,
    층수        INT,
    준공년도    INT
);

CREATE TABLE 강의실 (
    id          INT PRIMARY KEY,
    호실        VARCHAR(20) NOT NULL,
    건물_id     INT NOT NULL REFERENCES 건물(id),
    수용인원    INT
);

CREATE TABLE 시간표 (
    id          INT PRIMARY KEY,
    강의_id     INT NOT NULL REFERENCES 강의(id),
    강의실_id   INT NOT NULL REFERENCES 강의실(id),
    요일        VARCHAR(10),
    시작시간    VARCHAR(10),
    종료시간    VARCHAR(10)
);

-- ──────────── 도서관 ────────────

CREATE TABLE 도서관 (
    id          INT PRIMARY KEY,
    이름        VARCHAR(100) NOT NULL,
    건물_id     INT NOT NULL REFERENCES 건물(id),
    좌석수      INT
);

CREATE TABLE 도서 (
    id          INT PRIMARY KEY,
    제목        VARCHAR(200) NOT NULL,
    저자        VARCHAR(100),
    출판사      VARCHAR(100),
    ISBN        VARCHAR(20),
    도서관_id   INT NOT NULL REFERENCES 도서관(id)
);

CREATE TABLE 대출 (
    id          INT PRIMARY KEY,
    학생_id     INT NOT NULL REFERENCES 학생(id),
    도서_id     INT NOT NULL REFERENCES 도서(id),
    대출일      DATE,
    반납일      DATE
);

-- ──────────── 동아리 ────────────

CREATE TABLE 동아리 (
    id          INT PRIMARY KEY,
    이름        VARCHAR(100) NOT NULL,
    분류        VARCHAR(50),
    설립년도    INT
);

CREATE TABLE 동아리_회원 (
    id          INT PRIMARY KEY,
    학생_id     INT NOT NULL REFERENCES 학생(id),
    동아리_id   INT NOT NULL REFERENCES 동아리(id),
    역할        VARCHAR(30),
    가입일      DATE
);

-- ──────────── 장학금 ────────────

CREATE TABLE 장학금 (
    id          INT PRIMARY KEY,
    이름        VARCHAR(100) NOT NULL,
    금액        DECIMAL(12,2),
    유형        VARCHAR(30)
);

CREATE TABLE 장학금_수혜 (
    id          INT PRIMARY KEY,
    학생_id     INT NOT NULL REFERENCES 학생(id),
    장학금_id   INT NOT NULL REFERENCES 장학금(id),
    수혜학기    VARCHAR(20),
    수혜금액    DECIMAL(12,2)
);

-- ──────────── 연구 ────────────

CREATE TABLE 연구실 (
    id          INT PRIMARY KEY,
    이름        VARCHAR(100) NOT NULL,
    교수_id     INT NOT NULL REFERENCES 교수(id),
    건물_id     INT NOT NULL REFERENCES 건물(id),
    호실        VARCHAR(20)
);

CREATE TABLE 연구프로젝트 (
    id          INT PRIMARY KEY,
    제목        VARCHAR(200) NOT NULL,
    교수_id     INT NOT NULL REFERENCES 교수(id),
    예산        DECIMAL(15,2),
    시작일      DATE,
    종료일      DATE
);

CREATE TABLE 프로젝트_참여 (
    id          INT PRIMARY KEY,
    학생_id     INT NOT NULL REFERENCES 학생(id),
    프로젝트_id INT NOT NULL REFERENCES 연구프로젝트(id),
    역할        VARCHAR(30)
);

-- ──────────── 생활 ────────────

CREATE TABLE 기숙사 (
    id          INT PRIMARY KEY,
    이름        VARCHAR(100) NOT NULL,
    건물_id     INT NOT NULL REFERENCES 건물(id),
    정원        INT
);

CREATE TABLE 기숙사_배정 (
    id          INT PRIMARY KEY,
    학생_id     INT NOT NULL REFERENCES 학생(id),
    기숙사_id   INT NOT NULL REFERENCES 기숙사(id),
    호실        VARCHAR(20),
    학기        VARCHAR(20)
);

CREATE TABLE 식당 (
    id          INT PRIMARY KEY,
    이름        VARCHAR(100) NOT NULL,
    건물_id     INT NOT NULL REFERENCES 건물(id),
    영업시간    VARCHAR(50)
);

CREATE TABLE 메뉴 (
    id          INT PRIMARY KEY,
    식당_id     INT NOT NULL REFERENCES 식당(id),
    이름        VARCHAR(100) NOT NULL,
    가격        DECIMAL(8,2),
    날짜        DATE
);

-- ──────────── 상담/인턴 ────────────

CREATE TABLE 상담 (
    id          INT PRIMARY KEY,
    학생_id     INT NOT NULL REFERENCES 학생(id),
    교수_id     INT NOT NULL REFERENCES 교수(id),
    상담일      DATE,
    내용        TEXT
);

CREATE TABLE 인턴십 (
    id          INT PRIMARY KEY,
    회사명      VARCHAR(100) NOT NULL,
    부서        VARCHAR(50),
    기간_주     INT
);

CREATE TABLE 인턴십_참여 (
    id          INT PRIMARY KEY,
    학생_id     INT NOT NULL REFERENCES 학생(id),
    인턴십_id   INT NOT NULL REFERENCES 인턴십(id),
    시작일      DATE,
    평가        VARCHAR(10)
);

-- ──────────── 학사 ────────────

CREATE TABLE 학위논문 (
    id          INT PRIMARY KEY,
    학생_id     INT NOT NULL REFERENCES 학생(id),
    지도교수_id INT NOT NULL REFERENCES 교수(id),
    제목        VARCHAR(300) NOT NULL,
    제출일      DATE,
    결과        VARCHAR(20)
);

CREATE TABLE 공지사항 (
    id          INT PRIMARY KEY,
    학과_id     INT REFERENCES 학과(id),
    제목        VARCHAR(200) NOT NULL,
    내용        TEXT,
    작성일      DATE
);

CREATE TABLE 학사일정 (
    id          INT PRIMARY KEY,
    이름        VARCHAR(100) NOT NULL,
    시작일      DATE,
    종료일      DATE,
    유형        VARCHAR(30)
);
