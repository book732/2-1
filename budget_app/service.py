from __future__ import annotations

import csv
import logging
from calendar import monthrange
from collections.abc import Iterator
from datetime import date
from pathlib import Path

from .decorators import log_execution
from .models import MonthlySummary, RecurringRule, Transaction
from .storage import BackupStore, BudgetStore, CategoryStore, DataPaths, RecurringRepository, TransactionRepository


class ValidationError(ValueError):
    pass


class NotFoundError(LookupError):
    pass


class BudgetService:
    def __init__(self, _data_dir: Path) -> None:
        _paths = DataPaths(_data_dir)
        _paths.ensure_exists()
        self._transactions = TransactionRepository(_paths)
        self._categories = CategoryStore(_paths)
        self._budgets = BudgetStore(_paths)
        self._recurrences = RecurringRepository(_paths)
        self._backups = BackupStore(_paths)
        self._logger = logging.getLogger(f"budget_app.{_data_dir.resolve()}")
        if not self._logger.handlers:
            _handler = logging.FileHandler(_data_dir / "budget_app.log", encoding="utf-8")
            _handler.setFormatter(logging.Formatter("%(asctime)s %(levelname)s %(message)s"))
            self._logger.addHandler(_handler)
            self._logger.setLevel(logging.INFO)
            self._logger.propagate = False

    def close(self) -> None:
        """Release log file handles held by this service instance."""

        for _handler in tuple(self._logger.handlers):
            self._logger.removeHandler(_handler)
            _handler.close()

    @staticmethod
    def _validate_date(_value: str) -> str:
        try:
            return date.fromisoformat(_value).isoformat()
        except ValueError as _error:
            raise ValidationError("날짜 형식이 올바르지 않습니다 (YYYY-MM-DD).") from _error

    @staticmethod
    def _validate_month(_value: str) -> str:
        try:
            _parsed = date.fromisoformat(f"{_value}-01")
        except ValueError as _error:
            raise ValidationError("월 형식이 올바르지 않습니다 (YYYY-MM).") from _error
        if _parsed.strftime("%Y-%m") != _value:
            raise ValidationError("월 형식이 올바르지 않습니다 (YYYY-MM).")
        return _value

    @staticmethod
    def _validate_amount(_value: int) -> int:
        if _value <= 0:
            raise ValidationError("금액은 0보다 커야 합니다.")
        return _value

    @staticmethod
    def _validate_day(_value: int) -> int:
        if not 1 <= _value <= 31:
            raise ValidationError("반복 일자는 1부터 31 사이여야 합니다.")
        return _value

    @staticmethod
    def _validate_type(_value: str) -> str:
        if _value not in {"income", "expense"}:
            raise ValidationError("거래 유형은 income 또는 expense여야 합니다.")
        return _value

    def _validate_category(self, _value: str) -> str:
        _category = _value.strip()
        if not _category:
            raise ValidationError("카테고리를 입력해야 합니다.")
        if not self._categories.contains(_category):
            raise ValidationError(f"등록되지 않은 카테고리입니다: {_category}. category add로 먼저 추가하세요.")
        return _category

    @staticmethod
    def _normalize_tags(_value: str | tuple[str, ...]) -> tuple[str, ...]:
        _parts = _value.split(",") if isinstance(_value, str) else _value
        return tuple(_tag.strip() for _tag in _parts if _tag.strip())

    @log_execution
    def add_transaction(
        self, *, _date: str, _type: str, _category: str, _amount: int, _memo: str, _tags: str
    ) -> Transaction:
        _transaction = self._build_transaction(
            _transaction_id=self._transactions.next_id(),
            _date=self._validate_date(_date),
            _type=self._validate_type(_type),
            _category=self._validate_category(_category),
            _amount=self._validate_amount(_amount),
            _memo=_memo.strip(),
            _tags=self._normalize_tags(_tags),
        )
        self._transactions.append(_transaction)
        return _transaction

    def _build_transaction(
        self,
        *,
        _transaction_id: str,
        _date: str,
        _type: str,
        _category: str,
        _amount: int,
        _memo: str,
        _tags: tuple[str, ...],
        _recurrence_id: str | None = None,
    ) -> Transaction:
        return Transaction(
            id=_transaction_id,
            date=_date,
            type=_type,
            category=_category,
            amount=_amount,
            memo=_memo,
            tags=_tags,
            recurrence_id=_recurrence_id,
        )

    def list_transactions(self, _limit: int | None = None) -> Iterator[Transaction]:
        if _limit is not None and _limit <= 0:
            raise ValidationError("--limit은 1 이상의 정수여야 합니다.")
        for _index, _transaction in enumerate(self._transactions.iter_transactions(_reverse=True), start=1):
            if _limit is not None and _index > _limit:
                return
            yield _transaction

    def search_transactions(
        self,
        *,
        _from: str | None,
        _to: str | None,
        _category: str | None,
        _type: str | None,
        _query: str | None,
        _tag: str | None,
    ) -> Iterator[Transaction]:
        if _from:
            self._validate_date(_from)
        if _to:
            self._validate_date(_to)
        if _from and _to and _from > _to:
            raise ValidationError("시작일은 종료일보다 늦을 수 없습니다.")
        if _type:
            self._validate_type(_type)
        _query = _query.casefold() if _query else None
        for _transaction in self._transactions.iter_transactions(_reverse=True):
            if _from and _transaction.date < _from:
                continue
            if _to and _transaction.date > _to:
                continue
            if _category and _transaction.category != _category:
                continue
            if _type and _transaction.type != _type:
                continue
            if _query and _query not in _transaction.memo.casefold():
                continue
            if _tag and _tag not in _transaction.tags:
                continue
            yield _transaction

    @log_execution
    def update_transaction(self, _transaction_id: str, **_changes: object) -> Transaction:
        _current = self._transactions.get(_transaction_id)
        if _current is None:
            raise NotFoundError(f"거래를 찾을 수 없습니다: {_transaction_id}")
        _transaction = Transaction(
            id=_current.id,
            date=self._validate_date(str(_changes.get("date", _current.date))),
            type=self._validate_type(str(_changes.get("type", _current.type))),
            category=self._validate_category(str(_changes.get("category", _current.category))),
            amount=self._validate_amount(int(_changes.get("amount", _current.amount))),
            memo=str(_changes.get("memo", _current.memo)).strip(),
            tags=self._normalize_tags(_changes.get("tags", _current.tags)),
            recurrence_id=_current.recurrence_id,
        )
        self._transactions.replace(_transaction_id, _transaction)
        return _transaction

    @log_execution
    def delete_transaction(self, _transaction_id: str) -> None:
        if not self._transactions.delete(_transaction_id):
            raise NotFoundError(f"거래를 찾을 수 없습니다: {_transaction_id}")

    def summarize(self, _month: str) -> MonthlySummary:
        _month = self._validate_month(_month)
        _income = 0
        _expense = 0
        _category_expenses: dict[str, int] = {}
        for _transaction in self._transactions.iter_transactions():
            if not _transaction.date.startswith(_month):
                continue
            if _transaction.type == "income":
                _income += _transaction.amount
            else:
                _expense += _transaction.amount
                _category_expenses[_transaction.category] = (
                    _category_expenses.get(_transaction.category, 0) + _transaction.amount
                )
        return MonthlySummary(_income, _expense, _category_expenses, self._budgets.get(_month))

    @log_execution
    def set_budget(self, _month: str, _amount: int) -> None:
        self._budgets.set(self._validate_month(_month), self._validate_amount(_amount))

    @log_execution
    def add_category(self, _name: str) -> bool:
        _name = _name.strip()
        if not _name:
            raise ValidationError("카테고리를 입력해야 합니다.")
        return self._categories.add(_name)

    def list_categories(self) -> list[str]:
        return self._categories.list()

    def get_transaction(self, _transaction_id: str) -> Transaction | None:
        return self._transactions.get(_transaction_id)

    @log_execution
    def create_backup(self) -> tuple[Path, ...]:
        return self._backups.create()

    @log_execution
    def add_recurring_rule(
        self,
        *,
        _type: str,
        _category: str,
        _amount: int,
        _day: int,
        _memo: str,
        _tags: str,
    ) -> RecurringRule:
        _rule = RecurringRule(
            id=self._recurrences.next_id(),
            type=self._validate_type(_type),
            category=self._validate_category(_category),
            amount=self._validate_amount(_amount),
            day=self._validate_day(_day),
            memo=_memo.strip(),
            tags=self._normalize_tags(_tags),
        )
        self._recurrences.append(_rule)
        return _rule

    def list_recurring_rules(self) -> Iterator[RecurringRule]:
        yield from self._recurrences.iter_rules()

    @log_execution
    def apply_recurring_rules(self, _month: str) -> tuple[int, int]:
        _month = self._validate_month(_month)
        _year, _month_number = (int(_part) for _part in _month.split("-"))
        _last_day = monthrange(_year, _month_number)[1]
        _already_created = {
            _transaction.recurrence_id
            for _transaction in self._transactions.iter_transactions()
            if _transaction.recurrence_id and _transaction.date.startswith(_month)
        }
        _next_number = int(self._transactions.next_id().removeprefix("TX-"))
        _created = 0
        _skipped = 0

        def _transactions() -> Iterator[Transaction]:
            nonlocal _created, _next_number, _skipped
            for _rule in self._recurrences.iter_rules():
                if _rule.id in _already_created or _rule.day > _last_day:
                    _skipped += 1
                    continue
                _transaction = self._build_transaction(
                    _transaction_id=f"TX-{_next_number:06d}",
                    _date=date(_year, _month_number, _rule.day).isoformat(),
                    _type=_rule.type,
                    _category=_rule.category,
                    _amount=_rule.amount,
                    _memo=_rule.memo,
                    _tags=_rule.tags,
                    _recurrence_id=_rule.id,
                )
                _next_number += 1
                _created += 1
                yield _transaction

        self._transactions.append_many(_transactions())
        return _created, _skipped

    @log_execution
    def remove_category(self, _name: str) -> None:
        if not self._categories.contains(_name):
            raise NotFoundError(f"카테고리를 찾을 수 없습니다: {_name}")
        if any(_transaction.category == _name for _transaction in self._transactions.iter_transactions()):
            raise ValidationError(f"사용 중인 카테고리입니다: {_name}. 거래를 먼저 변경하거나 삭제하세요.")
        self._categories.remove(_name)

    @log_execution
    def import_csv(self, _source: Path) -> tuple[int, int]:
        _imported = 0
        _skipped = 0
        _next_number = int(self._transactions.next_id().removeprefix("TX-"))
        with _source.open("r", encoding="utf-8", newline="") as _stream:
            _reader = csv.DictReader(_stream)
            _required = {"date", "type", "category", "amount", "memo", "tags"}
            if _reader.fieldnames is None or not _required.issubset(_reader.fieldnames):
                raise ValidationError("CSV 헤더가 올바르지 않습니다. date,type,category,amount,memo,tags가 필요합니다.")
            def _transactions() -> Iterator[Transaction]:
                nonlocal _imported, _skipped, _next_number
                for _row in _reader:
                    try:
                        _transaction = self._build_transaction(
                            _transaction_id=f"TX-{_next_number:06d}",
                            _date=self._validate_date(_row["date"]),
                            _type=self._validate_type(_row["type"]),
                            _category=self._validate_category(_row["category"]),
                            _amount=self._validate_amount(int(_row["amount"])),
                            _memo=_row["memo"].strip(),
                            _tags=self._normalize_tags(_row["tags"]),
                        )
                    except (ValueError, ValidationError):
                        _skipped += 1
                        continue
                    _next_number += 1
                    _imported += 1
                    yield _transaction

            self._transactions.append_many(_transactions())
        return _imported, _skipped

    def export_csv(
        self, *, _output: Path, _month: str | None, _from: str | None, _to: str | None
    ) -> int:
        if bool(_month) == bool(_from or _to):
            raise ValidationError("export에는 --month 또는 --from과 --to를 지정해야 합니다.")
        if _month:
            _month = self._validate_month(_month)
            _year, _month_number = (int(_part) for _part in _month.split("-"))
            _from = f"{_month}-01"
            _to = f"{_month}-{monthrange(_year, _month_number)[1]:02d}"
        if not _from or not _to:
            raise ValidationError("기간 내보내기는 --from과 --to를 함께 지정해야 합니다.")
        _transactions = self.search_transactions(
            _from=_from, _to=_to, _category=None, _type=None, _query=None, _tag=None
        )
        _output.parent.mkdir(parents=True, exist_ok=True)
        _count = 0
        with _output.open("w", encoding="utf-8", newline="") as _stream:
            _writer = csv.DictWriter(
                _stream, fieldnames=["date", "type", "category", "amount", "memo", "tags"]
            )
            _writer.writeheader()
            for _transaction in _transactions:
                _writer.writerow(
                    {
                        "date": _transaction.date,
                        "type": _transaction.type,
                        "category": _transaction.category,
                        "amount": _transaction.amount,
                        "memo": _transaction.memo,
                        "tags": ",".join(_transaction.tags),
                    }
                )
                _count += 1
        return _count
