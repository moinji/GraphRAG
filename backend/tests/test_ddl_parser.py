"""DDL parser unit tests — 10 cases."""

from __future__ import annotations

from app.ddl_parser.parser import parse_ddl


# ── 1. Full DDL: table count ───────────────────────────────────────

def test_ecommerce_table_count(ecommerce_ddl: str):
    erd = parse_ddl(ecommerce_ddl)
    assert len(erd.tables) == 12


# ── 2. Full DDL: FK count ─────────────────────────────────────────

def test_ecommerce_fk_count(ecommerce_ddl: str):
    erd = parse_ddl(ecommerce_ddl)
    assert len(erd.foreign_keys) == 15


# ── 3. Single table, no FK ────────────────────────────────────────

def test_single_table_no_fk():
    ddl = """
    CREATE TABLE users (
        id SERIAL PRIMARY KEY,
        name VARCHAR(100) NOT NULL
    );
    """
    erd = parse_ddl(ddl)
    assert len(erd.tables) == 1
    assert erd.tables[0].name == "users"
    assert len(erd.foreign_keys) == 0


# ── 4. Column types preserved ─────────────────────────────────────

def test_column_types_preserved(ecommerce_ddl: str):
    erd = parse_ddl(ecommerce_ddl)
    products = next(t for t in erd.tables if t.name == "products")
    col_map = {c.name: c.data_type for c in products.columns}
    assert "SERIAL" in col_map["id"].upper()
    assert "VARCHAR" in col_map["name"].upper()
    assert "DECIMAL" in col_map["price"].upper()


# ── 5. Nullable detection ─────────────────────────────────────────

def test_nullable_detection(ecommerce_ddl: str):
    erd = parse_ddl(ecommerce_ddl)
    addresses = next(t for t in erd.tables if t.name == "addresses")
    col_map = {c.name: c for c in addresses.columns}
    # NOT NULL columns
    assert col_map["city"].nullable is False
    assert col_map["district"].nullable is False
    # nullable column
    assert col_map["zip_code"].nullable is True


# ── 6. Self-referential FK ────────────────────────────────────────

def test_self_referential_fk(ecommerce_ddl: str):
    erd = parse_ddl(ecommerce_ddl)
    self_fks = [
        fk for fk in erd.foreign_keys
        if fk.source_table == fk.target_table
    ]
    assert len(self_fks) == 1
    assert self_fks[0].source_table == "categories"
    assert self_fks[0].source_column == "parent_id"
    assert self_fks[0].target_column == "id"


# ── 7. Multiple FKs from same table ──────────────────────────────

def test_multiple_fks_same_table(ecommerce_ddl: str):
    erd = parse_ddl(ecommerce_ddl)
    product_fks = [fk for fk in erd.foreign_keys if fk.source_table == "products"]
    fk_cols = {fk.source_column for fk in product_fks}
    assert fk_cols == {"category_id", "supplier_id"}


# ── 8. Nullable FK ────────────────────────────────────────────────

def test_nullable_fk(ecommerce_ddl: str):
    erd = parse_ddl(ecommerce_ddl)
    orders = next(t for t in erd.tables if t.name == "orders")
    coupon_col = next(c for c in orders.columns if c.name == "coupon_id")
    # coupon_id has no NOT NULL — should be nullable
    assert coupon_col.nullable is True
    # Verify FK still exists
    coupon_fk = next(
        fk for fk in erd.foreign_keys
        if fk.source_table == "orders" and fk.source_column == "coupon_id"
    )
    assert coupon_fk.target_table == "coupons"


# ── 9. Empty DDL ──────────────────────────────────────────────────

def test_empty_ddl():
    erd = parse_ddl("")
    assert erd.tables == []
    assert erd.foreign_keys == []


# ── 10. Non-CREATE statements ignored ─────────────────────────────

def test_non_create_ignored():
    ddl = """
    DROP TABLE IF EXISTS old_table;
    ALTER TABLE something ADD COLUMN x INT;
    INSERT INTO logs VALUES (1, 'hello');
    CREATE TABLE fresh (
        id SERIAL PRIMARY KEY,
        val TEXT
    );
    """
    erd = parse_ddl(ddl)
    assert len(erd.tables) == 1
    assert erd.tables[0].name == "fresh"
