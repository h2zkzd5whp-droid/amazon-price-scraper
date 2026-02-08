"""Amazon Scraper Dashboard - Streamlit UI"""

import streamlit as st
import pandas as pd
import sqlite3
import re
from scraper import init_db, save_to_db, AmazonScraper, CONFIG

st.set_page_config(page_title="Amazon Scraper", page_icon="🛒", layout="wide")


@st.cache_resource
def get_connection():
    return sqlite3.connect(CONFIG["db_path"], check_same_thread=False)


def load_data(keyword_filter: str = "") -> pd.DataFrame:
    conn = get_connection()
    query = "SELECT * FROM products"
    params = ()
    if keyword_filter:
        query += " WHERE keyword = ?"
        params = (keyword_filter,)
    query += " ORDER BY created_at DESC"
    return pd.read_sql_query(query, conn, params=params)


def parse_price(price_str: str) -> float | None:
    """Extract numeric value from price string."""
    if not price_str or price_str == "N/A":
        return None
    numbers = re.findall(r'[\d,]+\.?\d*', price_str)
    if numbers:
        try:
            return float(numbers[0].replace(",", ""))
        except ValueError:
            return None
    return None


def parse_rating(rating_str: str) -> float | None:
    """Extract numeric value from rating string."""
    if not rating_str or rating_str == "N/A":
        return None
    numbers = re.findall(r'(\d+\.?\d*)\s*out of', rating_str)
    if numbers:
        try:
            return float(numbers[0])
        except ValueError:
            return None
    return None


# --- Sidebar ---
st.sidebar.title("Amazon Scraper")

st.sidebar.markdown("### New Scrape")
keyword = st.sidebar.text_input("Search Keyword", placeholder="e.g. wireless mouse")
max_products = st.sidebar.slider("Max Products", 10, 200, 30, step=10)
max_pages = st.sidebar.slider("Max Pages", 1, 20, 3)

if st.sidebar.button("Start Scraping", type="primary", use_container_width=True):
    if not keyword.strip():
        st.sidebar.error("Please enter a keyword.")
    else:
        CONFIG["max_products"] = max_products
        CONFIG["max_pages"] = max_pages
        with st.spinner(f"Scraping '{keyword}'..."):
            init_db()
            scraper = AmazonScraper(keyword.strip())
            data = scraper.scrape()
            if data:
                saved = save_to_db(data)
                st.sidebar.success(f"{saved} saved! ({len(data) - saved} duplicates)")
            else:
                st.sidebar.warning("No results. Blocked or check keyword.")
        st.rerun()

st.sidebar.markdown("---")

# Keyword filter
init_db()
conn = get_connection()
keywords = pd.read_sql_query("SELECT DISTINCT keyword FROM products", conn)["keyword"].tolist()

selected_keyword = st.sidebar.selectbox(
    "Keyword Filter",
    options=["All"] + keywords,
)
filter_kw = "" if selected_keyword == "All" else selected_keyword

# --- Load data ---
df = load_data(filter_kw)

# --- Main area ---
st.title("Amazon Product Dashboard")

if df.empty:
    st.info("No data yet. Enter a keyword in the sidebar and start scraping.")
    st.stop()

# Parse price/rating
df["price_num"] = df["price"].apply(parse_price)
df["rating_num"] = df["rating"].apply(parse_rating)
df["review_num"] = df["review_count"].apply(lambda x: int(x.replace(",", "")) if x and x != "N/A" else 0)

# --- Summary cards ---
col1, col2, col3, col4 = st.columns(4)
col1.metric("Total Products", f"{len(df):,}")

valid_prices = df["price_num"].dropna()
col2.metric("Avg Price", f"${valid_prices.mean():.2f}" if not valid_prices.empty else "N/A")

valid_ratings = df["rating_num"].dropna()
col3.metric("Avg Rating", f"{valid_ratings.mean():.1f} / 5.0" if not valid_ratings.empty else "N/A")

col4.metric("Keywords", df["keyword"].nunique())

st.markdown("---")

# --- Chart ---
st.subheader("Price Distribution")
price_data = df["price_num"].dropna()
if not price_data.empty:
    import numpy as np
    counts, edges = np.histogram(price_data, bins=15)
    midpoints = [(edges[i] + edges[i+1]) / 2 for i in range(len(counts))]
    chart_df = pd.DataFrame({"Price ($)": midpoints, "Count": counts}).set_index("Price ($)")
    st.line_chart(chart_df)
else:
    st.caption("No price data")

st.markdown("---")

# --- Product gallery ---
st.subheader("Product Gallery")
cols_per_row = 4
rows = (min(len(df), 20) + cols_per_row - 1) // cols_per_row

for row_idx in range(rows):
    cols = st.columns(cols_per_row)
    for col_idx, col in enumerate(cols):
        item_idx = row_idx * cols_per_row + col_idx
        if item_idx >= len(df) or item_idx >= 20:
            break
        item = df.iloc[item_idx]
        with col:
            if item["image_url"] and item["image_url"] != "N/A":
                st.image(item["image_url"], use_container_width=True)
            st.markdown(f"**{item['title'][:60]}...**")
            st.caption(f"{item['price']}  |  {item['rating'][:15] if item['rating'] != 'N/A' else 'N/A'}")

st.markdown("---")

# --- Data table ---
st.subheader("All Data")
display_df = df[["title", "price", "rating", "review_count", "sold_count", "keyword", "created_at"]].copy()
display_df.columns = ["Title", "Price", "Rating", "Reviews", "Sold", "Keyword", "Scraped At"]
st.dataframe(display_df, use_container_width=True, height=400)
