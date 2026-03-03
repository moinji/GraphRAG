"""Sample data generator with FK integrity.

Two modes:
1. E-commerce domain (hardcoded tables detected) → fixed seed data for demo queries.
2. Generic domain → auto-generate sample rows based on ERD schema.
"""

from __future__ import annotations

import random
from collections import defaultdict

from app.models.schemas import ERDSchema, ForeignKey, TableInfo

# ── E-commerce detection ──────────────────────────────────────────

_ECOMMERCE_TABLES = {
    "addresses", "categories", "suppliers", "coupons", "customers",
    "products", "orders", "order_items", "payments", "reviews",
    "wishlists", "shipping",
}


def _is_ecommerce(erd: ERDSchema) -> bool:
    """Check if ERD looks like our e-commerce PoC schema."""
    table_names = {t.name for t in erd.tables}
    # At least 8 of the 12 known tables must be present
    return len(table_names & _ECOMMERCE_TABLES) >= 8


# ── Generic data generator ────────────────────────────────────────

def _topo_sort(tables: list[TableInfo], fks: list[ForeignKey]) -> list[str]:
    """Topological sort of table names based on FK dependencies.

    Tables with no dependencies come first so that FK references are valid.
    """
    table_names = {t.name for t in tables}
    # Build adjacency: fk.source_table depends on fk.target_table
    deps: dict[str, set[str]] = defaultdict(set)
    for fk in fks:
        if fk.source_table in table_names and fk.target_table in table_names:
            # Self-referential FKs don't create ordering constraints
            if fk.source_table != fk.target_table:
                deps[fk.source_table].add(fk.target_table)

    result: list[str] = []
    visited: set[str] = set()
    temp: set[str] = set()

    def visit(name: str) -> None:
        if name in visited:
            return
        if name in temp:
            # Circular dependency — break the cycle
            return
        temp.add(name)
        for dep in deps.get(name, set()):
            visit(dep)
        temp.discard(name)
        visited.add(name)
        result.append(name)

    for t in tables:
        visit(t.name)

    return result


def _map_sql_type(data_type: str) -> str:
    """Classify SQL type into simple category."""
    upper = data_type.upper().split("(")[0].strip()
    if upper in ("SERIAL", "INTEGER", "INT", "BIGINT", "SMALLINT"):
        return "integer"
    if upper in ("DECIMAL", "NUMERIC", "FLOAT", "DOUBLE", "REAL"):
        return "float"
    if upper in ("BOOLEAN", "BOOL"):
        return "boolean"
    if upper in ("DATE",):
        return "date"
    if upper in ("TIMESTAMP", "TIMESTAMPTZ"):
        return "timestamp"
    return "string"


# Sample value pools keyed by column name hints
_NAME_POOLS: dict[str, list] = {
    "name": [
        "항목A", "항목B", "항목C", "항목D", "항목E",
        "항목F", "항목G", "항목H", "항목I", "항목J",
    ],
    "email": [
        "user1@example.com", "user2@example.com", "user3@example.com",
        "user4@example.com", "user5@example.com",
    ],
    "phone": [
        "010-1111-1111", "010-2222-2222", "010-3333-3333",
        "010-4444-4444", "010-5555-5555",
    ],
    "status": ["active", "inactive", "pending", "completed", "draft"],
    "type": ["typeA", "typeB", "typeC", "typeD"],
    "category": ["catA", "catB", "catC", "catD"],
    "method": ["계좌이체", "카드", "현금", "어음"],
    "description": [
        "샘플 설명 1", "샘플 설명 2", "샘플 설명 3",
        "샘플 설명 4", "샘플 설명 5",
    ],
    "comment": [
        "코멘트 A", "코멘트 B", "코멘트 C",
        "코멘트 D", "코멘트 E",
    ],
    "code": ["CODE-001", "CODE-002", "CODE-003", "CODE-004", "CODE-005"],
    "reference": ["REF-001", "REF-002", "REF-003", "REF-004", "REF-005"],
    "position": ["사원", "대리", "과장", "부장", "팀장"],
    "carrier": ["CJ대한통운", "한진택배", "로젠택배"],
    "city": ["서울시", "부산시", "대구시", "인천시", "대전시"],
    "country": ["KR", "US", "JP", "CN", "DE"],
}

