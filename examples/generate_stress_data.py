"""
종합대학교 스트레스 테스트 데이터 생성기

사용법:
    python generate_stress_data.py              # 기본 (학생 500명)
    python generate_stress_data.py --scale 3    # 3배 (학생 1500명)
    python generate_stress_data.py --scale 10   # 10배 (학생 5000명)

출력: ./stress_csv/ 디렉토리에 테이블별 CSV 파일 생성
"""

import csv
import os
import random
import argparse
from datetime import date, timedelta

random.seed(42)

# ── 이름 풀 ──
LAST_NAMES = ["김", "이", "박", "최", "정", "강", "조", "윤", "장", "임",
              "한", "오", "서", "신", "권", "황", "안", "송", "류", "홍"]
FIRST_NAMES = ["민수", "영희", "지훈", "수진", "현우", "미영", "성호", "은지",
               "태현", "지은", "동현", "서연", "준혁", "하은", "승민", "유진",
               "재원", "소희", "우진", "다은", "시우", "예은", "건우", "채원",
               "도윤", "서윤", "하준", "지유", "은호", "민지"]

COLLEGES = [
    ("공과대학", 1990), ("인문대학", 1985), ("자연과학대학", 1988),
    ("사회과학대학", 1992), ("경영대학", 1995), ("예술대학", 2000),
    ("의과대학", 1980), ("법과대학", 1987), ("교육대학", 1993),
    ("IT대학", 2005),
]

DEPARTMENTS_BY_COLLEGE = {
    "공과대학": ["컴퓨터공학과", "전자공학과", "기계공학과", "화학공학과", "건축공학과", "산업공학과"],
    "인문대학": ["국어국문학과", "영어영문학과", "철학과", "사학과"],
    "자연과학대학": ["수학과", "물리학과", "화학과", "생명과학과"],
    "사회과학대학": ["심리학과", "사회학과", "정치외교학과", "미디어학과"],
    "경영대학": ["경영학과", "회계학과", "국제통상학과"],
    "예술대학": ["음악학과", "미술학과", "디자인학과"],
    "의과대학": ["의학과", "간호학과"],
    "법과대학": ["법학과"],
    "교육대학": ["교육학과", "수학교육과"],
    "IT대학": ["소프트웨어학과", "인공지능학과", "데이터사이언스학과"],
}

RANKS = ["교수", "부교수", "조교수", "겸임교수"]
BUILDINGS_DATA = [
    ("제1공학관", 6, 1992), ("제2공학관", 8, 2005), ("인문관", 5, 1988),
    ("자연과학관", 7, 1990), ("사회과학관", 5, 1994), ("경영관", 6, 1998),
    ("예술관", 4, 2002), ("의학관", 10, 1985), ("법학관", 5, 1989),
    ("IT융합관", 9, 2010), ("중앙도서관", 4, 1986), ("제2도서관", 3, 2015),
    ("학생회관", 3, 1995), ("기숙사A동", 12, 2000), ("기숙사B동", 12, 2000),
    ("기숙사C동", 15, 2010), ("체육관", 2, 1993), ("본관", 4, 1980),
    ("복지관", 3, 1997), ("국제관", 5, 2008),
]

CLUB_NAMES = [
    ("코딩클럽", "학술"), ("영어토론반", "학술"), ("수학연구회", "학술"),
    ("밴드동아리", "예술"), ("연극반", "예술"), ("사진반", "예술"), ("미술반", "예술"),
    ("축구부", "체육"), ("농구부", "체육"), ("테니스부", "체육"), ("배드민턴부", "체육"),
    ("등산반", "체육"), ("봉사단", "봉사"), ("환경동아리", "봉사"),
    ("창업동아리", "기타"), ("여행동아리", "기타"), ("독서모임", "학술"),
    ("요리반", "기타"), ("영화감상반", "예술"), ("로봇공학회", "학술"),
]

SCHOLARSHIP_NAMES = [
    ("성적우수장학금", 2000000, "성적"), ("국가장학금", 3000000, "국가"),
    ("근로장학금", 1500000, "근로"), ("교내봉사장학금", 1000000, "봉사"),
    ("총장장학금", 5000000, "성적"), ("입학성적장학금", 4000000, "성적"),
    ("저소득층장학금", 3500000, "복지"), ("해외연수장학금", 6000000, "해외"),
    ("연구장학금", 2500000, "연구"), ("동문장학금", 2000000, "기타"),
    ("IT특기장학금", 3000000, "특기"), ("예체능장학금", 2500000, "특기"),
]

