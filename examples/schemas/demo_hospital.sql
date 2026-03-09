-- ============================================================
-- 병원 진료 시스템 DDL (Hospital/Medical Domain)
-- 환자, 의사, 진료과, 진료, 처방, 검사
-- ============================================================

CREATE TABLE department (
    id       INT PRIMARY KEY,
    name     VARCHAR(50) NOT NULL,
    floor    INT,
    phone    VARCHAR(20)
);

CREATE TABLE doctor (
    id            INT PRIMARY KEY,
    name          VARCHAR(50) NOT NULL,
    license_no    VARCHAR(30) NOT NULL UNIQUE,
    specialty     VARCHAR(50) NOT NULL,
    department_id INT NOT NULL REFERENCES department(id)
);

CREATE TABLE patient (
    id            INT PRIMARY KEY,
    name          VARCHAR(50) NOT NULL,
    birth_date    DATE NOT NULL,
    gender        VARCHAR(10),
    phone         VARCHAR(20),
    blood_type    VARCHAR(5),
    insurance_no  VARCHAR(30)
);

CREATE TABLE appointment (
    id          INT PRIMARY KEY,
    patient_id  INT NOT NULL REFERENCES patient(id),
    doctor_id   INT NOT NULL REFERENCES doctor(id),
    date        DATE NOT NULL,
    time        TIME NOT NULL,
    status      VARCHAR(20) DEFAULT 'scheduled',
    notes       TEXT
);

CREATE TABLE diagnosis (
    id             INT PRIMARY KEY,
    appointment_id INT NOT NULL REFERENCES appointment(id),
    icd_code       VARCHAR(10) NOT NULL,
    description    VARCHAR(200) NOT NULL,
    severity       VARCHAR(20) DEFAULT 'moderate'
);

CREATE TABLE medication (
    id          INT PRIMARY KEY,
    name        VARCHAR(100) NOT NULL,
    category    VARCHAR(50),
    unit        VARCHAR(20),
    unit_price  DECIMAL(10,2)
);

CREATE TABLE prescription (
    id             INT PRIMARY KEY,
    appointment_id INT NOT NULL REFERENCES appointment(id),
    medication_id  INT NOT NULL REFERENCES medication(id),
    dosage         VARCHAR(50) NOT NULL,
    frequency      VARCHAR(50) NOT NULL,
    duration_days  INT NOT NULL,
    notes          TEXT
);

CREATE TABLE lab_test (
    id          INT PRIMARY KEY,
    name        VARCHAR(100) NOT NULL,
    category    VARCHAR(50),
    normal_range VARCHAR(50)
);

CREATE TABLE lab_order (
    id             INT PRIMARY KEY,
    appointment_id INT NOT NULL REFERENCES appointment(id),
    lab_test_id    INT NOT NULL REFERENCES lab_test(id),
    result         VARCHAR(100),
    status         VARCHAR(20) DEFAULT 'pending',
    ordered_at     TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    completed_at   TIMESTAMP
);

CREATE TABLE ward (
    id            INT PRIMARY KEY,
    name          VARCHAR(50) NOT NULL,
    department_id INT NOT NULL REFERENCES department(id),
    capacity      INT NOT NULL,
    floor         INT
);

CREATE TABLE admission (
    id          INT PRIMARY KEY,
    patient_id  INT NOT NULL REFERENCES patient(id),
    ward_id     INT NOT NULL REFERENCES ward(id),
    doctor_id   INT NOT NULL REFERENCES doctor(id),
    admit_date  DATE NOT NULL,
    discharge_date DATE,
    status      VARCHAR(20) DEFAULT 'admitted',
    reason      TEXT
);