_DATE_POOL = [
    "2024-01-15", "2024-02-10", "2024-03-05", "2024-04-20",
    "2024-05-12", "2024-06-01", "2024-07-18", "2024-08-25",
    "2024-09-10", "2024-10-03", "2024-11-22", "2024-12-30",
]

_TIMESTAMP_POOL = [
    "2024-01-15T09:30:00", "2024-02-10T14:20:00", "2024-03-05T11:00:00",
    "2024-04-20T16:45:00", "2024-05-12T08:15:00", "2024-06-01T13:00:00",
]


def _generate_value(col_name: str, col_type: str, row_idx: int) -> object:
    """Generate a sample value for a column based on its name and type."""
    simple = _map_sql_type(col_type)

    # Check name-based pools first
    lower_name = col_name.lower()
    for hint, pool in _NAME_POOLS.items():
        if hint in lower_name:
            return pool[row_idx % len(pool)]

    if simple == "integer":
        return (row_idx + 1) * 10
    if simple == "float":
        return round(random.uniform(100, 10000), 2)
    if simple == "boolean":
        return row_idx % 2 == 0
    if simple == "date":
        return _DATE_POOL[row_idx % len(_DATE_POOL)]
    if simple == "timestamp":
        return _TIMESTAMP_POOL[row_idx % len(_TIMESTAMP_POOL)]

    # Default string
    return f"{col_name}_{row_idx + 1}"


def _generate_generic_data(
    erd: ERDSchema, rows_per_table: int = 5
) -> dict[str, list[dict]]:
    """Generate sample data for any ERD schema.

    - Topologically sorts tables so FK targets are populated first.
    - Self-referential FKs point to earlier rows or None.
    - FK columns reference valid IDs from the target table.
    """
    random.seed(42)  # Reproducible

    table_map = {t.name: t for t in erd.tables}
    # FK lookup: (source_table, source_column) → target_table
    fk_targets: dict[tuple[str, str], str] = {}
    # Track nullable FKs
    fk_nullable: dict[tuple[str, str], bool] = {}
    for fk in erd.foreign_keys:
        fk_targets[(fk.source_table, fk.source_column)] = fk.target_table
        # Check if column is nullable
        table = table_map.get(fk.source_table)
        if table:
            col_info = next(
                (c for c in table.columns if c.name == fk.source_column), None
            )
            fk_nullable[(fk.source_table, fk.source_column)] = (
                col_info.nullable if col_info else True
            )

    sorted_names = _topo_sort(erd.tables, erd.foreign_keys)
    data: dict[str, list[dict]] = {}

    for table_name in sorted_names:
        table = table_map[table_name]
        fk_cols = {
            fk.source_column
            for fk in erd.foreign_keys
            if fk.source_table == table_name
        }

        rows: list[dict] = []
        for i in range(rows_per_table):
            row: dict = {}
            for col in table.columns:
                if col.is_primary_key:
                    row[col.name] = i + 1
                    continue

                if col.name in fk_cols:
                    target_table = fk_targets.get((table_name, col.name))
                    is_self_ref = target_table == table_name
                    is_nullable = fk_nullable.get(
                        (table_name, col.name), True
                    )

                    if is_self_ref:
                        # Self-ref: first 2 rows have None, rest point to earlier
                        if i < 2:
                            row[col.name] = None
                        else:
                            row[col.name] = random.randint(1, i)
                    elif target_table and target_table in data:
                        target_rows = data[target_table]
                        if target_rows:
                            target_ids = [r["id"] for r in target_rows]
                            # Nullable FK: occasionally None
                            if is_nullable and i == rows_per_table - 1:
                                row[col.name] = None
                            else:
                                row[col.name] = random.choice(target_ids)
                        else:
                            row[col.name] = None
                    else:
                        row[col.name] = None
                    continue

                row[col.name] = _generate_value(col.name, col.data_type, i)

            rows.append(row)

        data[table_name] = rows

    return data


# ── E-commerce hardcoded data ─────────────────────────────────────

