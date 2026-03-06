-- 개발자 양성 부트캠프 교육 관리 시스템

CREATE TABLE campuses (
    id SERIAL PRIMARY KEY,
    name VARCHAR(100) NOT NULL,
    city VARCHAR(50) NOT NULL,
    address VARCHAR(200) NOT NULL
);

CREATE TABLE departments (
    id SERIAL PRIMARY KEY,
    name VARCHAR(100) NOT NULL,
    description TEXT
);

CREATE TABLE employees (
    id SERIAL PRIMARY KEY,
    name VARCHAR(100) NOT NULL,
    email VARCHAR(150) NOT NULL,
    phone VARCHAR(20),
    department_id INTEGER NOT NULL REFERENCES departments(id),
    role VARCHAR(50) NOT NULL,
    hire_date DATE NOT NULL
);

CREATE TABLE courses (
    id SERIAL PRIMARY KEY,
    name VARCHAR(200) NOT NULL,
    description TEXT,
    category VARCHAR(50) NOT NULL,
    duration_weeks INTEGER NOT NULL,
    instructor_id INTEGER NOT NULL REFERENCES employees(id),
    campus_id INTEGER NOT NULL REFERENCES campuses(id),
    start_date DATE NOT NULL,
    end_date DATE NOT NULL,
    max_students INTEGER NOT NULL
);

CREATE TABLE students (
    id SERIAL PRIMARY KEY,
    name VARCHAR(100) NOT NULL,
    email VARCHAR(150) NOT NULL,
    phone VARCHAR(20),
    birth_date DATE,
    registered_at DATE NOT NULL
);

CREATE TABLE enrollments (
    id SERIAL PRIMARY KEY,
    student_id INTEGER NOT NULL REFERENCES students(id),
    course_id INTEGER NOT NULL REFERENCES courses(id),
    enrolled_at DATE NOT NULL,
    status VARCHAR(20) NOT NULL
);

CREATE TABLE assignments (
    id SERIAL PRIMARY KEY,
    course_id INTEGER NOT NULL REFERENCES courses(id),
    title VARCHAR(200) NOT NULL,
    due_date DATE NOT NULL,
    max_score INTEGER NOT NULL
);

CREATE TABLE submissions (
    id SERIAL PRIMARY KEY,
    assignment_id INTEGER NOT NULL REFERENCES assignments(id),
    student_id INTEGER NOT NULL REFERENCES students(id),
    submitted_at DATE NOT NULL,
    score INTEGER,
    feedback TEXT
);

CREATE TABLE evaluations (
    id SERIAL PRIMARY KEY,
    student_id INTEGER NOT NULL REFERENCES students(id),
    course_id INTEGER NOT NULL REFERENCES courses(id),
    attendance_rate DECIMAL(5,2) NOT NULL,
    final_grade VARCHAR(5) NOT NULL,
    evaluation_date DATE NOT NULL
);

CREATE TABLE certificates (
    id SERIAL PRIMARY KEY,
    student_id INTEGER NOT NULL REFERENCES students(id),
    course_id INTEGER NOT NULL REFERENCES courses(id),
    issued_at DATE NOT NULL,
    certificate_number VARCHAR(50) NOT NULL
);
