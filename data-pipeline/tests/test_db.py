from __future__ import annotations

from wealthguard_pipeline.db import _split_statements


class TestSplitStatements:
    def test_splits_two_simple_statements(self):
        sql = "CREATE TABLE a (x INT); CREATE TABLE b (y INT);"

        assert _split_statements(sql) == ["CREATE TABLE a (x INT)", "CREATE TABLE b (y INT)"]

    def test_keeps_a_statement_preceded_by_a_comment_block(self):
        """Regression test: every table in schema.sql is preceded by a
        multi-line comment. A version of this function that only checked
        whether a whole chunk's *first line* was a comment silently dropped
        the real SQL that followed it -- exactly what happened to
        `CREATE TABLE pipeline_runs`, added after the other tables, and only
        caught because the next statement (an index on that table) then
        failed with "relation does not exist"."""
        sql = (
            "-- Some explanatory comment.\n"
            "-- Spanning several lines.\n"
            "CREATE TABLE pipeline_runs (\n"
            "    run_id UUID PRIMARY KEY\n"
            ");\n"
            "CREATE INDEX idx_pipeline_runs_run_at ON pipeline_runs(run_at);\n"
        )

        statements = _split_statements(sql)

        assert len(statements) == 2
        assert "CREATE TABLE pipeline_runs" in statements[0]
        assert "run_id UUID PRIMARY KEY" in statements[0]
        assert statements[1] == "CREATE INDEX idx_pipeline_runs_run_at ON pipeline_runs(run_at)"

    def test_ignores_a_standalone_comment_line_between_statements(self):
        sql = "CREATE TABLE a (x INT);\n-- just a note\nCREATE TABLE b (y INT);"

        assert _split_statements(sql) == ["CREATE TABLE a (x INT)", "CREATE TABLE b (y INT)"]

    def test_ignores_leading_and_trailing_whitespace_only_chunks(self):
        sql = "  \n\nCREATE TABLE a (x INT);\n\n  \n"

        assert _split_statements(sql) == ["CREATE TABLE a (x INT)"]

    def test_empty_input_yields_no_statements(self):
        assert _split_statements("") == []
        assert _split_statements("-- only a comment\n") == []
