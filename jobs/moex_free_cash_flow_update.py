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

from jobs.moex_data_update import clean_text, text_to_number

logger = logging.getLogger(__name__)

TICKER_FILE = Path(__file__).resolve().parent.parent / "moex_data.csv"
TARGET_YEARS = range(2019, 2026)
API_BASE_URL = "http://finefolionet:8080"


def load_tickers() -> list[str]:
    tickers = []
    seen = set()
    with TICKER_FILE.open(newline="", encoding="utf-8-sig") as ticker_file:
        for row in csv.DictReader(ticker_file):
            ticker = (row.get("Ticker") or "").strip()
            if ticker and ticker not in seen:
                tickers.append(ticker)
                seen.add(ticker)
    return tickers


def parse_free_cash_flow_values(header_cells: list[str], value_cells: list[str]) -> dict[int, float]:
    free_cash_flow = {}
    for header_index, header in enumerate(header_cells):
        year_text = clean_text(header)
        if not re.fullmatch(r"\d{4}", year_text):
            continue

        year = int(year_text)
        if year not in TARGET_YEARS:
            continue

        value_index = header_index + 1
        if value_index >= len(value_cells):
            logger.warning("No FCF value column for MOEX in %s", year)
            continue

        value = text_to_number(value_cells[value_index], suffix_set="billion")
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


def get_free_cash_flow(symbol: str) -> dict[int, float]:
    driver = create_chrome_driver()
    try:
        driver.set_page_load_timeout(30)
        driver.get(f"https://smart-lab.ru/q/{symbol}/f/y/")
        table = WebDriverWait(driver, 15).until(
            EC.presence_of_element_located(
                (By.CSS_SELECTOR, "table[class*='simple-little-table financials']")
            )
        )

        header_cells = []
        for row in table.find_elements(By.CSS_SELECTOR, "tr"):
            cells = row.find_elements(By.CSS_SELECTOR, "th, td")
            cell_texts = [clean_text(cell.text) for cell in cells]
            year_count = sum(
                1
                for text in cell_texts
                if re.fullmatch(r"\d{4}", text) and int(text) in TARGET_YEARS
            )
            if year_count > sum(
                1
                for text in header_cells
                if re.fullmatch(r"\d{4}", text) and int(text) in TARGET_YEARS
            ):
                header_cells = cell_texts

        fcf_rows = table.find_elements(By.CSS_SELECTOR, "tr[field='fcf']")
        if not header_cells or not fcf_rows:
            logger.info("No historical FCF row found for MOEX %s", symbol)
            return {}

        value_cells = [
            clean_text(cell.text)
            for cell in fcf_rows[0].find_elements(By.CSS_SELECTOR, "th, td")
        ]
        return parse_free_cash_flow_values(header_cells, value_cells)
    finally:
        driver.quit()


def run_update():
    for ticker in load_tickers():
        try:
            values_by_year = get_free_cash_flow(ticker)
        except Exception:
            logger.exception("Failed to scrape free cash flow for MOEX %s", ticker)
            continue

        for year, value in values_by_year.items():
            url = f"{API_BASE_URL}/valuation/MOEX/{ticker}/free-cash-flow"
            try:
                response = requests.post(url, json={"year": year, "value": value}, timeout=20)
            except requests.RequestException:
                logger.exception("Failed to submit free cash flow for MOEX %s in %s", ticker, year)
                continue

            if response.status_code == 200:
                logger.info("Updated free cash flow for MOEX %s in %s", ticker, year)
            else:
                logger.error(
                    "Free cash flow update failed for MOEX %s in %s: HTTP %s",
                    ticker,
                    year,
                    response.status_code,
                )
