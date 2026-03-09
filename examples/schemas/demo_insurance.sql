-- Insurance Management System
-- 12 tables, 12 FKs

CREATE TABLE agents (
    id          INT PRIMARY KEY,
    name        VARCHAR(100) NOT NULL,
    email       VARCHAR(200),
    license_no  VARCHAR(50),
    region      VARCHAR(50)
);

CREATE TABLE policyholders (
    id          INT PRIMARY KEY,
    name        VARCHAR(100) NOT NULL,
    email       VARCHAR(200),
    phone       VARCHAR(30),
    birth_date  DATE,
    address     VARCHAR(300)
);

CREATE TABLE products (
    id              INT PRIMARY KEY,
    name            VARCHAR(100) NOT NULL,
    category        VARCHAR(50),
    base_premium    DECIMAL(12,2),
    description     VARCHAR(500)
);

CREATE TABLE coverages (
    id              INT PRIMARY KEY,
    name            VARCHAR(100) NOT NULL,
    description     VARCHAR(500),
    coverage_type   VARCHAR(50)
);

CREATE TABLE exclusions (
    id              INT PRIMARY KEY,
    name            VARCHAR(100) NOT NULL,
    description     VARCHAR(500)
);

CREATE TABLE policies (
    id                  INT PRIMARY KEY,
    policy_number       VARCHAR(50) NOT NULL,
    policyholder_id     INT NOT NULL REFERENCES policyholders(id),
    product_id          INT NOT NULL REFERENCES products(id),
    agent_id            INT REFERENCES agents(id),
    start_date          DATE,
    end_date            DATE,
    status              VARCHAR(20) DEFAULT 'active',
    total_premium       DECIMAL(12,2)
);

CREATE TABLE policy_coverages (
    id              INT PRIMARY KEY,
    policy_id       INT NOT NULL REFERENCES policies(id),
    coverage_id     INT NOT NULL REFERENCES coverages(id),
    limit_amount    DECIMAL(12,2),
    deductible      DECIMAL(12,2)
);

CREATE TABLE policy_exclusions (
    id              INT PRIMARY KEY,
    policy_id       INT NOT NULL REFERENCES policies(id),
    exclusion_id    INT NOT NULL REFERENCES exclusions(id)
);

CREATE TABLE claims (
    id                  INT PRIMARY KEY,
    claim_number        VARCHAR(50) NOT NULL,
    policy_id           INT NOT NULL REFERENCES policies(id),
    policyholder_id     INT NOT NULL REFERENCES policyholders(id),
    filed_date          DATE,
    incident_date       DATE,
    description         VARCHAR(500),
    status              VARCHAR(20) DEFAULT 'pending',
    claimed_amount      DECIMAL(12,2)
);

CREATE TABLE claim_items (
    id          INT PRIMARY KEY,
    claim_id    INT NOT NULL REFERENCES claims(id),
    item_type   VARCHAR(100),
    amount      DECIMAL(12,2),
    description VARCHAR(300)
);

CREATE TABLE settlements (
    id              INT PRIMARY KEY,
    claim_id        INT NOT NULL REFERENCES claims(id),
    settled_amount  DECIMAL(12,2),
    settled_date    DATE,
    method          VARCHAR(50)
);

CREATE TABLE premiums (
    id          INT PRIMARY KEY,
    policy_id   INT NOT NULL REFERENCES policies(id),
    amount      DECIMAL(12,2),
    due_date    DATE,
    paid_date   DATE,
    status      VARCHAR(20) DEFAULT 'pending'
);
