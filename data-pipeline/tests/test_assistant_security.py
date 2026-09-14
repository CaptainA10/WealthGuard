from __future__ import annotations

import pytest

from wealthguard_pipeline.assistant.security import (
    ALLOWED_TABLES,
    QueryValidationError,
    validate_and_prepare,
)

MAX_ROWS = 50


def _validate(sql: str) -> str:
    return validate_and_prepare(sql, max_rows=MAX_ROWS)


class TestAcceptsLegitimateQueries:
    def test_accepts_a_simple_select(self):
        result = _validate("SELECT client_id, full_name FROM clients")

        assert result == "SELECT client_id, full_name FROM clients LIMIT 50"

    def test_accepts_a_query_joining_only_whitelisted_tables(self):
        sql = (
            "SELECT c.full_name, p.ticker FROM clients c "
            "JOIN positions p ON p.client_id = c.client_id"
        )

        result = _validate(sql)

        assert "LIMIT 50" in result

    def test_accepts_a_cte(self):
        sql = (
            "WITH totals AS (SELECT client_id, COUNT(*) AS n FROM positions GROUP BY client_id) "
            "SELECT * FROM totals"
        )

        result = _validate(sql)

        assert result.startswith("WITH totals AS")

    def test_accepts_multiple_ctes(self):
        sql = (
            "WITH a AS (SELECT client_id FROM clients), "
            "b AS (SELECT client_id FROM positions) "
            "SELECT * FROM a JOIN b USING (client_id)"
        )

        result = _validate(sql)

        assert "LIMIT 50" in result

    def test_a_cte_cannot_launder_access_to_a_forbidden_table(self):
        # Naming the CTE the same as a real, allowed table must not exempt
        # its own body from the whitelist check.
        sql = "WITH clients AS (SELECT * FROM pg_shadow) SELECT * FROM clients"

        with pytest.raises(QueryValidationError, match="pg_shadow"):
            _validate(sql)

    def test_accepts_schema_qualified_table_references(self):
        result = _validate("SELECT * FROM wealthguard.clients")

        assert "LIMIT 50" in result

    def test_is_case_insensitive_on_keywords(self):
        result = _validate("select * from Clients")

        assert result == "select * from Clients LIMIT 50"

    def test_strips_a_markdown_code_fence(self):
        result = _validate("```sql\nSELECT * FROM clients\n```")

        assert result == "SELECT * FROM clients LIMIT 50"

    def test_accepts_a_trailing_semicolon(self):
        result = _validate("SELECT * FROM clients;")

        assert result == "SELECT * FROM clients LIMIT 50"


class TestRowCapping:
    def test_appends_limit_when_absent(self):
        result = _validate("SELECT * FROM clients")

        assert result.endswith("LIMIT 50")

    def test_leaves_an_existing_smaller_limit_untouched(self):
        result = _validate("SELECT * FROM clients LIMIT 5")

        assert result == "SELECT * FROM clients LIMIT 5"

    def test_leaves_an_existing_larger_limit_untouched(self):
        # Deliberately not re-capped down: table whitelisting and the
        # read-only transaction are the security boundary, not row count --
        # this only exists to bound accidental full-table dumps.
        result = _validate("SELECT * FROM clients LIMIT 999999")

        assert result == "SELECT * FROM clients LIMIT 999999"


class TestRejectsUnsafeQueries:
    @pytest.mark.parametrize(
        "sql",
        [
            "INSERT INTO clients (client_id) VALUES ('X')",
            "UPDATE clients SET full_name = 'x'",
            "DELETE FROM clients",
            "DROP TABLE clients",
            "ALTER TABLE clients ADD COLUMN x TEXT",
            "TRUNCATE clients",
            "GRANT ALL ON clients TO public",
            "SELECT * FROM clients; DROP TABLE clients",
            "COPY clients TO '/tmp/out.csv'",
        ],
    )
    def test_rejects_a_write_or_ddl_statement(self, sql):
        with pytest.raises(QueryValidationError):
            _validate(sql)

    def test_rejects_a_second_statement_after_a_semicolon(self):
        with pytest.raises(QueryValidationError, match="Une seule instruction"):
            _validate("SELECT * FROM clients; SELECT * FROM instruments")

    def test_rejects_a_table_outside_the_whitelist(self):
        with pytest.raises(QueryValidationError, match="pg_shadow"):
            _validate("SELECT * FROM pg_shadow")

    def test_rejects_a_query_with_no_recognisable_table(self):
        with pytest.raises(QueryValidationError, match="Aucune table"):
            _validate("SELECT 1")

    def test_rejects_prose_that_is_not_sql_at_all(self):
        with pytest.raises(QueryValidationError):
            _validate("Voici la reponse a votre question : les clients sont nombreux.")

    def test_rejects_an_empty_query(self):
        with pytest.raises(QueryValidationError, match="vide"):
            _validate("")

    def test_rejects_whitespace_only(self):
        with pytest.raises(QueryValidationError):
            _validate("   \n  ")

    def test_error_message_lists_the_allowed_tables(self):
        with pytest.raises(QueryValidationError) as exc_info:
            _validate("SELECT * FROM secrets")

        for table in ALLOWED_TABLES:
            assert table in str(exc_info.value)
