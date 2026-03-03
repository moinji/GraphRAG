-- ============================================================
-- 회계 시스템 DDL (Accounting Domain)
-- 계정과목, 거래처, 전표, 분개, 예산, 부서
-- ============================================================

CREATE TABLE department (
    id          INT PRIMARY KEY,
    name        VARCHAR(50) NOT NULL,       -- 영업부, 인사부, 개발부 등
    cost_center VARCHAR(20) NOT NULL,       -- 원가 센터 코드
    parent_id   INT REFERENCES department(id)
);

CREATE TABLE employee (
    id            INT PRIMARY KEY,
    name          VARCHAR(50) NOT NULL,
    email         VARCHAR(100),
    position      VARCHAR(30),              -- 사원, 대리, 과장, 부장
    department_id INT NOT NULL REFERENCES department(id)
);

CREATE TABLE account (
    id          INT PRIMARY KEY,
    code        VARCHAR(10) NOT NULL UNIQUE, -- 1101, 2101, 4101 등
    name        VARCHAR(80) NOT NULL,        -- 현금, 매출채권, 매입채무 등
    type        VARCHAR(20) NOT NULL,        -- asset, liability, equity, revenue, expense
    parent_id   INT REFERENCES account(id)
);

CREATE TABLE vendor (
    id              INT PRIMARY KEY,
    name            VARCHAR(100) NOT NULL,
    business_number VARCHAR(20),             -- 사업자등록번호
    category        VARCHAR(30),             -- 원자재, IT서비스, 사무용품 등
    contact_email   VARCHAR(100)
);

CREATE TABLE fiscal_period (
    id         INT PRIMARY KEY,
    year       INT NOT NULL,
    quarter    INT NOT NULL,                 -- 1~4
    month      INT NOT NULL,                 -- 1~12
    start_date DATE NOT NULL,
    end_date   DATE NOT NULL,
    is_closed  BOOLEAN DEFAULT FALSE
);

CREATE TABLE journal_entry (
    id               INT PRIMARY KEY,
    entry_number     VARCHAR(20) NOT NULL UNIQUE,  -- JE-2025-0001
    entry_date       DATE NOT NULL,
    description      VARCHAR(200),
    status           VARCHAR(15) DEFAULT 'draft',  -- draft, posted, reversed
    fiscal_period_id INT NOT NULL REFERENCES fiscal_period(id),
    created_by       INT NOT NULL REFERENCES employee(id),
    approved_by      INT REFERENCES employee(id)
);

CREATE TABLE journal_line (
    id               INT PRIMARY KEY,
    journal_entry_id INT NOT NULL REFERENCES journal_entry(id),
    account_id       INT NOT NULL REFERENCES account(id),
    debit_amount     DECIMAL(15,2) DEFAULT 0,
    credit_amount    DECIMAL(15,2) DEFAULT 0,
    description      VARCHAR(200),
    vendor_id        INT REFERENCES vendor(id),
    department_id    INT REFERENCES department(id)
);

CREATE TABLE invoice (
    id              INT PRIMARY KEY,
    invoice_number  VARCHAR(30) NOT NULL UNIQUE,
    invoice_date    DATE NOT NULL,
    due_date        DATE NOT NULL,
    total_amount    DECIMAL(15,2) NOT NULL,
    paid_amount     DECIMAL(15,2) DEFAULT 0,
    status          VARCHAR(15) DEFAULT 'unpaid', -- unpaid, partial, paid, overdue
    vendor_id       INT NOT NULL REFERENCES vendor(id),
    journal_entry_id INT REFERENCES journal_entry(id)
);

CREATE TABLE payment (
    id             INT PRIMARY KEY,
    payment_date   DATE NOT NULL,
    amount         DECIMAL(15,2) NOT NULL,
    method         VARCHAR(20) NOT NULL,     -- 계좌이체, 카드, 현금, 어음
    reference      VARCHAR(50),              -- 거래 참조번호
    invoice_id     INT NOT NULL REFERENCES invoice(id),
    account_id     INT NOT NULL REFERENCES account(id),  -- 출금 계좌
    processed_by   INT NOT NULL REFERENCES employee(id)
);

CREATE TABLE budget (
    id               INT PRIMARY KEY,
    fiscal_period_id INT NOT NULL REFERENCES fiscal_period(id),
    department_id    INT NOT NULL REFERENCES department(id),
    account_id       INT NOT NULL REFERENCES account(id),
    budget_amount    DECIMAL(15,2) NOT NULL,
    actual_amount    DECIMAL(15,2) DEFAULT 0,
    variance         DECIMAL(15,2) DEFAULT 0
);
