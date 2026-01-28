# Amazon Price Scraper

A tool that collects Amazon product prices and provides a REST API for querying the data.

## Features

- Search and scrape Amazon products by keyword
- Store price data in SQLite database
- Query data via FastAPI REST API

## Installation
```bash
pip install selenium webdriver-manager fastapi uvicorn
```

## Usage

### Scraping
```bash
python scraper.py "wireless mouse"
```

### Run API Server
```bash
uvicorn api:app --reload
```

### API Endpoints

- `GET /` - Home
- `GET /products` - List of saved keywords
- `GET /products/{keyword}` - Products for specific keyword

## Tech Stack

- Python
- Selenium
- FastAPI
- SQLite
