import json
import os
import re
import time
from datetime import datetime, timedelta

import requests
from kafka import KafkaProducer
from selenium import webdriver
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver.support.select import WebElement
import pandas as pd

KAFKA_BOOTSTRAP_SERVERS = os.getenv("KAFKA_BOOTSTRAP_SERVERS", "kafka-broker:9092").split(",")
KAFKA_NET_INCOME_TOPIC = os.getenv("KAFKA_NET_INCOME_TOPIC", "finefolio.net-income")


def get_kafka_producer():
    return KafkaProducer(
        bootstrap_servers=KAFKA_BOOTSTRAP_SERVERS,
        value_serializer=lambda value: json.dumps(value, default=str).encode("utf-8"),
    )

def get_timestamp_a_week_ago():
    # Calculate the datetime 7 days ago
    seven_days_ago = datetime.now() - timedelta(days=7)
    # Convert to a 13-digit millisecond timestamp
    timestamp_ms = int(seven_days_ago.timestamp() * 1000)
    return timestamp_ms

def get_tickers(timestamp:str):
    options = Options()
    # Direct Selenium to the native Debian package locations
    options.binary_location = "/usr/bin/chromium" 
    options.add_argument("--headless=new")
    options.add_argument("--no-sandbox")
    options.add_argument("--disable-dev-shm-usage")
    # Pass the native system driver path explicitly
    service = Service(executable_path="/usr/bin/chromedriver")
    driver = webdriver.Chrome(service=service, options=options)
    url = f"https://www.tradingview.com/earnings-calendar/?countries=us&timestamp={timestamp}"
    driver.get(url)
    time.sleep(10)
    # Wait for the financials table to appear
    table = WebDriverWait(driver, 5).until(
        EC.presence_of_element_located((By.CSS_SELECTOR, "div[class*='table']"))
    )
    symbol = driver.find_elements(By.CSS_SELECTOR, "div[class*='symbolWrap']")
    tickers = []
    for i in range(len(symbol)):
        a = symbol[i].find_element(By.TAG_NAME,'a')
        ticker_exchange = a.get_attribute("href").split("/")[-2]
        ticker = ticker_exchange.split("-")[1]
        exchange = ticker_exchange.split("-")[0]
        if exchange in ["NYSE","NASDAQ"]:
            new_element = {"exchange":exchange,"ticker":ticker}
            tickers.append(new_element)
    driver.quit()
    return tickers

def clean_text(txt: str) -> str:
    """Remove invisible Unicode formatting chars and normalize minus/dashes."""
    if txt is None:
        return ''
    # remove directional/formatting/invisible characters
    txt = re.sub(r'[\u200B-\u200F\u202A-\u202F\u2060-\u206F\uFEFF]', '', txt)
    # normalize common Unicode minus/dash characters to ASCII minus
    txt = txt.replace('\u2212', '-')  # unicode minus
    txt = txt.replace('\u2013', '-')  # en dash
    txt = txt.replace('\u2014', '-')  # em dash
    # trim and collapse multiple spaces (including exotic spaces)
    txt = re.sub(r'\s+', ' ', txt).strip()
    return txt

