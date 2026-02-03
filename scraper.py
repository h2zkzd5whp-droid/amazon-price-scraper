"""Amazon Product Scraper - 검색 결과를 SQLite/CSV로 저장"""

from selenium import webdriver
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.common.exceptions import TimeoutException, NoSuchElementException, WebDriverException
from webdriver_manager.chrome import ChromeDriverManager
import sqlite3
from datetime import datetime
from contextlib import contextmanager
import sys
import time
import csv
import os
import re
import random
import logging

# 로깅 설정
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    handlers=[
        logging.FileHandler("scraper.log", encoding="utf-8"),
        logging.StreamHandler()
    ]
)
logger = logging.getLogger(__name__)

# 환경변수 기반 설정
CONFIG = {
    "output_dir": os.getenv("SCRAPER_OUTPUT_DIR", "output"),
    "db_path": os.getenv("SCRAPER_DB_PATH", "products.db"),
    "max_products": int(os.getenv("SCRAPER_MAX_PRODUCTS", "30")),
    "timeout": int(os.getenv("SCRAPER_TIMEOUT", "20")),
    "headless": os.getenv("SCRAPER_HEADLESS", "true").lower() == "true",
    "user_agents": [
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/121.0.0.0 Safari/537.36",
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/120.0.0.0 Safari/537.36",
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 Chrome/121.0.0.0 Safari/537.36",
    ],
}


@contextmanager
def get_db_connection(db_path: str = CONFIG["db_path"]):
    """DB 연결 context manager."""
    conn = sqlite3.connect(db_path)
    try:
        yield conn
    finally:
        conn.close()


def init_db():
    """DB 테이블 생성."""
    with get_db_connection() as conn:
        conn.execute("""
            CREATE TABLE IF NOT EXISTS products (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                title TEXT,
                price TEXT,
                rating TEXT,
                review_count TEXT,
                sold_count TEXT,
                product_url TEXT UNIQUE,
                image_url TEXT,
                keyword TEXT,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        """)
        conn.commit()


def format_price_usd(price_text: str) -> str:
    """가격을 USD로 변환. 원화면 환율 적용."""
    if not price_text or price_text == "N/A":
        return "N/A"

    # 통화 감지
    is_krw = "₩" in price_text or "KRW" in price_text.upper()
    is_usd = "$" in price_text

    numbers = re.findall(r'[\d,]+\.?\d*', price_text)
    if not numbers:
        return "N/A"

    try:
        price_val = float(numbers[0].replace(',', ''))

        # 원화 → 달러 변환
        if is_krw or (not is_usd and price_val > 500):  # 500 이상이면 원화로 추정
            krw_rate = float(os.getenv("KRW_USD_RATE", "1450"))
            price_val = price_val / krw_rate

        return f"${price_val:.2f} USD"
    except ValueError:
        return "N/A"


