from __future__ import annotations

import argparse
from collections.abc import Sequence
from pathlib import Path

from .models import MonthlySummary, Transaction
from .service import BudgetService, NotFoundError, ValidationError


def _parse_amount(_value: str) -> int:
    try:
        return int(_value)
    except ValueError as _error:
        raise ValidationError("금액은 정수로 입력해야 합니다.") from _error


def _parse_amount_argument(_value: str) -> int:
    try:
        return _parse_amount(_value)
    except ValidationError as _error:
        raise argparse.ArgumentTypeError(str(_error)) from _error


def _build_parser() -> argparse.ArgumentParser:
    _parser = argparse.ArgumentParser(prog="python -m budget_app", description="개인 가계부 CLI")
    _parser.add_argument("--data-dir", default="data", type=Path, help="데이터 디렉터리 (기본값: ./data)")
    _commands = _parser.add_subparsers(dest="command", required=True)

    _commands.add_parser("add", help="대화형으로 거래를 추가합니다.")
    _list = _commands.add_parser("list", help="최신 거래를 조회합니다.")
    _list.add_argument("--limit", type=int, help="출력할 최대 거래 수")

    _search = _commands.add_parser("search", help="거래를 검색합니다.")
    _search.add_argument("--from", dest="from_date", help="시작일 (YYYY-MM-DD)")
    _search.add_argument("--to", dest="to_date", help="종료일 (YYYY-MM-DD)")
    _search.add_argument("--category", help="카테고리")
    _search.add_argument("--type", choices=("income", "expense"), help="거래 유형")
    _search.add_argument("--q", dest="query", help="메모 키워드")
    _search.add_argument("--tag", help="태그")

    _summary = _commands.add_parser("summary", help="월별 수입과 지출을 집계합니다.")
    _summary.add_argument("--month", required=True, help="대상 월 (YYYY-MM)")
    _summary.add_argument("--top", type=int, default=3, help="지출 카테고리 상위 개수")

    _budget = _commands.add_parser("budget", help="월 예산을 관리합니다.")
    _budget_commands = _budget.add_subparsers(dest="budget_command", required=True)
    _budget_set = _budget_commands.add_parser("set", help="월 예산을 설정합니다.")
    _budget_set.add_argument("--month", required=True, help="대상 월 (YYYY-MM)")
    _budget_set.add_argument("--amount", required=True, type=_parse_amount_argument, help="예산 금액")

    _category = _commands.add_parser("category", help="카테고리를 관리합니다.")
    _category_commands = _category.add_subparsers(dest="category_command", required=True)
    _category_add = _category_commands.add_parser("add", help="카테고리를 추가합니다.")
    _category_add.add_argument("--name", help="카테고리 이름")
    _category_commands.add_parser("list", help="카테고리를 조회합니다.")
    _category_remove = _category_commands.add_parser("remove", help="카테고리를 삭제합니다.")
    _category_remove.add_argument("--name", help="카테고리 이름")

    _update = _commands.add_parser("update", help="거래를 수정합니다.")
    _update.add_argument("--id", required=True, help="거래 ID")
    _update.add_argument("--date", help="날짜 (YYYY-MM-DD)")
    _update.add_argument("--type", choices=("income", "expense"), help="거래 유형")
    _update.add_argument("--category", help="카테고리")
    _update.add_argument("--amount", type=_parse_amount_argument, help="금액")
    _update.add_argument("--memo", help="메모")
    _update.add_argument("--tags", help="쉼표로 구분한 태그")

    _delete = _commands.add_parser("delete", help="거래를 삭제합니다.")
    _delete.add_argument("--id", required=True, help="거래 ID")

    _import = _commands.add_parser("import", help="CSV 거래를 가져옵니다.")
    _import.add_argument("--from", dest="source", required=True, type=Path, help="입력 CSV 경로")
    _export = _commands.add_parser("export", help="거래를 CSV로 내보냅니다.")
    _export.add_argument("--out", required=True, type=Path, help="출력 CSV 경로")
    _export.add_argument("--month", help="대상 월 (YYYY-MM)")
    _export.add_argument("--from", dest="from_date", help="시작일 (YYYY-MM-DD)")
    _export.add_argument("--to", dest="to_date", help="종료일 (YYYY-MM-DD)")
    return _parser


def _prompt(_label: str) -> str:
    return input(f"{_label}: ").strip()


def _print_transaction(_transaction: Transaction) -> None:
    _tags = f" | {','.join(_transaction.tags)}" if _transaction.tags else ""
    print(
        f"{_transaction.id} | {_transaction.date} | {_transaction.type} | "
        f"{_transaction.category} | {_transaction.amount} | {_transaction.memo}{_tags}"
    )