def text_to_number(txt, suffix_set='billion') -> float:
    """
    Convert strings like '5.88 B', '−1.98\u202fB', '(1.2M)', '2.1M', '3,450' into numeric values.
    Returns int when integer-valued, otherwise float. Returns None if parsing fails.
    """
    if txt is None:
        return None

    s = clean_text(txt)
    if not s:
        return None

    # common approximations and noise characters
    s = s.replace('~', '').replace('≈', '')
    s = s.replace(' ', '')         # remove thousands separators
    s = s.replace('\u202f', ' ')   # narrow NBSP -> space (if any remain)
    s = s.replace('\u00A0', ' ')   # non-breaking space -> space
    s = s.replace(',', '')         # remove thousands separators
    s = s.strip().lower()

    # parentheses indicate negative in some reports: "(1.2B)" -> -1.2B
    is_parentheses_negative = False
    if s.startswith('(') and s.endswith(')'):
        is_parentheses_negative = True
        s = s[1:-1].strip()

    # find first numeric token + optional suffix
    m = re.search(r'([+-]?\d+(?:\.\d+)?)\s*(k|m|b|t|thousand|million|billion|trillion)?', s)
    if not m:
        return None

    num = float(m.group(1))
    suffix = suffix_set

    # if number had an explicit leading sign we keep it; otherwise apply parentheses-negation
    if not str(m.group(1)).startswith(('+', '-')) and is_parentheses_negative:
        num = -num

    multipliers = {
        'k': 1_000,
        'm': 1_000_000,
        'b': 1_000_000_000,
        't': 1_000_000_000_000,
        'thousand': 1_000,
        'million': 1_000_000,
        'billion': 1_000_000_000,
        'trillion': 1_000_000_000_000,
    }

    if suffix:
        num *= multipliers.get(suffix, 1)

    # return int when whole number
    if num.is_integer():
        return int(num)
    return float(num)


def get_net_income(exchange:str,tickers:list[str]):
    for ticker in tickers:
        options = Options()
        # Direct Selenium to the native Debian package locations
        options.binary_location = "/usr/bin/chromium" 
        options.add_argument("--headless=new")
        options.add_argument("--no-sandbox")
        options.add_argument("--disable-dev-shm-usage")
        # Pass the native system driver path explicitly
        service = Service(executable_path="/usr/bin/chromedriver")
        driver = webdriver.Chrome(service=service, options=options)
        url = f"https://tradingview.com/symbols/{exchange}-{ticker}/financials-income-statement/?selected=total_revenue%2Cgross_profit%2Coper_income%2Cpretax_income"
        driver.get(url)
        try:
            table = WebDriverWait(driver, 5).until(EC.presence_of_element_located((By.CSS_SELECTOR, "div[class*='tableWrap']")))
            header_row = table.find_elements(By.CSS_SELECTOR, 'div[class*="stickyContainer"]')[0]   
            year_2025 = header_row.find_elements(By.XPATH, "//span[contains(@class, 'conten') and contains(text(), '2025')]")
            year_2026 = header_row.find_elements(By.XPATH, "//span[contains(@class, 'conten') and contains(text(), '2026')]")
            if len(year_2025)>0 and len(year_2026)<=0:
                net_income_row = driver.find_elements(By.CSS_SELECTOR, '[data-name="Net income"]')
                values = net_income_row[0].find_elements(By.CSS_SELECTOR, "div[class*='container']")  
                value = text_to_number(clean_text(values[-2].text).split(" ")[0])
                driver.quit()
                return value
            else:
                driver.quit()
                return None
        except:
            driver.quit()
            return None


def run_update():
    timestamp = get_timestamp_a_week_ago()
    tickers = get_tickers(timestamp=timestamp)
    producer = get_kafka_producer()

    for ticker in tickers:
        net_income_2025 = get_net_income(ticker["exchange"], [ticker["ticker"]])
        if net_income_2025 is not None:
            net_income_payload = {
                "exchange": ticker["exchange"],
                "ticker": ticker["ticker"],
                "year": 2025,
                "value": net_income_2025,
            }
            try:
                future = producer.send(
                    KAFKA_NET_INCOME_TOPIC,
                    key=f"{ticker['exchange']}.{ticker['ticker']}".encode("utf-8"),
                    value=net_income_payload,
                )
                record_metadata = future.get(timeout=10)
                print(
                    f"Successfully sent net income to Kafka topic {record_metadata.topic} "
                    f"for {ticker['exchange']}:{ticker['ticker']} for 2025"
                )
            except Exception as exc:
                print(
                    f"Failed to send net income to Kafka for {ticker['exchange']}:{ticker['ticker']} "
                    f"for 2025: {exc}"
                )

    producer.flush()
    producer.close()
    