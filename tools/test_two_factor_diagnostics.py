"""Diagnostico sem banco real: python -m unittest tools.test_two_factor_diagnostics."""

import unittest
from unittest.mock import Mock

from psycopg2.errors import InsufficientPrivilege

from backend.two_factor import _state


class PermissionDiagnosticTests(unittest.TestCase):
    def test_permission_log_excludes_secrets_and_preserves_exception(self):
        cursor = Mock()
        failure = InsufficientPrivilege("permission denied")
        cursor.execute.side_effect = failure
        cursor.connection.get_dsn_parameters.return_value = {
            "user": "runtime_role", "dbname": "runtime_db", "host": "runtime.example.invalid",
            "password": "SECRET_PASSWORD", "options": "SECRET_OPTIONS",
            "dsn": "postgresql://runtime_role:SECRET_PASSWORD@runtime.example.invalid/runtime_db",
        }
        with self.assertLogs("backend.two_factor", level="ERROR") as captured:
            with self.assertRaises(InsufficientPrivilege) as raised:
                _state(cursor, "PRIVATE_ACCOUNT_ID")
        self.assertIs(raised.exception, failure)
        output = "\n".join(captured.output)
        for expected in ("DB_PERMISSION_DIAGNOSTIC", "runtime_role", "runtime_db", "runtime.example.invalid"):
            self.assertIn(expected, output)
        for private in ("SECRET_PASSWORD", "SECRET_OPTIONS", "postgresql://", "PRIVATE_ACCOUNT_ID"):
            self.assertNotIn(private, output)

    def test_metadata_failure_does_not_replace_database_error(self):
        cursor = Mock()
        failure = InsufficientPrivilege("permission denied")
        cursor.execute.side_effect = failure
        cursor.connection.get_dsn_parameters.side_effect = RuntimeError("PRIVATE_METADATA_ERROR")
        with self.assertLogs("backend.two_factor", level="ERROR") as captured:
            with self.assertRaises(InsufficientPrivilege) as raised:
                _state(cursor, "PRIVATE_ACCOUNT_ID")
        self.assertIs(raised.exception, failure)
        self.assertNotIn("PRIVATE_METADATA_ERROR", "\n".join(captured.output))

    def test_success_returns_state_without_diagnostic(self):
        cursor = Mock()
        cursor.fetchone.return_value = {"secret_encrypted": None}
        with self.assertNoLogs("backend.two_factor", level="ERROR"):
            self.assertEqual(_state(cursor, "account"), {"secret_encrypted": None})


if __name__ == "__main__":
    unittest.main()
