-- ============================================================
-- HR 인사관리 시스템 DDL (Human Resources Domain)
-- 부서, 직원, 프로젝트, 스킬, 출결, 평가
-- ============================================================

CREATE TABLE department (
    id          INT PRIMARY KEY,
    name        VARCHAR(50) NOT NULL,
    location    VARCHAR(100),
    parent_id   INT REFERENCES department(id)
);

CREATE TABLE employee (
    id            INT PRIMARY KEY,
    name          VARCHAR(50) NOT NULL,
    email         VARCHAR(100) NOT NULL UNIQUE,
    phone         VARCHAR(20),
    position      VARCHAR(30) NOT NULL,
    hire_date     DATE NOT NULL,
    salary        DECIMAL(12,2),
    department_id INT NOT NULL REFERENCES department(id),
    manager_id    INT REFERENCES employee(id)
);

CREATE TABLE skill (
    id    INT PRIMARY KEY,
    name  VARCHAR(50) NOT NULL,
    level VARCHAR(20) NOT NULL
);

CREATE TABLE employee_skill (
    id          INT PRIMARY KEY,
    employee_id INT NOT NULL REFERENCES employee(id),
    skill_id    INT NOT NULL REFERENCES skill(id),
    proficiency VARCHAR(20) DEFAULT 'intermediate'
);

CREATE TABLE project (
    id          INT PRIMARY KEY,
    name        VARCHAR(100) NOT NULL,
    status      VARCHAR(20) NOT NULL DEFAULT 'active',
    start_date  DATE NOT NULL,
    end_date    DATE,
    budget      DECIMAL(15,2),
    department_id INT NOT NULL REFERENCES department(id)
);

CREATE TABLE project_member (
    id          INT PRIMARY KEY,
    project_id  INT NOT NULL REFERENCES project(id),
    employee_id INT NOT NULL REFERENCES employee(id),
    role        VARCHAR(30) DEFAULT 'member'
);

CREATE TABLE attendance (
    id          INT PRIMARY KEY,
    employee_id INT NOT NULL REFERENCES employee(id),
    date        DATE NOT NULL,
    check_in    TIME,
    check_out   TIME,
    status      VARCHAR(20) NOT NULL DEFAULT 'present'
);

CREATE TABLE leave_request (
    id          INT PRIMARY KEY,
    employee_id INT NOT NULL REFERENCES employee(id),
    leave_type  VARCHAR(30) NOT NULL,
    start_date  DATE NOT NULL,
    end_date    DATE NOT NULL,
    status      VARCHAR(20) DEFAULT 'pending',
    approved_by INT REFERENCES employee(id)
);

CREATE TABLE performance_review (
    id          INT PRIMARY KEY,
    employee_id INT NOT NULL REFERENCES employee(id),
    reviewer_id INT NOT NULL REFERENCES employee(id),
    period      VARCHAR(20) NOT NULL,
    score       DECIMAL(3,1) NOT NULL,
    comments    TEXT,
    created_at  TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE training (
    id          INT PRIMARY KEY,
    name        VARCHAR(100) NOT NULL,
    category    VARCHAR(50),
    duration_hours INT,
    skill_id    INT REFERENCES skill(id)
);

CREATE TABLE training_enrollment (
    id           INT PRIMARY KEY,
    training_id  INT NOT NULL REFERENCES training(id),
    employee_id  INT NOT NULL REFERENCES employee(id),
    enrolled_at  TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    completed    BOOLEAN DEFAULT FALSE,
    score        DECIMAL(5,2)
);
