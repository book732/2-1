from __future__ import annotations

import json
import os
import shutil
import tempfile
from collections.abc import Iterable, Iterator
from datetime import datetime
from pathlib import Path
from typing import Any

from .models import RecurringRule, Transaction


class DataPaths:
    def __init__(self, _data_dir: Path) -> None:
        self._data_dir = _data_dir
        self._transactions = _data_dir / "transactions.jsonl"
        self._categories = _data_dir / "categories.jsonl"
        self._budgets = _data_dir / "budgets.jsonl"
        self._recurrences = _data_dir / "recurrences.jsonl"

    def ensure_exists(self) -> None:
        self._data_dir.mkdir(parents=True, exist_ok=True)
        for _path in self.data_files():
            _path.touch(exist_ok=True)

    def data_files(self) -> tuple[Path, ...]:
        return self._transactions, self._categories, self._budgets, self._recurrences


def _iter_json_records(_path: Path, *, _reverse: bool = False) -> Iterator[dict[str, Any]]:
    if not _path.exists():
        return
    if not _reverse:
        with _path.open("r", encoding="utf-8") as _stream:
            for _line in _stream:
                if _line.strip():
                    yield json.loads(_line)
        return

    # Read fixed-size blocks so recent JSONL records can be streamed in reverse.
    with _path.open("rb") as _stream:
        _stream.seek(0, os.SEEK_END)
        _position = _stream.tell()
        _buffer = b""
        while _position:
            _size = min(65_536, _position)
            _position -= _size
            _stream.seek(_position)
            _buffer = _stream.read(_size) + _buffer
            _lines = _buffer.split(b"\n")
            _buffer = _lines[0]
            for _line in reversed(_lines[1:]):
                if _line.strip():
                    yield json.loads(_line)
        if _buffer.strip():
            yield json.loads(_buffer)


def _atomic_write_jsonl(_path: Path, _records: Iterable[dict[str, Any]]) -> None:
    _path.parent.mkdir(parents=True, exist_ok=True)
    _file_descriptor, _temporary_name = tempfile.mkstemp(
        prefix=f".{_path.stem}-", suffix=".tmp", dir=_path.parent, text=True
    )
    try:
        with os.fdopen(_file_descriptor, "w", encoding="utf-8", newline="\n") as _stream:
            for _record in _records:
                _stream.write(json.dumps(_record, ensure_ascii=False, separators=(",", ":")))
                _stream.write("\n")
            _stream.flush()
            os.fsync(_stream.fileno())
        os.replace(_temporary_name, _path)
    except BaseException:
        if os.path.exists(_temporary_name):
            os.unlink(_temporary_name)
        raise


class TransactionRepository:
    def __init__(self, _paths: DataPaths) -> None:
        self._paths = _paths

    def iter_transactions(self, *, _reverse: bool = False) -> Iterator[Transaction]:
        for _record in _iter_json_records(self._paths._transactions, _reverse=_reverse):
            yield Transaction.from_dict(_record)

    def append(self, _transaction: Transaction) -> None:
        self.append_many((_transaction,))

    def append_many(self, _transactions: Iterable[Transaction]) -> None:
        with self._paths._transactions.open("a", encoding="utf-8", newline="\n") as _stream:
            for _transaction in _transactions:
                _stream.write(json.dumps(_transaction.to_dict(), ensure_ascii=False, separators=(",", ":")))
                _stream.write("\n")
            _stream.flush()
            os.fsync(_stream.fileno())

    def next_id(self) -> str:
        _largest = 0
        for _transaction in self.iter_transactions():
            if _transaction.id.startswith("TX-") and _transaction.id[3:].isdigit():
                _largest = max(_largest, int(_transaction.id[3:]))
        return f"TX-{_largest + 1:06d}"

    def get(self, _transaction_id: str) -> Transaction | None:
        for _transaction in self.iter_transactions():
            if _transaction.id == _transaction_id:
                return _transaction
        return None

    def replace(self, _transaction_id: str, _replacement: Transaction) -> bool:
        _replaced = False

        def _records() -> Iterator[dict[str, Any]]:
            nonlocal _replaced
            for _transaction in self.iter_transactions():
                if _transaction.id == _transaction_id:
                    _replaced = True
                    yield _replacement.to_dict()
                else:
                    yield _transaction.to_dict()

        _atomic_write_jsonl(self._paths._transactions, _records())
        return _replaced

    def delete(self, _transaction_id: str) -> bool:
        _deleted = False

        def _records() -> Iterator[dict[str, Any]]:
            nonlocal _deleted
            for _transaction in self.iter_transactions():
                if _transaction.id == _transaction_id:
                    _deleted = True
                    continue
                yield _transaction.to_dict()

        _atomic_write_jsonl(self._paths._transactions, _records())
        return _deleted


