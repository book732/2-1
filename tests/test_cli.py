from __future__ import annotations

import csv
import io
import unittest
from contextlib import redirect_stdout
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import patch

from budget_app.cli import main


class BudgetCliTests(unittest.TestCase):
    def setUp(self) -> None:
        self._temporary_directory = TemporaryDirectory()
        self._root = Path(self._temporary_directory.name)
        self._data_dir = self._root / "data"

    def tearDown(self) -> None:
        self._temporary_directory.cleanup()

    def _run(self, *args: str) -> tuple[int, str]:
        _output = io.StringIO()
        with redirect_stdout(_output):
            _status = main(["--data-dir", str(self._data_dir), *args])
        return _status, _output.getvalue()

    def test_budget_workflow_and_latest_first(self) -> None:
        self.assertEqual(self._run("category", "add", "--name", "food")[0], 0)
        self.assertEqual(self._run("category", "add", "--name", "salary")[0], 0)

        with patch("builtins.input", side_effect=["2024-01-14", "income", "salary", "3000000", "급여", ""]):
            self.assertEqual(self._run("add")[0], 0)
        with patch("builtins.input", side_effect=["2024-01-15", "expense", "food", "15000", "점심", "meal"]):
            self.assertEqual(self._run("add")[0], 0)

        _status, _output = self._run("list", "--limit", "1")
        self.assertEqual(_status, 0)
        self.assertIn("TX-000002", _output)

        _status, _output = self._run("search", "--tag", "meal")
        self.assertEqual(_status, 0)
        self.assertIn("TX-000002", _output)
        self.assertEqual(
            self._run("update", "--id", "TX-000002", "--memo", "저녁", "--tags", "dinner")[0], 0
        )
        _status, _output = self._run("search", "--q", "저녁")
        self.assertEqual(_status, 0)
        self.assertIn("dinner", _output)

        self.assertEqual(self._run("budget", "set", "--month", "2024-01", "--amount", "10000")[0], 0)
        _status, _output = self._run("summary", "--month", "2024-01")
        self.assertEqual(_status, 0)
        self.assertIn("총 수입 : 3000000 원", _output)
        self.assertIn("[경고] 예산 초과 : 5000 원", _output)

        _status, _output = self._run("category", "remove", "--name", "food")
        self.assertEqual(_status, 2)
        self.assertIn("사용 중인 카테고리", _output)
        self.assertEqual(self._run("delete", "--id", "TX-000002")[0], 0)
        self.assertEqual(self._run("category", "remove", "--name", "food")[0], 0)

    def test_import_export_and_validation(self) -> None:
        self.assertEqual(self._run("category", "add", "--name", "transport")[0], 0)
        _source = self._root / "input.csv"
        with _source.open("w", encoding="utf-8", newline="") as _stream:
            _writer = csv.DictWriter(_stream, fieldnames=["date", "type", "category", "amount", "memo", "tags"])
            _writer.writeheader()
            _writer.writerow(
                {"date": "2024-01-12", "type": "expense", "category": "transport", "amount": "20000", "memo": "버스", "tags": "commute"}
            )
            _writer.writerow(
                {"date": "2024-13-01", "type": "expense", "category": "transport", "amount": "10", "memo": "bad", "tags": ""}
            )

        _status, _output = self._run("import", "--from", str(_source))
        self.assertEqual(_status, 0)
        self.assertIn("imported=1, skipped=1", _output)

        _output_path = self._root / "output.csv"
        self.assertEqual(self._run("export", "--out", str(_output_path), "--month", "2024-01")[0], 0)
        with _output_path.open(encoding="utf-8", newline="") as _stream:
            self.assertEqual(next(csv.DictReader(_stream))["memo"], "버스")

        _status, _output = self._run("delete", "--id", "TX-999999")
        self.assertEqual(_status, 2)
        self.assertIn("거래를 찾을 수 없습니다", _output)

    def test_invalid_amount_and_cancellation_are_friendly(self) -> None:
        self.assertEqual(self._run("category", "add", "--name", "food")[0], 0)
        with patch("builtins.input", side_effect=["2026-09-16", "expense", "food", "점심"]):
            _status, _output = self._run("add")
        self.assertEqual(_status, 2)
        self.assertIn("금액은 정수로 입력해야 합니다", _output)

        with patch("builtins.input", side_effect=KeyboardInterrupt):
            _status, _output = self._run("add")
        self.assertEqual(_status, 130)
        self.assertIn("[취소] 입력이 취소되었습니다", _output)


if __name__ == "__main__":
    unittest.main()