def _print_summary(_summary: MonthlySummary, _top: int) -> None:
    if _top <= 0:
        raise ValidationError("--top은 1 이상의 정수여야 합니다.")
    print(f"총 수입 : {_summary.income} 원")
    print(f"총 지출 : {_summary.expense} 원")
    print(f"잔액 : {_summary.balance} 원")
    if _summary.budget is not None:
        print(f"예산 : {_summary.budget} 원 (사용 {_summary.budget_ratio * 100:.1f}%)")
        if _summary.expense > _summary.budget:
            print(f"[경고] 예산 초과 : {_summary.expense - _summary.budget} 원")
    print(f"지출 TOP {_top}")
    for _index, (_category, _amount) in enumerate(
        sorted(_summary.category_expenses.items(), key=lambda _item: (-_item[1], _item[0]))[:_top], start=1
    ):
        print(f"{_index}) {_category} {_amount} 원")


def _interactive_update(_service: BudgetService, _transaction_id: str) -> dict[str, object]:
    _current = _service.get_transaction(_transaction_id)
    if _current is None:
        raise NotFoundError(f"거래를 찾을 수 없습니다: {_transaction_id}")
    _changes: dict[str, object] = {}
    for _field, _label, _value in (
        ("date", "날짜 (YYYY-MM-DD)", _current.date),
        ("type", "유형 (income/expense)", _current.type),
        ("category", "카테고리", _current.category),
        ("amount", "금액", str(_current.amount)),
        ("memo", "메모", _current.memo),
        ("tags", "태그 (쉼표 구분)", ",".join(_current.tags)),
    ):
        _input = input(f"{_label} [{_value}]: ").strip()
        if _input:
            _changes[_field] = _parse_amount(_input) if _field == "amount" else _input
    return _changes


def _run(_arguments: argparse.Namespace, _service: BudgetService) -> None:
    if _arguments.command == "add":
        _transaction = _service.add_transaction(
            _date=_prompt("날짜 (YYYY-MM-DD)"),
            _type=_prompt("유형 (income/expense)"),
            _category=_prompt("카테고리"),
            _amount=_parse_amount(_prompt("금액 (원)")),
            _memo=_prompt("메모 (선택)"),
            _tags=_prompt("태그 (쉼표로 구분, 선택)"),
        )
        print(f"[저장 완료] id={_transaction.id}")
    elif _arguments.command == "list":
        for _transaction in _service.list_transactions(_arguments.limit):
            _print_transaction(_transaction)
    elif _arguments.command == "search":
        for _transaction in _service.search_transactions(
            _from=_arguments.from_date,
            _to=_arguments.to_date,
            _category=_arguments.category,
            _type=_arguments.type,
            _query=_arguments.query,
            _tag=_arguments.tag,
        ):
            _print_transaction(_transaction)
    elif _arguments.command == "summary":
        _print_summary(_service.summarize(_arguments.month), _arguments.top)
    elif _arguments.command == "budget":
        _service.set_budget(_arguments.month, _arguments.amount)
        print(f"[저장 완료] {_arguments.month} 예산 {_arguments.amount} 원")
    elif _arguments.command == "category":
        if _arguments.category_command == "add":
            _name = _arguments.name or _prompt("카테고리명")
            if _service.add_category(_name):
                print(f"[저장 완료] category={_name}")
            else:
                print(f"[안내] 이미 등록된 카테고리입니다: {_name}")
        elif _arguments.category_command == "list":
            for _name in _service.list_categories():
                print(f"- {_name}")
        else:
            _name = _arguments.name or _prompt("카테고리명")
            _service.remove_category(_name)
            print(f"[삭제 완료] category={_name}")
    elif _arguments.command == "update":
        _changes = {
            _field: getattr(_arguments, _field)
            for _field in ("date", "type", "category", "amount", "memo", "tags")
            if getattr(_arguments, _field) is not None
        }
        if not _changes:
            _changes = _interactive_update(_service, _arguments.id)
        _transaction = _service.update_transaction(_arguments.id, **_changes)
        print(f"[수정 완료] id={_transaction.id}")
    elif _arguments.command == "delete":
        _service.delete_transaction(_arguments.id)
        print(f"[삭제 완료] id={_arguments.id}")
    elif _arguments.command == "import":
        _imported, _skipped = _service.import_csv(_arguments.source)
        print(f"[완료] imported={_imported}, skipped={_skipped}")
    elif _arguments.command == "export":
        _count = _service.export_csv(
            _output=_arguments.out,
            _month=_arguments.month,
            _from=_arguments.from_date,
            _to=_arguments.to_date,
        )
        print(f"[완료] {_arguments.out} ({_count} records)")


def main(_argv: Sequence[str] | None = None) -> int:
    _parser = _build_parser()
    _arguments = _parser.parse_args(_argv)
    _service: BudgetService | None = None
    try:
        _service = BudgetService(_arguments.data_dir)
        _run(_arguments, _service)
    except KeyboardInterrupt:
        print("[취소] 입력이 취소되었습니다.")
        return 130
    except (OSError, ValueError, ValidationError, NotFoundError) as _error:
        print(f"[오류] {_error}")
        return 2
    finally:
        if _service is not None:
            _service.close()
    return 0
