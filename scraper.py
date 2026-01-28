from selenium import webdriver
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from webdriver_manager.chrome import ChromeDriverManager
import sqlite3
from datetime import datetime
import sys
import time

keyword = sys.argv[1] if len(sys.argv) > 1 else "wireless mouse"

options = Options()
options.add_argument("--headless")
options.add_argument("--no-sandbox")
options.add_argument("--lang=en-US")
options.add_argument("user-agent=Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36")

driver = webdriver.Chrome(service=Service(ChromeDriverManager().install()), options=options)

conn = sqlite3.connect("products.db")
cursor = conn.cursor()
cursor.execute("""
    CREATE TABLE IF NOT EXISTS products (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        title TEXT,
        price TEXT,
        keyword TEXT,
        scraped_at TIMESTAMP
    )
""")

url = f"https://www.amazon.com/s?k={keyword.replace(' ', '+')}"
driver.get(url)

wait = WebDriverWait(driver, 10)
wait.until(EC.presence_of_all_elements_located((By.CSS_SELECTOR, "[data-component-type='s-search-result']")))
time.sleep(3)

products = driver.find_elements(By.CSS_SELECTOR, "[data-component-type='s-search-result']")

print(f"검색어: {keyword}")
print(f"상품 수: {len(products)}")
print("-" * 50)

count = 0
for product in products[:10]:
    try:
        title = product.find_element(By.CSS_SELECTOR, "h2 span").text
        price = product.find_element(By.CSS_SELECTOR, "span.a-offscreen").get_attribute("innerHTML")
        cursor.execute("INSERT INTO products (title, price, keyword, scraped_at) VALUES (?, ?, ?, ?)", 
                      (title, price, keyword, datetime.now()))
        print(f"{title[:50]}... - {price}")
        count += 1
    except:
        continue

conn.commit()
conn.close()
driver.quit()

print("-" * 50)
print(f"완료! {count}개 저장됨")