COMPANIES = [
    ("삼성전자", "반도체"), ("LG전자", "가전"), ("현대자동차", "R&D"),
    ("네이버", "개발"), ("카카오", "플랫폼"), ("SK하이닉스", "메모리"),
    ("쿠팡", "물류기술"), ("배달의민족", "서비스개발"), ("토스", "핀테크"),
    ("라인", "메신저개발"), ("당근마켓", "백엔드"), ("마이크로소프트", "클라우드"),
    ("구글코리아", "AI연구"), ("아마존웹서비스", "인프라"), ("넥슨", "게임개발"),
]

BOOK_TITLES = [
    "데이터구조론", "알고리즘개론", "운영체제", "컴퓨터네트워크", "데이터베이스시스템",
    "선형대수학", "미적분학", "확률과통계", "이산수학", "수치해석",
    "일반물리학", "일반화학", "유기화학", "생명과학개론", "환경과학",
    "경영학원론", "마케팅관리론", "재무관리", "인사조직론", "회계원리",
    "한국현대문학", "영미문학개론", "서양철학사", "동양철학개론", "한국사개설",
    "심리학개론", "사회학개론", "정치학개론", "법학개론", "교육학개론",
    "인공지능", "머신러닝", "딥러닝", "자연어처리", "컴퓨터비전",
    "소프트웨어공학", "웹프로그래밍", "모바일앱개발", "클라우드컴퓨팅", "정보보안",
]

PUBLISHERS = ["한빛미디어", "길벗", "위키북스", "에이콘", "인사이트",
              "교문사", "학지사", "박영사", "법문사", "민음사"]

MENU_ITEMS = [
    "김치찌개", "된장찌개", "부대찌개", "순두부찌개",
    "비빔밥", "김치볶음밥", "제육볶음", "불고기",
    "돈까스", "치킨까스", "생선까스",
    "짜장면", "짬뽕", "탕수육",
    "라면", "칼국수", "우동", "떡볶이",
    "샐러드", "샌드위치", "파스타", "피자",
]

SEMESTERS = ["2024-1", "2024-2", "2025-1", "2025-2"]
DAYS = ["월", "화", "수", "목", "금"]
GRADES = ["A+", "A", "B+", "B", "C+", "C", "D+", "D", "F"]
THESIS_RESULTS = ["합격", "수정후합격", "불합격"]
EVAL_GRADES = ["우수", "양호", "보통"]


def rand_name():
    return random.choice(LAST_NAMES) + random.choice(FIRST_NAMES)

def rand_email(name, domain="univ.ac.kr"):
    return f"{name}_{random.randint(1,999)}@{domain}"

def rand_date(start_year, end_year):
    start = date(start_year, 1, 1)
    end = date(end_year, 12, 31)
    delta = (end - start).days
    return start + timedelta(days=random.randint(0, delta))


