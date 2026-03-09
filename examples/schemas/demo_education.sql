-- Education / Learning Management System
-- 11 tables, 15 FKs

CREATE TABLE departments (
    id          INT PRIMARY KEY,
    name        VARCHAR(100) NOT NULL,
    building    VARCHAR(50),
    dean_name   VARCHAR(100)
);

CREATE TABLE instructors (
    id              INT PRIMARY KEY,
    name            VARCHAR(100) NOT NULL,
    email           VARCHAR(200),
    department_id   INT REFERENCES departments(id),
    title           VARCHAR(50),
    hire_date       DATE
);

CREATE TABLE semesters (
    id          INT PRIMARY KEY,
    name        VARCHAR(50) NOT NULL,
    start_date  DATE,
    end_date    DATE
);

CREATE TABLE classrooms (
    id          INT PRIMARY KEY,
    building    VARCHAR(50) NOT NULL,
    room_number VARCHAR(20) NOT NULL,
    capacity    INT
);

CREATE TABLE courses (
    id              INT PRIMARY KEY,
    code            VARCHAR(20) NOT NULL,
    title           VARCHAR(200) NOT NULL,
    credits         INT DEFAULT 3,
    department_id   INT REFERENCES departments(id),
    instructor_id   INT REFERENCES instructors(id),
    semester_id     INT REFERENCES semesters(id),
    classroom_id    INT REFERENCES classrooms(id),
    max_enrollment  INT DEFAULT 40
);

CREATE TABLE students (
    id              INT PRIMARY KEY,
    name            VARCHAR(100) NOT NULL,
    email           VARCHAR(200),
    department_id   INT REFERENCES departments(id),
    year            INT DEFAULT 1,
    gpa             DECIMAL(3,2)
);

CREATE TABLE enrollments (
    id              INT PRIMARY KEY,
    student_id      INT NOT NULL REFERENCES students(id),
    course_id       INT NOT NULL REFERENCES courses(id),
    grade           VARCHAR(5),
    enrollment_date DATE,
    status          VARCHAR(20) DEFAULT 'active'
);

CREATE TABLE assignments (
    id          INT PRIMARY KEY,
    course_id   INT NOT NULL REFERENCES courses(id),
    title       VARCHAR(200) NOT NULL,
    due_date    DATE,
    max_score   INT DEFAULT 100,
    weight      DECIMAL(3,2) DEFAULT 0.10
);

CREATE TABLE grades (
    id              INT PRIMARY KEY,
    student_id      INT NOT NULL REFERENCES students(id),
    assignment_id   INT NOT NULL REFERENCES assignments(id),
    score           DECIMAL(5,2),
    submitted_at    TIMESTAMP
);

CREATE TABLE prerequisites (
    id              INT PRIMARY KEY,
    course_id       INT NOT NULL REFERENCES courses(id),
    prerequisite_id INT NOT NULL REFERENCES courses(id)
);

CREATE TABLE certificates (
    id          INT PRIMARY KEY,
    student_id  INT NOT NULL REFERENCES students(id),
    course_id   INT NOT NULL REFERENCES courses(id),
    issued_date DATE,
    cert_type   VARCHAR(50) DEFAULT 'completion'
);
