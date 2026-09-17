from __future__ import annotations

from .models import MonthlySummary, RecurringRule, Transaction


def _line(_values: tuple[str, ...], _widths: tuple[int, ...]) -> str:
    return " | ".join(_value[:_width].ljust(_width) for _value, _width in zip(_values, _widths))


def transaction_header() -> tuple[str, str]:
    _widths = (10, 10, 7, 14, 12, 20, 16)
    return _line(("ID", "DATE", "TYPE", "CATEGORY", "AMOUNT", "MEMO", "TAGS"), _widths), "-+-".join("-" * _width for _width in _widths)


def format_transaction(_transaction: Transaction) -> str:
    return _line(
        (
            _transaction.id,
            _transaction.date,
            _transaction.type,
            _transaction.category,
            f"{_transaction.amount:,}",
            _transaction.memo,
            ",".join(_transaction.tags),
        ),
        (10, 10, 7, 14, 12, 20, 16),
    )


def recurring_header() -> tuple[str, str]:
    _widths = (10, 7, 14, 12, 5, 20, 16)
    return _line(("RULE ID", "TYPE", "CATEGORY", "AMOUNT", "DAY", "MEMO", "TAGS"), _widths), "-+-".join("-" * _width for _width in _widths)


def format_recurring_rule(_rule: RecurringRule) -> str:
    return _line(
        (_rule.id, _rule.type, _rule.category, f"{_rule.amount:,}", str(_rule.day), _rule.memo, ",".join(_rule.tags)),
        (10, 7, 14, 12, 5, 20, 16),
    )


def format_summary(_summary: MonthlySummary, _top: int) -> tuple[str, ...]:
    _lines = ["항목             | 금액", "-----------------+----------------"]
    _lines.extend(
        (
            f"총 수입          | {_summary.income:,} 원",
            f"총 지출          | {_summary.expense:,} 원",
            f"잔액             | {_summary.balance:,} 원",
        )
    )
    if _summary.budget is not None:
        _lines.append(f"예산             | {_summary.budget:,} 원 (사용 {_summary.budget_ratio * 100:.1f}%)")
        if _summary.expense > _summary.budget:
            _lines.append(f"예산 초과        | {_summary.expense - _summary.budget:,} 원")
    _lines.append("지출 TOP " + str(_top))
    for _index, (_category, _amount) in enumerate(
        sorted(_summary.category_expenses.items(), key=lambda _item: (-_item[1], _item[0]))[:_top], start=1
    ):
        _lines.append(f"{_index}. {_category:<14} | {_amount:,} 원")
    return tuple(_lines)
