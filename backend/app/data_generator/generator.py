"""Sample data generator with FK integrity.

Fixed seed data designed so Q1/Q2/Q3 demo queries produce clean answers:
  Q1: 김민수 → 맥북프로, 에어팟프로, 갤럭시탭
  Q2: Top 3 avg rating in 김민수's categories → 맥북에어(5.0), 에어팟프로(4.67), 아이패드에어(4.5)
  Q3: Top 3 categories by order count → 노트북(6), 오디오(4), 태블릿(2)
"""

from __future__ import annotations

from app.models.schemas import ERDSchema


def generate_sample_data(erd: ERDSchema) -> dict[str, list[dict]]:
    """Return table_name → list[row_dict] for all 12 tables.

    Dependency order is respected: parent tables first.
    All FK references are valid by construction.
    """
    data: dict[str, list[dict]] = {}

    # ── addresses (no deps) ────────────────────────────────────────
    data["addresses"] = [
        {"id": 1, "city": "서울시", "district": "강남구", "street": "테헤란로 123", "zip_code": "06134"},
        {"id": 2, "city": "서울시", "district": "서초구", "street": "반포대로 45", "zip_code": "06501"},
        {"id": 3, "city": "부산시", "district": "해운대구", "street": "해운대로 67", "zip_code": "48094"},
        {"id": 4, "city": "대구시", "district": "수성구", "street": "들안로 89", "zip_code": "42188"},
        {"id": 5, "city": "인천시", "district": "연수구", "street": "센트럴로 101", "zip_code": "21984"},
    ]

    # ── categories (self-ref: parent_id → categories.id) ───────────
    data["categories"] = [
        {"id": 1, "name": "전자기기", "parent_id": None},
        {"id": 2, "name": "의류", "parent_id": None},
        {"id": 3, "name": "식품", "parent_id": None},
        {"id": 4, "name": "노트북", "parent_id": 1},
        {"id": 5, "name": "오디오", "parent_id": 1},
        {"id": 6, "name": "태블릿", "parent_id": 1},
    ]

    # ── suppliers (no deps) ────────────────────────────────────────
    data["suppliers"] = [
        {"id": 1, "name": "애플코리아", "contact_email": "biz@apple.co.kr", "country": "KR"},
        {"id": 2, "name": "삼성전자", "contact_email": "biz@samsung.com", "country": "KR"},
        {"id": 3, "name": "LG전자", "contact_email": "biz@lge.com", "country": "KR"},
    ]

    # ── coupons (no deps) ──────────────────────────────────────────
    data["coupons"] = [
        {"id": 1, "code": "WELCOME10", "discount_pct": 10.0, "valid_from": "2024-01-01", "valid_until": "2024-12-31"},
        {"id": 2, "code": "VIP20", "discount_pct": 20.0, "valid_from": "2024-01-01", "valid_until": "2024-06-30"},
    ]

    # ── customers (→ addresses) ────────────────────────────────────
    data["customers"] = [
        {"id": 1, "name": "김민수", "email": "minsu@example.com", "phone": "010-1234-5678", "address_id": 1},
        {"id": 2, "name": "이영희", "email": "younghee@example.com", "phone": "010-2345-6789", "address_id": 2},
        {"id": 3, "name": "박지훈", "email": "jihoon@example.com", "phone": "010-3456-7890", "address_id": 3},
        {"id": 4, "name": "최수진", "email": "soojin@example.com", "phone": "010-4567-8901", "address_id": 4},
        {"id": 5, "name": "정대현", "email": "daehyun@example.com", "phone": "010-5678-9012", "address_id": 5},
    ]

    # ── products (→ categories, suppliers) ─────────────────────────
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

    # ── orders (→ customers, coupons) ──────────────────────────────
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

    # ── order_items (→ orders, products) ───────────────────────────
    # 김민수(id=1) orders: 1→맥북프로, 2→에어팟프로, 8→갤럭시탭
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

    # ── payments (→ orders) ────────────────────────────────────────
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

    # ── reviews (→ customers, products) ────────────────────────────
    # Avg ratings (for Q2):
    #   맥북에어(7): 5,5,5 → 5.0
    #   에어팟프로(2): 5,5,4 → 4.67
    #   아이패드에어(6): 5,4 → 4.5
    #   맥북프로(1): 4,4 → 4.0   소니WH(8): 4   갤럭시탭(3): 4
    #   LG그램(4): 4,3 → 3.5     갤럭시버즈(5): 3
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

    # ── wishlists (→ customers, products) ──────────────────────────
    data["wishlists"] = [
        {"id": 1, "customer_id": 1, "product_id": 4, "added_at": "2024-02-01"},
        {"id": 2, "customer_id": 1, "product_id": 8, "added_at": "2024-02-15"},
        {"id": 3, "customer_id": 2, "product_id": 1, "added_at": "2024-01-20"},
        {"id": 4, "customer_id": 3, "product_id": 6, "added_at": "2024-03-01"},
    ]

    # ── shipping (→ orders, addresses) ─────────────────────────────
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


def verify_fk_integrity(
    data: dict[str, list[dict]], erd: ERDSchema
) -> list[str]:
    """Check all FK references are valid. Returns list of violations."""
    pk_pools: dict[str, set] = {}
    for table_name, rows in data.items():
        pk_pools[table_name] = {row["id"] for row in rows}

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
