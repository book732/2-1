# 개인 가계부 CLI

Python 3.10 이상과 표준 라이브러리만 사용하는 가계부 명령줄 프로그램입니다.

## 실행

```powershell
python -m budget_app --help
python -m budget_app --data-dir ./data category add --name food
python -m budget_app --data-dir ./data add
python -m budget_app --data-dir ./data list --limit 3
```

`--data-dir`을 생략하면 현재 경로의 `./data`를 사용합니다. 데이터 디렉터리에는 아래 JSONL 파일이 생성됩니다.

- `transactions.jsonl`: 거래 데이터
- `categories.jsonl`: 등록 카테고리
- `budgets.jsonl`: 월별 예산

거래 목록과 검색 결과는 최신 저장 순서로 출력하며, JSONL 레코드를 역방향으로 스트리밍합니다.

## 명령

```text
add
list --limit N
search [--from YYYY-MM-DD] [--to YYYY-MM-DD] [--category NAME] [--type income|expense] [--q TEXT] [--tag TAG]
summary --month YYYY-MM [--top N]
budget set --month YYYY-MM --amount AMOUNT
category add [--name NAME]
category list
category remove [--name NAME]
update --id ID [--date YYYY-MM-DD] [--type income|expense] [--category NAME] [--amount AMOUNT] [--memo TEXT] [--tags TAG1,TAG2]
delete --id ID
import --from INPUT.csv
export --out OUTPUT.csv (--month YYYY-MM | --from YYYY-MM-DD --to YYYY-MM-DD)
```

`add`는 필수 입력을 대화형으로 받습니다. `update`는 수정 옵션을 생략하면 각 필드를 대화형으로 선택 수정합니다. `category remove`는 해당 카테고리를 참조하는 거래가 있으면 삭제를 거부합니다.

## CSV 스키마

입력·출력 CSV는 UTF-8 인코딩과 아래 헤더를 사용합니다.

| column | required | format |
| --- | --- | --- |
| date | Y | YYYY-MM-DD |
| type | Y | income / expense |
| category | Y | 등록된 카테고리 |
| amount | Y | 양의 정수 |
| memo | N | 문자열 |
| tags | N | 쉼표로 구분한 문자열 |

가져오기 전에 CSV의 카테고리를 `category add`로 등록해야 합니다. 잘못된 행은 건너뛰고 최종 처리 건수를 출력합니다.