class AmazonScraper:
    """Amazon 제품 스크래퍼."""

    def __init__(self, keyword: str):
        self.keyword = keyword
        self.driver = None
        self.scraped_data = []

    def _create_driver(self) -> webdriver.Chrome:
        """Chrome 드라이버 생성."""
        options = Options()

        if CONFIG["headless"]:
            options.add_argument("--headless=new")

        options.add_argument("--no-sandbox")
        options.add_argument("--disable-blink-features=AutomationControlled")
        options.add_argument("--disable-dev-shm-usage")
        options.add_argument("--disable-infobars")
        options.add_argument("--disable-extensions")
        options.add_argument("--disable-gpu")
        options.add_argument("--lang=en-US")
        options.add_argument("--window-size=1920,1080")
        options.add_argument(f"user-agent={random.choice(CONFIG['user_agents'])}")
        options.add_experimental_option("excludeSwitches", ["enable-automation", "enable-logging"])
        options.add_experimental_option("useAutomationExtension", False)

        return webdriver.Chrome(
            service=Service(ChromeDriverManager().install()),
            options=options
        )

    def _random_delay(self, min_sec: float = 1, max_sec: float = 3):
        """랜덤 딜레이."""
        time.sleep(random.uniform(min_sec, max_sec))

    def _human_scroll(self):
        """스크롤 시뮬레이션."""
        for _ in range(3):
            self.driver.execute_script(f"window.scrollBy(0, {random.randint(300, 700)});")
            time.sleep(random.uniform(0.5, 1.5))

    def _is_blocked(self) -> bool:
        """차단 페이지 확인."""
        page_source = self.driver.page_source.lower()
        return any(x in page_source for x in ["sorry, something went wrong", "captcha", "robot"])

    def _extract_product_data(self, product) -> dict | None:
        """단일 제품 데이터 추출."""
        try:
            title = product.find_element(By.CSS_SELECTOR, "h2 span").text
        except NoSuchElementException:
            return None

        def safe_extract(selector: str, attr: str = "text") -> str:
            try:
                el = product.find_element(By.CSS_SELECTOR, selector)
                return el.get_attribute("innerHTML") if attr == "innerHTML" else el.text
            except NoSuchElementException:
                return "N/A"

        # 가격
        raw_price = safe_extract("span.a-offscreen", "innerHTML")
        price = format_price_usd(raw_price)

        # 평점
        rating = safe_extract("span.a-icon-alt", "innerHTML")

        # 리뷰 수
        review_count = "0"
        try:
            review_link = product.find_element(By.CSS_SELECTOR, "a[href*='customerReviews']")
            aria_label = review_link.get_attribute("aria-label")
            if aria_label:
                numbers = re.findall(r'[\d,]+', aria_label)
                if numbers:
                    review_count = numbers[0]
        except NoSuchElementException:
            pass

        # 판매량
        sold_count = "N/A"
        try:
            sold_el = product.find_element(By.CSS_SELECTOR, "span.a-size-base.a-color-secondary")
            if "bought" in sold_el.text.lower():
                sold_count = sold_el.text
        except NoSuchElementException:
            pass

        # URL (여러 셀렉터 시도)
        product_url = "N/A"
        url_selectors = [
            "h2 a",
            "a.a-link-normal.s-no-outline",
            "a.a-link-normal[href*='/dp/']",
            ".s-product-image-container a",
        ]
        for selector in url_selectors:
            try:
                el = product.find_element(By.CSS_SELECTOR, selector)
                href = el.get_attribute("href")
                if href and "/dp/" in href:
                    product_url = href.split("/ref=")[0]  # tracking param 제거
                    break
            except NoSuchElementException:
                continue

        # 이미지
        try:
            image_url = product.find_element(By.CSS_SELECTOR, "img.s-image").get_attribute("src")
        except NoSuchElementException:
            image_url = "N/A"

        return {
            "title": title,
            "price": price,
            "rating": rating,
            "review_count": review_count,
            "sold_count": sold_count,
            "product_url": product_url,
            "image_url": image_url,
            "keyword": self.keyword,
        }

    def scrape(self) -> list[dict]:
        """스크래핑 실행."""
        try:
            self.driver = self._create_driver()
            url = f"https://www.amazon.com/s?k={self.keyword.replace(' ', '+')}"

            logger.info("Connecting to Amazon...")
            self.driver.get("https://www.amazon.com")
            self._random_delay(2, 3)

            self.driver.get(url)
            self._random_delay(2, 3)
            self._human_scroll()

            wait = WebDriverWait(self.driver, CONFIG["timeout"])
            wait.until(EC.presence_of_all_elements_located(
                (By.CSS_SELECTOR, "[data-component-type='s-search-result']")
            ))
            products = self.driver.find_elements(
                By.CSS_SELECTOR, "[data-component-type='s-search-result']"
            )

            if not products:
                logger.warning("No products found.")
                return []

            logger.info(f"Search keyword: {self.keyword}")
            logger.info(f"Products found: {len(products)}")

            for product in products[:CONFIG["max_products"]]:
                data = self._extract_product_data(product)
                if data:
                    self.scraped_data.append(data)
                    logger.info(f"{data['title'][:50]}... | {data['price']}")

            return self.scraped_data

        except TimeoutException:
            if self._is_blocked():
                logger.error("Amazon blocked the request.")
            else:
                logger.error("Page load timeout.")
            return []

        except WebDriverException as e:
            logger.error(f"WebDriver error: {e}")
            return []

        finally:
            if self.driver:
                self.driver.quit()
                logger.debug("Driver closed.")


def save_to_db(data: list[dict]) -> int:
    """DB에 저장. 중복 제외하고 저장된 개수 반환."""
    saved = 0
    with get_db_connection() as conn:
        cursor = conn.cursor()
        for item in data:
            url = item["product_url"]

            # 유효한 URL인 경우만 중복 체크
            if url and url != "N/A":
                cursor.execute("SELECT 1 FROM products WHERE product_url = ?", (url,))
                if cursor.fetchone():
                    logger.debug(f"Duplicate skipped: {item['title'][:30]}...")
                    continue

            # N/A URL은 NULL로 저장 (UNIQUE 제약 우회)
            cursor.execute(
                """INSERT INTO products
                   (title, price, rating, review_count, sold_count, product_url, image_url, keyword)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?)""",
                (item["title"], item["price"], item["rating"], item["review_count"],
                 item["sold_count"], url if url != "N/A" else None, item["image_url"], item["keyword"])
            )
            saved += 1
        conn.commit()
    return saved


def save_to_csv(data: list[dict], keyword: str) -> str:
    """CSV로 내보내기. 파일 경로 반환."""
    os.makedirs(CONFIG["output_dir"], exist_ok=True)

    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    safe_keyword = keyword.replace(" ", "_").replace("/", "_")
    filepath = os.path.join(CONFIG["output_dir"], f"{safe_keyword}_{timestamp}.csv")

    headers = ["title", "price", "rating", "review_count", "sold_count", "product_url", "image_url", "keyword"]
    with open(filepath, mode="w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=headers)
        writer.writeheader()
        writer.writerows(data)

    logger.info(f"CSV exported: {filepath}")
    return filepath


def main():
    """메인 함수."""
    keyword = sys.argv[1] if len(sys.argv) > 1 else "wireless mouse"

    logger.info(f"Starting scraper (headless={CONFIG['headless']})")
    init_db()

    scraper = AmazonScraper(keyword)
    data = scraper.scrape()

    if data:
        saved = save_to_db(data)
        save_to_csv(data, keyword)
        logger.info(f"Done! {saved} new products saved ({len(data) - saved} duplicates skipped).")
    else:
        logger.warning("No data scraped.")


if __name__ == "__main__":
    main()
