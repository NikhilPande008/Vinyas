---
name: ops-db-guardrails
description: Enforces database schema, naming, and SQL query safety guardrails for Vinyas SQLite demo storage and production PostgreSQL/AlloyDB schema validation.
---

# Vinyas Database Guardrails (`ops-db-guardrails`)

## Core Rules
1. **Strict Naming Convention:** All table names and column identifiers MUST use `snake_case` (e.g., `equipment_sops`, `inspection_incidents`, `work_orders`).
2. **Mandatory Primary Key:** Every table MUST define a primary key column named `id`.
3. **Parameterized Queries Only:** All runtime SQL queries MUST use parameterized placeholders (`$1, $2` for PostgreSQL or `?, ?` for SQLite). Raw string interpolation or Python f-strings inside SQL statements are strictly prohibited.
4. **Destructive DDL Prohibition:** Block any statement containing `DROP TABLE`, `DROP DATABASE`, `TRUNCATE TABLE`, or unqualified `DELETE FROM` without a `WHERE` clause.

## Enforcement Checklist
- Verify `CREATE TABLE IF NOT EXISTS <table_name>` has `id` as `PRIMARY KEY`.
- Verify vector search queries use bound parameters and match the embedding dimensionality of `gemini-embedding-2`.
