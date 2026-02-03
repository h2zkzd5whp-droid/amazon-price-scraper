"""Amazon Price Tracker API"""

from fastapi import FastAPI, HTTPException, Query, Request
from fastapi.responses import JSONResponse
from scraper import get_db_connection
from slowapi import Limiter, _rate_limit_exceeded_handler
from slowapi.util import get_remote_address
from slowapi.errors import RateLimitExceeded
import sqlite3
import re

# Rate limiter 설정
limiter = Limiter(key_func=get_remote_address)
app = FastAPI(title="Amazon Price Tracker API")
app.state.limiter = limiter
app.add_exception_handler(RateLimitExceeded, _rate_limit_exceeded_handler)


def dict_factory(cursor, row):
    """sqlite row를 dict로 변환."""
    return {col[0]: row[idx] for idx, col in enumerate(cursor.description)}


def parse_price(price_str: str) -> float | None:
    """가격 문자열에서 숫자 추출."""
    if not price_str or price_str == "N/A":
        return None
    numbers = re.findall(r'[\d.]+', price_str.replace(',', ''))
    return float(numbers[0]) if numbers else None


@app.get("/")
@limiter.limit("60/minute")
def home(request: Request):
    """API health check."""
    return {"message": "Amazon Price Tracker API"}


@app.get("/products")
@limiter.limit("30/minute")
def get_keywords(request: Request):
    """Get all unique search keywords with product counts."""
    with get_db_connection() as conn:
        cursor = conn.cursor()
        cursor.execute("""
            SELECT keyword, COUNT(*) as count
            FROM products
            GROUP BY keyword
        """)
        rows = cursor.fetchall()
    return {"keywords": [{"keyword": row[0], "count": row[1]} for row in rows]}


@app.get("/products/{keyword}")
@limiter.limit("30/minute")
def get_products_by_keyword(
    request: Request,
    keyword: str,
    page: int = Query(1, ge=1, description="페이지 번호"),
    limit: int = Query(20, ge=1, le=100, description="페이지당 항목 수"),
    sort_by: str = Query("created_at", description="정렬 기준: price, rating, review_count, created_at"),
    order: str = Query("desc", description="정렬 순서: asc, desc"),
    min_price: float | None = Query(None, ge=0, description="최소 가격"),
    max_price: float | None = Query(None, ge=0, description="최대 가격"),
):
    """Get products for a keyword with pagination, sorting, filtering."""

    # 정렬 필드 검증
    valid_sort_fields = {"price", "rating", "review_count", "created_at", "title"}
    if sort_by not in valid_sort_fields:
        raise HTTPException(status_code=400, detail=f"Invalid sort_by. Use: {valid_sort_fields}")

    order = order.lower()
    if order not in {"asc", "desc"}:
        raise HTTPException(status_code=400, detail="Invalid order. Use: asc, desc")

    with get_db_connection() as conn:
        conn.row_factory = dict_factory
        cursor = conn.cursor()

        # 전체 개수 조회
        cursor.execute("SELECT COUNT(*) FROM products WHERE keyword = ?", (keyword,))
        total = cursor.fetchone()["COUNT(*)"]

        if total == 0:
            raise HTTPException(status_code=404, detail=f"No products found for keyword: {keyword}")

        # 메인 쿼리
        offset = (page - 1) * limit
        cursor.execute(
            f"""SELECT title, price, rating, review_count, sold_count, product_url, image_url, created_at
                FROM products
                WHERE keyword = ?
                ORDER BY {sort_by} {order}
                LIMIT ? OFFSET ?""",
            (keyword, limit, offset)
        )
        products = cursor.fetchall()

    # 가격 필터링 (문자열이라 Python에서 처리)
    if min_price is not None or max_price is not None:
        filtered = []
        for p in products:
            price_val = parse_price(p["price"])
            if price_val is None:
                continue
            if min_price is not None and price_val < min_price:
                continue
            if max_price is not None and price_val > max_price:
                continue
            filtered.append(p)
        products = filtered

    total_pages = (total + limit - 1) // limit

    return {
        "keyword": keyword,
        "pagination": {
            "page": page,
            "limit": limit,
            "total": total,
            "total_pages": total_pages,
            "has_next": page < total_pages,
            "has_prev": page > 1,
        },
        "sort": {"by": sort_by, "order": order},
        "count": len(products),
        "products": products,
    }


@app.get("/products/{keyword}/stats")
@limiter.limit("30/minute")
def get_keyword_stats(request: Request, keyword: str):
    """Get price statistics for a keyword."""
    with get_db_connection() as conn:
        conn.row_factory = dict_factory
        cursor = conn.cursor()
        cursor.execute(
            "SELECT price FROM products WHERE keyword = ?",
            (keyword,)
        )
        rows = cursor.fetchall()

    if not rows:
        raise HTTPException(status_code=404, detail=f"No products found for keyword: {keyword}")

    prices = [parse_price(r["price"]) for r in rows]
    prices = [p for p in prices if p is not None]

    if not prices:
        return {"keyword": keyword, "stats": None, "message": "No valid prices found"}

    return {
        "keyword": keyword,
        "stats": {
            "count": len(prices),
            "min": min(prices),
            "max": max(prices),
            "avg": round(sum(prices) / len(prices), 2),
        }
    }
