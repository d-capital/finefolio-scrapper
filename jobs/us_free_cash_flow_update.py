import csv
import logging
import re
from pathlib import Path

import requests
from selenium import webdriver
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.common.by import By
from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver.support.ui import WebDriverWait

from jobs.us_data_update import clean_text, text_to_number

logger = logging.getLogger(__name__)

TICKER_FILE = Path(__file__).resolve().parent.parent / "net_income_nyse_nasdaq.csv"
TARGET_YEARS = range(2019, 2026)
FREE_CASH_FLOW_DATA_NAME = "Free cash flow"
API_BASE_URL = "http://localhost:64663"


def load_tickers() -> list[tuple[str, str]]:
    tickers = []
    with TICKER_FILE.open(newline="", encoding="utf-8-sig") as ticker_file:
        for row in csv.DictReader(ticker_file):
            ticker = (row.get("tickers") or "").strip()
            exchange = (row.get("exchange") or "").strip().upper()
            if ticker and exchange in {"NYSE", "NASDAQ"}:
                tickers.append((exchange, ticker))
    return tickers


def parse_free_cash_flow_values(annual_years: set[int], value_texts: list[str]) -> dict[int, float]:
    available_years = annual_years.intersection(TARGET_YEARS)
    if not available_years:
        return {}

    latest_year = max(annual_years)
    latest_year_index = len(value_texts) - 2
    free_cash_flow = {}

    for year in sorted(available_years):
        value_index = latest_year_index - (latest_year - year)
        if value_index < 0 or value_index >= len(value_texts) - 1:
            logger.warning("No TradingView value column for %s", year)
            continue
        value_text = clean_text(value_texts[value_index]).split("\n")[0]
        value = text_to_number(value_text)
        if value is not None:
            free_cash_flow[year] = value

    return free_cash_flow


def create_chrome_driver():
    options = Options()
    options.add_argument("--headless=new")
    options.add_argument("--no-sandbox")
    options.add_argument("--disable-dev-shm-usage")

    chromium_path = Path("/usr/bin/chromium")
    driver_path = Path("/usr/bin/chromedriver")
    if chromium_path.is_file() and driver_path.is_file():
        options.binary_location = str(chromium_path)
        service = Service(executable_path=str(driver_path))
        return webdriver.Chrome(options=options, service=service)

    return webdriver.Chrome(options=options)


def get_free_cash_flow(exchange: str, ticker: str) -> dict[int, float]:
    driver = create_chrome_driver()

    try:
        driver.set_page_load_timeout(30)
        url = f"https://www.tradingview.com/symbols/{exchange}-{ticker}/financials-cash-flow/"
        driver.get(url)
        table = WebDriverWait(driver, 10).until(
            EC.presence_of_element_located((By.CSS_SELECTOR, 'div[class*="tableWrap"]'))
        )
        header_row = table.find_elements(By.CSS_SELECTOR, 'div[class*="stickyContainer"]')[0]
        annual_years = set()
        for element in header_row.find_elements(By.CSS_SELECTOR, "span"):
            year = clean_text(element.text)
            if re.fullmatch(r"\d{4}", year):
                annual_years.add(int(year))
        if not annual_years.intersection(TARGET_YEARS):
            return {}

        rows = driver.find_elements(By.CSS_SELECTOR, f'[data-name="{FREE_CASH_FLOW_DATA_NAME}"]')
        if not rows:
            return {}

        values = rows[0].find_elements(By.CSS_SELECTOR, 'div[class*="container"]')
        return parse_free_cash_flow_values(annual_years, [value.text for value in values])
    finally:
        driver.quit()


def run_update():
    for exchange, ticker in load_tickers():
        try:
            free_cash_flow_by_year = get_free_cash_flow(exchange, ticker)
        except Exception:
            logger.exception("Failed to scrape free cash flow for %s %s", exchange, ticker)
            continue

        for year, value in free_cash_flow_by_year.items():
            payload = {"year": year, "value": value}
            url = f"{API_BASE_URL}/valuation/{exchange}/{ticker}/free-cash-flow"
            try:
                response = requests.post(url, json=payload, timeout=20)
            except requests.RequestException:
                logger.exception("Failed to submit free cash flow for %s %s in %s", exchange, ticker, year)
                continue

            if response.status_code == 200:
                logger.info("Updated free cash flow for %s %s in %s", exchange, ticker, year)
            else:
                logger.error(
                    "Free cash flow update failed for %s %s in %s: HTTP %s",
                    exchange,
                    ticker,
                    year,
                    response.status_code,
                )
