# Amazon Price Tracker

Amazon 검색 결과를 스크래핑하여 SQLite/CSV로 저장하고, REST API로 조회하는 도구.

## 설치

```bash
pip install selenium webdriver-manager fastapi uvicorn slowapi
```

## 사용법

### 스크래핑

```bash
python scraper.py "검색어"
```

```bash
# 예시
python scraper.py "wireless mouse"
python scraper.py "sata ssd"
```

### API 서버

```bash
uvicorn api:app --reload
```

## API 엔드포인트

| Method | Endpoint | 설명 |
|--------|----------|------|
| GET | `/` | Health check |
| GET | `/products` | 키워드 목록 + 개수 |
| GET | `/products/{keyword}` | 제품 조회 (페이지네이션/정렬/필터) |
| GET | `/products/{keyword}/stats` | 가격 통계 |

### 쿼리 파라미터

```
GET /products/{keyword}?page=1&limit=20&sort_by=price&order=asc&min_price=10&max_price=100
```

| 파라미터 | 기본값 | 설명 |
|----------|--------|------|
| `page` | 1 | 페이지 번호 |
| `limit` | 20 | 페이지당 항목 (최대 100) |
| `sort_by` | created_at | 정렬 기준: price, rating, review_count, created_at, title |
| `order` | desc | 정렬 순서: asc, desc |
| `min_price` | - | 최소 가격 필터 |
| `max_price` | - | 최대 가격 필터 |

## 환경변수

| 변수 | 기본값 | 설명 |
|------|--------|------|
| `SCRAPER_OUTPUT_DIR` | output | CSV 출력 폴더 |
| `SCRAPER_DB_PATH` | products.db | SQLite DB 경로 |
| `SCRAPER_MAX_PRODUCTS` | 30 | 최대 스크래핑 수 |
| `SCRAPER_TIMEOUT` | 20 | 페이지 로드 타임아웃 (초) |
| `SCRAPER_HEADLESS` | true | 헤드리스 모드 |
| `KRW_USD_RATE` | 1450 | 원/달러 환율 |

```bash
# 브라우저 창 띄우고 실행
set SCRAPER_HEADLESS=false
python scraper.py "keyboard"
```

## 출력

- `products.db` - SQLite 데이터베이스
- `output/{keyword}_{timestamp}.csv` - CSV 파일
- `scraper.log` - 로그 파일

## Rate Limit

API는 IP당 30 req/min 제한.
