from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class Transaction:
    id: str
    type: str
    date: str
    amount: int
    category: str
    memo: str
    tags: tuple[str, ...]
    recurrence_id: str | None = None

    def to_dict(self) -> dict[str, object]:
        return {
            "id": self.id,
            "type": self.type,
            "date": self.date,
            "amount": self.amount,
            "category": self.category,
            "memo": self.memo,
            "tags": list(self.tags),
            "recurrence_id": self.recurrence_id,
        }

    @classmethod
    def from_dict(cls, _data: dict[str, object]) -> "Transaction":
        return cls(
            id=str(_data["id"]),
            type=str(_data["type"]),
            date=str(_data["date"]),
            amount=int(_data["amount"]),
            category=str(_data["category"]),
            memo=str(_data.get("memo", "")),
            tags=tuple(str(_tag) for _tag in _data.get("tags", [])),
            recurrence_id=str(_data["recurrence_id"]) if _data.get("recurrence_id") else None,
        )


@dataclass(frozen=True, slots=True)
class RecurringRule:
    id: str
    type: str
    category: str
    amount: int
    day: int
    memo: str
    tags: tuple[str, ...]

    def to_dict(self) -> dict[str, object]:
        return {
            "id": self.id,
            "type": self.type,
            "category": self.category,
            "amount": self.amount,
            "day": self.day,
            "memo": self.memo,
            "tags": list(self.tags),
        }

    @classmethod
    def from_dict(cls, _data: dict[str, object]) -> "RecurringRule":
        return cls(
            id=str(_data["id"]),
            type=str(_data["type"]),
            category=str(_data["category"]),
            amount=int(_data["amount"]),
            day=int(_data["day"]),
            memo=str(_data.get("memo", "")),
            tags=tuple(str(_tag) for _tag in _data.get("tags", [])),
        )


@dataclass(frozen=True, slots=True)
class MonthlySummary:
    income: int
    expense: int
    category_expenses: dict[str, int]
    budget: int | None

    @property
    def balance(self) -> int:
        return self.income - self.expense

    @property
    def budget_ratio(self) -> float | None:
        if self.budget is None:
            return None
        return self.expense / self.budget if self.budget else 0.0
