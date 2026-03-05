"""Demo v0 pipeline orchestrator.

Usage:
    docker compose up -d
    pip install -r requirements.txt
    cd backend && python demo.py

Pipeline: DDL Parse → Ontology → Data Gen → Neo4j Load → Q&A
"""

from __future__ import annotations

import os
import sys
from pathlib import Path

# Add backend to sys.path so `app.*` imports work
sys.path.insert(0, str(Path(__file__).resolve().parent))

from dotenv import load_dotenv

from app.ddl_parser.parser import parse_ddl_file
from app.ontology.fk_rule_engine import build_ontology
from app.data_generator.generator import generate_sample_data, verify_fk_integrity
from app.kg_builder.loader import load_to_neo4j
from app.query.pipeline import run_query


def _sep(title: str):
    print(f"\n{'=' * 60}")
    print(f"  {title}")
    print(f"{'=' * 60}")


def main():
    # ── Load config ────────────────────────────────────────────────
    env_path = Path(__file__).resolve().parent.parent / ".env.example"
    load_dotenv(env_path)

    neo4j_uri = os.getenv("NEO4J_URI", "bolt://localhost:7687")
    neo4j_user = os.getenv("NEO4J_USER", "neo4j")
    neo4j_password = os.getenv("NEO4J_PASSWORD", "password123")

    ddl_path = Path(__file__).resolve().parent.parent / "examples" / "schemas" / "demo_ecommerce.sql"

    # ── Step 1: DDL Parsing ────────────────────────────────────────
    _sep("Step 1: DDL Parsing")
    erd = parse_ddl_file(ddl_path)
    print(f"  Tables:       {len(erd.tables)}")
    print(f"  Foreign Keys: {len(erd.foreign_keys)}")
    for t in erd.tables:
        pk = t.primary_key or "-"
        print(f"    - {t.name} ({len(t.columns)} cols, PK={pk})")
    assert len(erd.tables) == 12, f"Expected 12 tables, got {len(erd.tables)}"
    assert len(erd.foreign_keys) == 15, f"Expected 15 FKs, got {len(erd.foreign_keys)}"
    print("  [PASS] 12 tables, 15 FKs")

    # ── Step 2: Ontology Generation ────────────────────────────────
    _sep("Step 2: Ontology Generation (FK Rules)")
    ontology = build_ontology(erd)
    print(f"  Node types:         {len(ontology.node_types)}")
    for nt in ontology.node_types:
        print(f"    - {nt.name} (from {nt.source_table}, {len(nt.properties)} props)")
    print(f"  Relationship types: {len(ontology.relationship_types)}")
    for rt in ontology.relationship_types:
        print(f"    - ({rt.source_node})-[{rt.name}]->({rt.target_node})")
    assert len(ontology.node_types) == 9, f"Expected 9 node types, got {len(ontology.node_types)}"
    assert len(ontology.relationship_types) == 12, f"Expected 12 rel types, got {len(ontology.relationship_types)}"
    print("  [PASS] 9 node types, 12 relationship types")

    # ── Step 3: Sample Data Generation ─────────────────────────────
    _sep("Step 3: Sample Data Generation")
    data = generate_sample_data(erd)
    for table_name, rows in data.items():
        print(f"    - {table_name}: {len(rows)} rows")
    violations = verify_fk_integrity(data, erd)
    if violations:
        print("  [FAIL] FK integrity violations:")
        for v in violations:
            print(f"    ! {v}")
        sys.exit(1)
    print("  [PASS] FK integrity check PASSED (0 violations)")

    # ── Step 4: Neo4j Loading ──────────────────────────────────────
    _sep("Step 4: Neo4j Loading")
    print(f"  Connecting to {neo4j_uri} ...")
    stats = load_to_neo4j(ontology, data, neo4j_uri, neo4j_user, neo4j_password)
    print(f"  Loaded nodes:         {stats['nodes']}")
    print(f"  Loaded relationships: {stats['relationships']}")
    print(f"  Neo4j node count:     {stats['neo4j_nodes']}")
    print(f"  Neo4j rel count:      {stats['neo4j_relationships']}")
    print("  [PASS] Neo4j loading complete")

    # ── Step 5: Q&A Demo ──────────────────────────────────────────
    _sep("Step 5: Q&A Demo")
    demo_questions = [
        "고객 김민수가 주문한 상품은?",
        "김민수가 주문한 상품과 같은 카테고리에서 리뷰 평점 Top 3 상품은?",
        "가장 많이 팔린 카테고리 Top 3는?",
    ]
    for i, question in enumerate(demo_questions, 1):
        r = run_query(question, mode="a")
        print(f"\n  Q{i}: {r.question}")
        print(f"  A{i}: {r.answer}")
        print(f"  Template: {r.template_id}")
        print(f"  Cypher: {r.cypher[:80]}...")
        print(f"  Evidence paths:")
        for p in r.paths:
            print(f"    - {p}")

    # ── Done ───────────────────────────────────────────────────────
    _sep("Demo Complete!")
    print("  All 5 steps passed successfully.")
    print("  DDL -> KG -> Q&A pipeline is working end-to-end.\n")


if __name__ == "__main__":
    main()
