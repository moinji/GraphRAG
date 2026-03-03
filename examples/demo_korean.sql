-- ========================================
-- 온라인 서점 데이터베이스
-- ========================================

-- 회원 정보
CREATE TABLE 회원 (
    id          INT PRIMARY KEY,
    이름        VARCHAR(50) NOT NULL,
    이메일      VARCHAR(100),
    가입일      DATE
);

-- 책 정보
CREATE TABLE 책 (
    id          INT PRIMARY KEY,
    제목        VARCHAR(200) NOT NULL,
    가격        DECIMAL(10,2),
    출간일      DATE
);

-- 작가 정보
CREATE TABLE 작가 (
    id          INT PRIMARY KEY,
    이름        VARCHAR(50) NOT NULL,
    국적        VARCHAR(50)
);

-- 장르 (소설, 에세이, 자기계발 등)
CREATE TABLE 장르 (
    id          INT PRIMARY KEY,
    이름        VARCHAR(50) NOT NULL
);

-- 주문
CREATE TABLE 주문 (
    id          INT PRIMARY KEY,
    회원_id     INT NOT NULL REFERENCES 회원(id),
    주문일      DATE,
    총금액      DECIMAL(10,2)
);

-- 주문에 포함된 책 (주문 1건에 책 여러 권)
CREATE TABLE 주문상세 (
    id          INT PRIMARY KEY,
    주문_id     INT NOT NULL REFERENCES 주문(id),
    책_id       INT NOT NULL REFERENCES 책(id),
    수량        INT DEFAULT 1
);

-- 책의 리뷰
CREATE TABLE 리뷰 (
    id          INT PRIMARY KEY,
    회원_id     INT NOT NULL REFERENCES 회원(id),
    책_id       INT NOT NULL REFERENCES 책(id),
    별점        INT,
    내용        TEXT
);

-- 책과 작가 연결 (공저 가능)
CREATE TABLE 책_작가 (
    책_id       INT NOT NULL REFERENCES 책(id),
    작가_id     INT NOT NULL REFERENCES 작가(id),
    PRIMARY KEY (책_id, 작가_id)
);

-- 책과 장르 연결 (한 책이 여러 장르)
CREATE TABLE 책_장르 (
    책_id       INT NOT NULL REFERENCES 책(id),
    장르_id     INT NOT NULL REFERENCES 장르(id),
    PRIMARY KEY (책_id, 장르_id)
);
