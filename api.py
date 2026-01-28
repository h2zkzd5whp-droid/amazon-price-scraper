from fastapi import FastAPI
import sqlite3

app = FastAPI()

@app.get("/")
def home():
    return {"message": "Amazon Price Tracker API"}

@app.get("/products")
def get_keywords():
    conn = sqlite3.connect("products.db")
    cursor = conn.cursor()
    cursor.execute("SELECT DISTINCT keyword FROM products")
    rows = cursor.fetchall()
    conn.close()
    
    keywords = [row[0] for row in rows]
    return {"keywords": keywords}

@app.get("/products/{keyword}")
def get_products_by_keyword(keyword: str):
    conn = sqlite3.connect("products.db")
    cursor = conn.cursor()
    cursor.execute("SELECT title, price, keyword, scraped_at FROM products WHERE keyword = ? ORDER BY scraped_at DESC", (keyword,))
    rows = cursor.fetchall()
    conn.close()
    
    products = []
    for row in rows:
        products.append({
            "title": row[0],
            "price": row[1],
            "keyword": row[2],
            "scraped_at": row[3]
        })
    return {"keyword": keyword, "count": len(products), "products": products}