def generate(scale=1, output_dir="stress_csv"):
    os.makedirs(output_dir, exist_ok=True)

    # ── 규모 설정 ──
    n_students     = 500 * scale
    n_professors   = 100 * scale
    n_staff        = 50 * scale
    n_courses      = 200 * scale
    n_enrollments  = 2000 * scale
    n_books        = 300 * scale
    n_loans        = 800 * scale
    n_counseling   = 200 * scale
    n_menus        = 500 * scale
    n_dorm_assign  = 300 * scale
    n_scholarships_award = 400 * scale
    n_internship_enroll  = 150 * scale
    n_theses       = 80 * scale
    n_notices      = 100 * scale
    n_projects     = 60 * scale
    n_prereqs      = 80 * scale

    def write_csv(filename, headers, rows):
        path = os.path.join(output_dir, filename)
        with open(path, "w", newline="", encoding="utf-8-sig") as f:
            w = csv.writer(f)
            w.writerow(headers)
            w.writerows(rows)
        print(f"  {filename}: {len(rows)} rows")

    print(f"=== 데이터 생성 (scale={scale}) ===\n")

    # ── 1. 단과대학 ──
    colleges = []
    for i, (name, year) in enumerate(COLLEGES, 1):
        colleges.append((i, name, year))
    write_csv("단과대학.csv", ["id", "이름", "설립년도"], colleges)

    # ── 2. 학과 ──
    departments = []
    dept_id = 1
    dept_college_map = {}
    for col_id, (col_name, _) in enumerate(COLLEGES, 1):
        for dept_name in DEPARTMENTS_BY_COLLEGE[col_name]:
            departments.append((dept_id, dept_name, col_id, random.randint(30, 80)))
            dept_college_map[dept_id] = col_id
            dept_id += 1
    write_csv("학과.csv", ["id", "이름", "단과대학_id", "정원"], departments)
    dept_ids = [d[0] for d in departments]

    # ── 3. 교수 ──
    professors = []
    for i in range(1, n_professors + 1):
        name = rand_name()
        professors.append((
            i, name, rand_email(name, "prof.univ.ac.kr"),
            random.choice(dept_ids), random.choice(RANKS),
            rand_date(2000, 2024)
        ))
    write_csv("교수.csv", ["id", "이름", "이메일", "학과_id", "직급", "입사일"], professors)

    # ── 4. 학생 ──
    students = []
    for i in range(1, n_students + 1):
        name = rand_name()
        year = random.randint(1, 4)
        enter_year = 2025 - year + 1
        students.append((
            i, name, f"{enter_year}{i:05d}",
            rand_email(name, "student.univ.ac.kr"),
            random.choice(dept_ids), year, rand_date(enter_year, enter_year)
        ))
    write_csv("학생.csv", ["id", "이름", "학번", "이메일", "학과_id", "학년", "입학일"], students)

    # ── 5. 교직원 ──
    staff = []
    depts_list = ["교무처", "학생처", "총무처", "기획처", "입학처", "도서관", "전산원", "시설관리"]
    for i in range(1, n_staff + 1):
        name = rand_name()
        staff.append((
            i, name, random.choice(depts_list),
            random.choice(dept_ids) if random.random() > 0.5 else "",
            random.choice(["팀장", "대리", "주임", "사원"])
        ))
    write_csv("교직원.csv", ["id", "이름", "부서", "학과_id", "직책"], staff)

    # ── 6. 건물 ──
    buildings = []
    for i, (name, floors, year) in enumerate(BUILDINGS_DATA, 1):
        buildings.append((i, name, floors, year))
    write_csv("건물.csv", ["id", "이름", "층수", "준공년도"], buildings)
    building_ids = [b[0] for b in buildings]

    # ── 7. 강의실 ──
    classrooms = []
    cr_id = 1
    for b in buildings[:12]:  # 강의용 건물만
        for floor in range(1, b[2] + 1):
            for room in range(1, random.randint(3, 8)):
                classrooms.append((cr_id, f"{floor}{room:02d}호", b[0], random.randint(30, 200)))
                cr_id += 1
    write_csv("강의실.csv", ["id", "호실", "건물_id", "수용인원"], classrooms)
    cr_ids = [c[0] for c in classrooms]

    # ── 8. 강의 ──
    subjects = [
        "프로그래밍기초", "자료구조", "알고리즘", "운영체제", "데이터베이스",
        "컴퓨터네트워크", "소프트웨어공학", "인공지능", "머신러닝", "딥러닝",
        "웹프로그래밍", "모바일프로그래밍", "클라우드컴퓨팅", "정보보안", "컴파일러",
        "선형대수", "미적분학", "확률통계", "이산수학", "수치해석",
        "일반물리", "일반화학", "생명과학", "환경과학", "지구과학",
        "경영학원론", "마케팅", "재무관리", "회계원리", "인사관리",
        "심리학개론", "사회학개론", "정치학개론", "법학개론", "교육학개론",
        "한국문학", "영미문학", "철학개론", "한국사", "세계사",
        "음악이론", "미술개론", "디자인기초", "작곡법", "실기",
    ]
    courses = []
    for i in range(1, n_courses + 1):
        subj = random.choice(subjects)
        semester = random.choice(SEMESTERS)
        courses.append((
            i, f"{subj}({semester})", random.choice([2, 3]),
            random.choice(dept_ids), random.choice(range(1, n_professors + 1)),
            semester
        ))
    write_csv("강의.csv", ["id", "과목명", "학점", "학과_id", "교수_id", "학기"], courses)

    # ── 9. 수강 ──
    enrollments = []
    enroll_set = set()
    for i in range(1, n_enrollments + 1):
        while True:
            s_id = random.randint(1, n_students)
            c_id = random.randint(1, n_courses)
            if (s_id, c_id) not in enroll_set:
                enroll_set.add((s_id, c_id))
                break
        enrollments.append((
            i, s_id, c_id,
            round(random.uniform(0, 100), 1),
            round(random.uniform(0, 100), 1),
            random.choice(GRADES)
        ))
    write_csv("수강.csv", ["id", "학생_id", "강의_id", "중간성적", "기말성적", "학점결과"], enrollments)

    # ── 10. 선수과목 ──
    prereqs = []
    prereq_set = set()
    for _ in range(n_prereqs):
        while True:
            c1 = random.randint(1, n_courses)
            c2 = random.randint(1, n_courses)
            if c1 != c2 and (c1, c2) not in prereq_set:
                prereq_set.add((c1, c2))
                break
        prereqs.append((len(prereqs) + 1, c1, c2))
    write_csv("선수과목.csv", ["id", "강의_id", "선수강의_id"], prereqs)

    # ── 11. 시간표 ──
    schedules = []
    for i in range(1, n_courses + 1):
        n_slots = random.randint(1, 2)
        for _ in range(n_slots):
            hour = random.randint(9, 17)
            schedules.append((
                len(schedules) + 1, i, random.choice(cr_ids),
                random.choice(DAYS), f"{hour:02d}:00", f"{hour+1:02d}:30"
            ))
    write_csv("시간표.csv", ["id", "강의_id", "강의실_id", "요일", "시작시간", "종료시간"], schedules)

    # ── 12. 도서관 ──
    libraries = [
        (1, "중앙도서관", 11, 500),
        (2, "제2도서관", 12, 300),
        (3, "의학도서관", 8, 150),
    ]
    write_csv("도서관.csv", ["id", "이름", "건물_id", "좌석수"], libraries)

    # ── 13. 도서 ──
    books = []
    for i in range(1, n_books + 1):
        books.append((
            i, random.choice(BOOK_TITLES) + f" {random.choice(['제3판','제4판','제5판','개정판',''])}".strip(),
            rand_name(), random.choice(PUBLISHERS),
            f"978-89-{random.randint(1000,9999)}-{random.randint(100,999)}-{random.randint(0,9)}",
            random.choice([1, 2, 3])
        ))
    write_csv("도서.csv", ["id", "제목", "저자", "출판사", "ISBN", "도서관_id"], books)

    # ── 14. 대출 ──
    loans = []
    for i in range(1, n_loans + 1):
        borrow = rand_date(2024, 2025)
        returned = borrow + timedelta(days=random.randint(1, 30)) if random.random() > 0.2 else ""
        loans.append((i, random.randint(1, n_students), random.randint(1, n_books), borrow, returned))
    write_csv("대출.csv", ["id", "학생_id", "도서_id", "대출일", "반납일"], loans)

    # ── 15. 동아리 ──
    clubs = []
    for i, (name, cat) in enumerate(CLUB_NAMES, 1):
        clubs.append((i, name, cat, random.randint(2000, 2020)))
    write_csv("동아리.csv", ["id", "이름", "분류", "설립년도"], clubs)

    # ── 16. 동아리_회원 ──
    club_members = []
    cm_set = set()
    n_cm = min(n_students * 2, len(CLUB_NAMES) * n_students)
    for _ in range(n_cm):
        while True:
            s_id = random.randint(1, n_students)
            c_id = random.randint(1, len(CLUB_NAMES))
            if (s_id, c_id) not in cm_set:
                cm_set.add((s_id, c_id))
                break
        club_members.append((
            len(club_members) + 1, s_id, c_id,
            random.choice(["회원", "부원", "부장", "총무"]),
            rand_date(2022, 2025)
        ))
        if len(club_members) >= 500 * scale:
            break
    write_csv("동아리_회원.csv", ["id", "학생_id", "동아리_id", "역할", "가입일"], club_members)

    # ── 17. 장학금 ──
    scholarships = []
    for i, (name, amount, typ) in enumerate(SCHOLARSHIP_NAMES, 1):
        scholarships.append((i, name, amount, typ))
    write_csv("장학금.csv", ["id", "이름", "금액", "유형"], scholarships)

    # ── 18. 장학금_수혜 ──
    awards = []
    for i in range(1, n_scholarships_award + 1):
        sch = random.choice(scholarships)
        awards.append((
            i, random.randint(1, n_students), sch[0],
            random.choice(SEMESTERS),
            sch[2] * random.uniform(0.5, 1.0)
        ))
    write_csv("장학금_수혜.csv", ["id", "학생_id", "장학금_id", "수혜학기", "수혜금액"], awards)

    # ── 19. 연구실 ──
    labs = []
    for i in range(1, min(n_professors, 40 * scale) + 1):
        b_id = random.choice(building_ids[:12])
        labs.append((i, f"{professors[i-1][1]}연구실", i, b_id, f"{random.randint(1,8)}{random.randint(1,20):02d}"))
    write_csv("연구실.csv", ["id", "이름", "교수_id", "건물_id", "호실"], labs)

    # ── 20. 연구프로젝트 ──
    projects = []
    project_titles = [
        "AI기반 자연어처리 연구", "빅데이터 분석 플랫폼 개발", "IoT 센서 네트워크 최적화",
        "블록체인 보안 프로토콜", "자율주행 알고리즘 연구", "신약 후보물질 탐색",
        "스마트시티 에너지 관리", "로봇 제어 시스템", "양자컴퓨팅 시뮬레이션",
        "기후변화 예측 모델", "유전체 분석 파이프라인", "메타버스 교육 플랫폼",
        "차세대 반도체 설계", "바이오센서 개발", "디지털트윈 시뮬레이션",
    ]
    for i in range(1, n_projects + 1):
        start = rand_date(2023, 2025)
        projects.append((
            i, random.choice(project_titles) + f" ({i}차)",
            random.randint(1, n_professors),
            random.randint(10000000, 500000000),
            start, start + timedelta(days=random.randint(180, 730))
        ))
    write_csv("연구프로젝트.csv", ["id", "제목", "교수_id", "예산", "시작일", "종료일"], projects)

    # ── 21. 프로젝트_참여 ──
    proj_members = []
    pm_set = set()
    for _ in range(n_projects * 5):
        while True:
            s_id = random.randint(1, n_students)
            p_id = random.randint(1, n_projects)
            if (s_id, p_id) not in pm_set:
                pm_set.add((s_id, p_id))
                break
        proj_members.append((len(proj_members) + 1, s_id, p_id, random.choice(["연구원", "인턴", "보조연구원"])))
    write_csv("프로젝트_참여.csv", ["id", "학생_id", "프로젝트_id", "역할"], proj_members)

    # ── 22. 기숙사 ──
    dorms = [
        (1, "행복관", 14, 400), (2, "희망관", 15, 500), (3, "진리관", 16, 300),
    ]
    write_csv("기숙사.csv", ["id", "이름", "건물_id", "정원"], dorms)

    # ── 23. 기숙사_배정 ──
    dorm_assigns = []
    for i in range(1, n_dorm_assign + 1):
        dorm_assigns.append((
            i, random.randint(1, n_students), random.choice([1, 2, 3]),
            f"{random.randint(2,12)}{random.randint(1,20):02d}호",
            random.choice(SEMESTERS)
        ))
    write_csv("기숙사_배정.csv", ["id", "학생_id", "기숙사_id", "호실", "학기"], dorm_assigns)

    # ── 24. 식당 ──
    cafeterias = [
        (1, "학생식당", 13, "07:30-19:00"),
        (2, "교직원식당", 18, "11:00-14:00"),
        (3, "기숙사식당", 14, "07:00-20:00"),
        (4, "카페테리아", 13, "09:00-21:00"),
    ]
    write_csv("식당.csv", ["id", "이름", "건물_id", "영업시간"], cafeterias)

    # ── 25. 메뉴 ──
    menus = []
    for i in range(1, n_menus + 1):
        menus.append((
            i, random.choice([1, 2, 3, 4]),
            random.choice(MENU_ITEMS),
            random.choice([3500, 4000, 4500, 5000, 5500, 6000, 6500]),
            rand_date(2025, 2025)
        ))
    write_csv("메뉴.csv", ["id", "식당_id", "이름", "가격", "날짜"], menus)

    # ── 26. 상담 ──
    counseling = []
    for i in range(1, n_counseling + 1):
        topics = ["진로상담", "학업상담", "생활상담", "대학원진학", "취업상담", "휴학상담"]
        counseling.append((
            i, random.randint(1, n_students), random.randint(1, n_professors),
            rand_date(2024, 2025), random.choice(topics)
        ))
    write_csv("상담.csv", ["id", "학생_id", "교수_id", "상담일", "내용"], counseling)

    # ── 27. 인턴십 ──
    internships = []
    for i, (company, dept) in enumerate(COMPANIES, 1):
        internships.append((i, company, dept, random.choice([4, 8, 12, 24])))
    write_csv("인턴십.csv", ["id", "회사명", "부서", "기간_주"], internships)

    # ── 28. 인턴십_참여 ──
    intern_enrolls = []
    for i in range(1, n_internship_enroll + 1):
        intern_enrolls.append((
            i, random.randint(1, n_students), random.randint(1, len(COMPANIES)),
            rand_date(2024, 2025), random.choice(EVAL_GRADES)
        ))
    write_csv("인턴십_참여.csv", ["id", "학생_id", "인턴십_id", "시작일", "평가"], intern_enrolls)

    # ── 29. 학위논문 ──
    theses = []
    thesis_titles = [
        "딥러닝 기반 한국어 감성 분석", "블록체인 합의 알고리즘 비교 연구",
        "스마트팜 IoT 센서 데이터 분석", "추천 시스템의 공정성 연구",
        "자율주행 환경 인식 모델 개선", "의료 영상 분할 딥러닝 모델",
        "탄소중립을 위한 에너지 최적화", "메타버스 기반 원격 교육 효과",
    ]
    for i in range(1, n_theses + 1):
        theses.append((
            i, random.randint(1, n_students), random.randint(1, n_professors),
            random.choice(thesis_titles) + f" ({i})",
            rand_date(2024, 2025), random.choice(THESIS_RESULTS)
        ))
    write_csv("학위논문.csv", ["id", "학생_id", "지도교수_id", "제목", "제출일", "결과"], theses)

    # ── 30. 공지사항 ──
    notices = []
    notice_titles = [
        "수강신청 안내", "중간고사 일정 공지", "기말고사 일정 공지",
        "장학금 신청 안내", "졸업요건 변경 안내", "동아리 모집 공고",
        "인턴십 프로그램 안내", "학과 MT 안내", "연구실 모집",
        "취업설명회 일정", "교환학생 모집", "학사일정 변경",
    ]
    for i in range(1, n_notices + 1):
        notices.append((
            i, random.choice(dept_ids) if random.random() > 0.3 else "",
            random.choice(notice_titles), f"상세 내용 {i}",
            rand_date(2024, 2025)
        ))
    write_csv("공지사항.csv", ["id", "학과_id", "제목", "내용", "작성일"], notices)

    # ── 31. 학사일정 ──
    calendars = [
        (1, "1학기 개강", "2025-03-03", "2025-03-03", "학기"),
        (2, "1학기 중간고사", "2025-04-21", "2025-04-25", "시험"),
        (3, "1학기 기말고사", "2025-06-16", "2025-06-20", "시험"),
        (4, "여름방학", "2025-06-23", "2025-08-31", "방학"),
        (5, "2학기 개강", "2025-09-01", "2025-09-01", "학기"),
        (6, "2학기 중간고사", "2025-10-20", "2025-10-24", "시험"),
        (7, "2학기 기말고사", "2025-12-15", "2025-12-19", "시험"),
        (8, "겨울방학", "2025-12-22", "2026-02-28", "방학"),
        (9, "수강신청", "2025-02-17", "2025-02-21", "행사"),
        (10, "축제", "2025-05-12", "2025-05-14", "행사"),
    ]
    write_csv("학사일정.csv", ["id", "이름", "시작일", "종료일", "유형"], calendars)

    # ── 집계 ──
    total = sum([
        len(colleges), len(departments), len(professors), len(students), len(staff),
        len(buildings), len(classrooms), len(courses), len(enrollments), len(prereqs),
        len(schedules), len(libraries), len(books), len(loans),
        len(clubs), len(club_members), len(scholarships), len(awards),
        len(labs), len(projects), len(proj_members),
        len(dorms), len(dorm_assigns), len(cafeterias), len(menus),
        len(counseling), len(internships), len(intern_enrolls),
        len(theses), len(notices), len(calendars),
    ])
    print(f"\n=== 완료: {output_dir}/ 에 31개 CSV, 총 {total:,} rows 생성 ===")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="종합대학교 스트레스 테스트 데이터 생성")
    parser.add_argument("--scale", type=int, default=1, help="배율 (1=학생500, 3=1500, 10=5000)")
    parser.add_argument("--output", type=str, default="stress_csv", help="출력 디렉토리")
    args = parser.parse_args()
    generate(scale=args.scale, output_dir=args.output)