class CategoryStore:
    def __init__(self, _paths: DataPaths) -> None:
        self._paths = _paths

    def list(self) -> list[str]:
        return sorted({str(_record["name"]) for _record in _iter_json_records(self._paths._categories)})

    def contains(self, _name: str) -> bool:
        return _name in set(self.list())

    def add(self, _name: str) -> bool:
        if self.contains(_name):
            return False
        with self._paths._categories.open("a", encoding="utf-8", newline="\n") as _stream:
            _stream.write(json.dumps({"name": _name}, ensure_ascii=False, separators=(",", ":")) + "\n")
            _stream.flush()
            os.fsync(_stream.fileno())
        return True

    def remove(self, _name: str) -> bool:
        _removed = False

        def _records() -> Iterator[dict[str, Any]]:
            nonlocal _removed
            for _record in _iter_json_records(self._paths._categories):
                if _record["name"] == _name:
                    _removed = True
                    continue
                yield _record

        _atomic_write_jsonl(self._paths._categories, _records())
        return _removed


class BudgetStore:
    def __init__(self, _paths: DataPaths) -> None:
        self._paths = _paths

    def get(self, _month: str) -> int | None:
        _amount: int | None = None
        for _record in _iter_json_records(self._paths._budgets):
            if _record["month"] == _month:
                _amount = int(_record["amount"])
        return _amount

    def set(self, _month: str, _amount: int) -> None:
        _found = False

        def _records() -> Iterator[dict[str, Any]]:
            nonlocal _found
            for _record in _iter_json_records(self._paths._budgets):
                if _record["month"] == _month:
                    if not _found:
                        yield {"month": _month, "amount": _amount}
                        _found = True
                    continue
                yield _record
            if not _found:
                yield {"month": _month, "amount": _amount}

        _atomic_write_jsonl(self._paths._budgets, _records())


class RecurringRepository:
    def __init__(self, _paths: DataPaths) -> None:
        self._paths = _paths

    def iter_rules(self) -> Iterator[RecurringRule]:
        for _record in _iter_json_records(self._paths._recurrences):
            yield RecurringRule.from_dict(_record)

    def append(self, _rule: RecurringRule) -> None:
        with self._paths._recurrences.open("a", encoding="utf-8", newline="\n") as _stream:
            _stream.write(json.dumps(_rule.to_dict(), ensure_ascii=False, separators=(",", ":")))
            _stream.write("\n")
            _stream.flush()
            os.fsync(_stream.fileno())

    def next_id(self) -> str:
        _largest = 0
        for _rule in self.iter_rules():
            if _rule.id.startswith("RC-") and _rule.id[3:].isdigit():
                _largest = max(_largest, int(_rule.id[3:]))
        return f"RC-{_largest + 1:06d}"


class BackupStore:
    def __init__(self, _paths: DataPaths) -> None:
        self._paths = _paths

    def create(self) -> tuple[Path, ...]:
        _backup_directory = self._paths._data_dir / "backups"
        _backup_directory.mkdir(parents=True, exist_ok=True)
        _timestamp = datetime.now().strftime("%Y%m%d-%H%M%S-%f")
        _backups: list[Path] = []
        for _source in self._paths.data_files():
            _target = _backup_directory / f"{_source.stem}-{_timestamp}{_source.suffix}"
            shutil.copy2(_source, _target)
            _backups.append(_target)
        return tuple(_backups)