def _generate_ecommerce_data() -> dict[str, list[dict]]:
    """Return hardcoded e-commerce sample data for demo queries.

    Fixed seed data designed so Q1/Q2/Q3 demo queries produce clean answers:
      Q1: 김민수 → 맥북프로, 에어팟프로, 갤럭시탭
      Q2: Top 3 avg rating in 김민수's categories → 맥북에어(5.0), 에어팟프로(4.67), 아이패드에어(4.5)
      Q3: Top 3 categories by order count → 노트북(6), 오디오(4), 태블릿(2)
    """
    data: dict[str, list[dict]] = {}

    data["addresses"] = [
        {"id": 1, "city": "서울시", "district": "강남구", "street": "테헤란로 123", "zip_code": "06134"},
        {"id": 2, "city": "서울시", "district": "서초구", "street": "반포대로 45", "zip_code": "06501"},
        {"id": 3, "city": "부산시", "district": "해운대구", "street": "해운대로 67", "zip_code": "48094"},
        {"id": 4, "city": "대구시", "district": "수성구", "street": "들안로 89", "zip_code": "42188"},
        {"id": 5, "city": "인천시", "district": "연수구", "street": "센트럴로 101", "zip_code": "21984"},
    ]

    data["categories"] = [
        {"id": 1, "name": "전자기기", "parent_id": None},
        {"id": 2, "name": "의류", "parent_id": None},
        {"id": 3, "name": "식품", "parent_id": None},
        {"id": 4, "name": "노트북", "parent_id": 1},
        {"id": 5, "name": "오디오", "parent_id": 1},
        {"id": 6, "name": "태블릿", "parent_id": 1},
    ]

    data["suppliers"] = [
        {"id": 1, "name": "애플코리아", "contact_email": "biz@apple.co.kr", "country": "KR"},
        {"id": 2, "name": "삼성전자", "contact_email": "biz@samsung.com", "country": "KR"},
        {"id": 3, "name": "LG전자", "contact_email": "biz@lge.com", "country": "KR"},
    ]

    data["coupons"] = [
        {"id": 1, "code": "WELCOME10", "discount_pct": 10.0, "valid_from": "2024-01-01", "valid_until": "2024-12-31"},
        {"id": 2, "code": "VIP20", "discount_pct": 20.0, "valid_from": "2024-01-01", "valid_until": "2024-06-30"},
    ]

    data["customers"] = [
        {"id": 1, "name": "김민수", "email": "minsu@example.com", "phone": "010-1234-5678", "address_id": 1},
        {"id": 2, "name": "이영희", "email": "younghee@example.com", "phone": "010-2345-6789", "address_id": 2},
        {"id": 3, "name": "박지훈", "email": "jihoon@example.com", "phone": "010-3456-7890", "address_id": 3},
        {"id": 4, "name": "최수진", "email": "soojin@example.com", "phone": "010-4567-8901", "address_id": 4},
        {"id": 5, "name": "정대현", "email": "daehyun@example.com", "phone": "010-5678-9012", "address_id": 5},
    ]

    data["products"] = [
        {"id": 1, "name": "맥북프로", "price": 3500000, "stock": 50, "category_id": 4, "supplier_id": 1},
        {"id": 2, "name": "에어팟프로", "price": 359000, "stock": 200, "category_id": 5, "supplier_id": 1},
        {"id": 3, "name": "갤럭시탭", "price": 699000, "stock": 80, "category_id": 6, "supplier_id": 2},
        {"id": 4, "name": "LG그램", "price": 1890000, "stock": 30, "category_id": 4, "supplier_id": 3},
        {"id": 5, "name": "갤럭시버즈", "price": 229000, "stock": 150, "category_id": 5, "supplier_id": 2},
        {"id": 6, "name": "아이패드에어", "price": 929000, "stock": 60, "category_id": 6, "supplier_id": 1},
        {"id": 7, "name": "맥북에어", "price": 1690000, "stock": 45, "category_id": 4, "supplier_id": 1},
        {"id": 8, "name": "소니WH-1000XM5", "price": 459000, "stock": 70, "category_id": 5, "supplier_id": 3},
    ]

    data["orders"] = [
        {"id": 1, "customer_id": 1, "status": "delivered", "total_amount": 3500000, "coupon_id": None, "created_at": "2024-01-15"},
        {"id": 2, "customer_id": 1, "status": "delivered", "total_amount": 323100, "coupon_id": 1, "created_at": "2024-02-20"},
        {"id": 3, "customer_id": 2, "status": "delivered", "total_amount": 2348000, "coupon_id": None, "created_at": "2024-01-20"},
        {"id": 4, "customer_id": 3, "status": "shipped", "total_amount": 3536000, "coupon_id": 2, "created_at": "2024-03-01"},
        {"id": 5, "customer_id": 2, "status": "delivered", "total_amount": 3959000, "coupon_id": None, "created_at": "2024-02-10"},
        {"id": 6, "customer_id": 4, "status": "shipped", "total_amount": 1521000, "coupon_id": 1, "created_at": "2024-03-05"},
        {"id": 7, "customer_id": 5, "status": "delivered", "total_amount": 2608000, "coupon_id": None, "created_at": "2024-01-25"},
        {"id": 8, "customer_id": 1, "status": "delivered", "total_amount": 699000, "coupon_id": None, "created_at": "2024-03-10"},
    ]

    data["order_items"] = [
        {"id": 1, "order_id": 1, "product_id": 1, "quantity": 1, "unit_price": 3500000},
        {"id": 2, "order_id": 2, "product_id": 2, "quantity": 1, "unit_price": 359000},
        {"id": 3, "order_id": 3, "product_id": 4, "quantity": 1, "unit_price": 1890000},
        {"id": 4, "order_id": 3, "product_id": 5, "quantity": 2, "unit_price": 229000},
        {"id": 5, "order_id": 4, "product_id": 6, "quantity": 1, "unit_price": 929000},
        {"id": 6, "order_id": 4, "product_id": 1, "quantity": 1, "unit_price": 3500000},
        {"id": 7, "order_id": 5, "product_id": 1, "quantity": 1, "unit_price": 3500000},
        {"id": 8, "order_id": 5, "product_id": 8, "quantity": 1, "unit_price": 459000},
        {"id": 9, "order_id": 6, "product_id": 7, "quantity": 1, "unit_price": 1690000},
        {"id": 10, "order_id": 7, "product_id": 2, "quantity": 2, "unit_price": 359000},
        {"id": 11, "order_id": 7, "product_id": 4, "quantity": 1, "unit_price": 1890000},
        {"id": 12, "order_id": 8, "product_id": 3, "quantity": 1, "unit_price": 699000},
    ]

    data["payments"] = [
        {"id": 1, "order_id": 1, "method": "credit_card", "amount": 3500000, "status": "completed", "paid_at": "2024-01-15"},
        {"id": 2, "order_id": 2, "method": "credit_card", "amount": 323100, "status": "completed", "paid_at": "2024-02-20"},
        {"id": 3, "order_id": 3, "method": "bank_transfer", "amount": 2348000, "status": "completed", "paid_at": "2024-01-20"},
        {"id": 4, "order_id": 4, "method": "credit_card", "amount": 3536000, "status": "completed", "paid_at": "2024-03-01"},
        {"id": 5, "order_id": 5, "method": "credit_card", "amount": 3959000, "status": "completed", "paid_at": "2024-02-10"},
        {"id": 6, "order_id": 6, "method": "kakaopay", "amount": 1521000, "status": "completed", "paid_at": "2024-03-05"},
        {"id": 7, "order_id": 7, "method": "bank_transfer", "amount": 2608000, "status": "completed", "paid_at": "2024-01-25"},
        {"id": 8, "order_id": 8, "method": "credit_card", "amount": 699000, "status": "completed", "paid_at": "2024-03-10"},
    ]

    data["reviews"] = [
        {"id": 1, "customer_id": 2, "product_id": 7, "rating": 5, "comment": "최고의 가성비 노트북", "created_at": "2024-02-01"},
        {"id": 2, "customer_id": 3, "product_id": 7, "rating": 5, "comment": "가볍고 성능 좋음", "created_at": "2024-02-15"},
        {"id": 3, "customer_id": 5, "product_id": 7, "rating": 5, "comment": "디자인이 예쁨", "created_at": "2024-03-01"},
        {"id": 4, "customer_id": 2, "product_id": 2, "rating": 5, "comment": "음질 최고", "created_at": "2024-02-05"},
        {"id": 5, "customer_id": 3, "product_id": 2, "rating": 5, "comment": "노이즈캔슬링 훌륭", "created_at": "2024-02-20"},
        {"id": 6, "customer_id": 4, "product_id": 2, "rating": 4, "comment": "배터리가 조금 아쉬움", "created_at": "2024-03-05"},
        {"id": 7, "customer_id": 2, "product_id": 6, "rating": 5, "comment": "태블릿 중 최고", "created_at": "2024-02-10"},
        {"id": 8, "customer_id": 4, "product_id": 6, "rating": 4, "comment": "화면이 좋음", "created_at": "2024-03-10"},
        {"id": 9, "customer_id": 2, "product_id": 1, "rating": 4, "comment": "비싸지만 좋음", "created_at": "2024-01-25"},
        {"id": 10, "customer_id": 3, "product_id": 1, "rating": 4, "comment": "개발용으로 적합", "created_at": "2024-02-01"},
        {"id": 11, "customer_id": 4, "product_id": 4, "rating": 4, "comment": "가벼워서 좋음", "created_at": "2024-02-15"},
        {"id": 12, "customer_id": 5, "product_id": 4, "rating": 3, "comment": "보통", "created_at": "2024-03-01"},
        {"id": 13, "customer_id": 3, "product_id": 5, "rating": 3, "comment": "가격 대비 보통", "created_at": "2024-02-20"},
        {"id": 14, "customer_id": 2, "product_id": 8, "rating": 4, "comment": "노이즈캔슬링 최고", "created_at": "2024-02-25"},
        {"id": 15, "customer_id": 4, "product_id": 3, "rating": 4, "comment": "화면이 크고 좋음", "created_at": "2024-03-15"},
    ]

    data["wishlists"] = [
        {"id": 1, "customer_id": 1, "product_id": 4, "added_at": "2024-02-01"},
        {"id": 2, "customer_id": 1, "product_id": 8, "added_at": "2024-02-15"},
        {"id": 3, "customer_id": 2, "product_id": 1, "added_at": "2024-01-20"},
        {"id": 4, "customer_id": 3, "product_id": 6, "added_at": "2024-03-01"},
    ]

    data["shipping"] = [
        {"id": 1, "order_id": 1, "address_id": 1, "carrier": "CJ대한통운", "tracking_number": "CJ123456789", "status": "delivered", "shipped_at": "2024-01-16"},
        {"id": 2, "order_id": 2, "address_id": 1, "carrier": "한진택배", "tracking_number": "HJ987654321", "status": "delivered", "shipped_at": "2024-02-21"},
        {"id": 3, "order_id": 3, "address_id": 2, "carrier": "CJ대한통운", "tracking_number": "CJ234567890", "status": "delivered", "shipped_at": "2024-01-21"},
        {"id": 4, "order_id": 4, "address_id": 3, "carrier": "로젠택배", "tracking_number": "LG345678901", "status": "in_transit", "shipped_at": "2024-03-02"},
        {"id": 5, "order_id": 5, "address_id": 2, "carrier": "CJ대한통운", "tracking_number": "CJ456789012", "status": "delivered", "shipped_at": "2024-02-11"},
        {"id": 6, "order_id": 6, "address_id": 4, "carrier": "한진택배", "tracking_number": "HJ567890123", "status": "in_transit", "shipped_at": "2024-03-06"},
        {"id": 7, "order_id": 7, "address_id": 5, "carrier": "CJ대한통운", "tracking_number": "CJ678901234", "status": "delivered", "shipped_at": "2024-01-26"},
        {"id": 8, "order_id": 8, "address_id": 1, "carrier": "로젠택배", "tracking_number": "LG789012345", "status": "delivered", "shipped_at": "2024-03-11"},
    ]

    return data


# ── Public API ────────────────────────────────────────────────────

def generate_sample_data(erd: ERDSchema) -> dict[str, list[dict]]:
    """Return table_name → list[row_dict].

    E-commerce schema uses fixed demo data.
    Any other schema gets auto-generated sample data.
    """
    if _is_ecommerce(erd):
        return _generate_ecommerce_data()
    return _generate_generic_data(erd)


def verify_fk_integrity(
    data: dict[str, list[dict]], erd: ERDSchema
) -> list[str]:
    """Check all FK references are valid. Returns list of violations."""
    pk_pools: dict[str, set] = {}
    for table_name, rows in data.items():
        pk_pools[table_name] = {row.get("id") for row in rows}

    violations: list[str] = []
    for fk in erd.foreign_keys:
        if fk.source_table not in data:
            continue
        target_ids = pk_pools.get(fk.target_table, set())
        for row in data[fk.source_table]:
            val = row.get(fk.source_column)
            if val is not None and val not in target_ids:
                violations.append(
                    f"{fk.source_table}.{fk.source_column}={val} "
                    f"→ {fk.target_table}.{fk.target_column} NOT FOUND"
                )
    return violations
