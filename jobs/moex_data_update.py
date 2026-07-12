import requests

from selenium import webdriver
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver.support.select import WebElement
import re
import time
import pandas as pd
import re
from datetime import datetime, timedelta

import re
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

def find_last_element(elements: list[WebElement], suffix_set='billion') -> float:
    if len(elements)>0:
        el1 = elements[0].find_elements(By.CSS_SELECTOR, "td")[-3].text.strip()
        el2 = elements[0].find_elements(By.CSS_SELECTOR, "td")[-4].text.strip()
        if text_to_number(el1, suffix_set=suffix_set) is not None:
            return text_to_number(el1, suffix_set=suffix_set)
        elif text_to_number(el2, suffix_set=suffix_set) is not None:
            return text_to_number(el2, suffix_set=suffix_set)
        else:
            return 0.0
    return 0.0 

def find_eps_ttm(elements: list[WebElement], suffix_set='billion') -> float:
    if len(elements)>0:
        el0 = elements[0].find_elements(By.CSS_SELECTOR, "td")[-1].text.strip()
        el1 = elements[0].find_elements(By.CSS_SELECTOR, "td")[-3].text.strip()
        el2 = elements[0].find_elements(By.CSS_SELECTOR, "td")[-4].text.strip()
        if text_to_number(el0, suffix_set=suffix_set) is not None:
            return text_to_number(el0, suffix_set=suffix_set)
        if text_to_number(el1, suffix_set=suffix_set) is not None:
            return text_to_number(el1, suffix_set=suffix_set)
        elif text_to_number(el2, suffix_set=suffix_set) is not None:
            return text_to_number(el2, suffix_set=suffix_set)
        else:
            return 0.0
    return 0.0 

def get_submitted_files():
    options = Options()
    options.add_argument("--headless=new")
    moex_data = pd.read_csv("moex_data.csv")
    moex_tickers = moex_data['Ticker'].to_list()
    driver = webdriver.Chrome(options=options)
    today = datetime.now()
    seven_days_ago = today - timedelta(days=7)
    formatted_date = today.strftime("%d.%m.%Y")
    formatted_seven_days_ago = seven_days_ago.strftime("%d.%m.%Y")
    # Output: 07.03.2026 (assuming today is March 7, 2026)
    url = f"https://smart-lab.ru/calendar/stocks/company_reports/country_0/from_{formatted_seven_days_ago}/to_{formatted_date}/"
    driver.get(url)
    time.sleep(10)
    # Wait for the financials table to appear
    table = WebDriverWait(driver, 15).until(
        EC.presence_of_element_located((By.CSS_SELECTOR, "table[class*='simple-little-table']"))
    )
    all_events = table.find_elements(By.CSS_SELECTOR, "tr[class='odd']")
    updated_tickers = []
    for i in range(len(all_events)):
        row = all_events[i]
        ticker = row.text.split(" ")[1].split(":")[0]
        print(ticker)
        updated_tickers.append(ticker)
    stocks_to_update = [item for item in updated_tickers if item in moex_tickers]
    return stocks_to_update


def get_net_income_for_years(symbol, target_years=("2025")):
    options = Options()
    options.add_argument("--headless=new") 
    driver = webdriver.Chrome(options=options)
    url = f"https://smart-lab.ru/q/{symbol}/f/y/"
    driver.get(url)
    time.sleep(10)
    # Wait for the financials table to appear
    table = WebDriverWait(driver, 15).until(
        EC.presence_of_element_located((By.CSS_SELECTOR, "table[class*='simple-little-table financials']"))
    )

    items = table.find_elements(By.CSS_SELECTOR, "tr[field*='net_income']")
    if len(items)>0:
        children = items[0].find_elements(By.CSS_SELECTOR, "td")
        net_income = text_to_number(children[5].text.strip())
    eps_row = table.find_elements(By.CSS_SELECTOR, "tr[field='eps']")
    eps = find_eps_ttm(eps_row, suffix_set=None)
    print("EPS: "+str(eps))
    debt_row = table.find_elements(By.CSS_SELECTOR, "tr[field='debt']")
    if len(debt_row)==0:
        debt_row = table.find_elements(By.CSS_SELECTOR, "tr[field='net_debt']")
    debt = find_last_element(debt_row, suffix_set='billion')
    print("Debt: "+str(debt))
    equity_row = table.find_elements(By.CSS_SELECTOR, "tr[field='assets']")
    if len(equity_row)==0:
        equity_row = table.find_elements(By.CSS_SELECTOR, "tr[field='bank_assets']")
    equity = find_last_element(equity_row,'billion')
    print("Equity: "+str(equity))
    fcf_row = table.find_elements(By.CSS_SELECTOR, "tr[field='fcf']")
    fcf = find_last_element(fcf_row, suffix_set='billion')
    print("FCF: "+str(fcf))
    dividends_row = table.find_elements(By.CSS_SELECTOR, "tr[field='div_yield']")
    dividends = find_last_element(dividends_row, suffix_set=None)
    print("Dividends: "+str(dividends))

    interest_expenses = table.find_elements(By.CSS_SELECTOR, "tr[field='interest_expenses']")
    interest_expenses = find_last_element(interest_expenses, suffix_set='billion')
    net_debt = table.find_elements(By.CSS_SELECTOR, "tr[field='net_debt']")
    net_debt = find_last_element(net_debt, suffix_set='billion')
    print("interest_expenses: "+str(interest_expenses))
    print("net_debt: "+str(net_debt))

    driver.quit()
    return net_income, eps, debt, equity, fcf, dividends, interest_expenses, net_debt

def run_update():
    stocks_to_update = get_submitted_files()
    if len(stocks_to_update) > 0:
        print(stocks_to_update)
        file = pd.read_csv("moex_data.csv")
        for ticker in stocks_to_update:
            print("started: " + ticker)
            ticker_row = file[file['Ticker'] == ticker]
            if len(ticker_row)>0:
                financials = get_net_income_for_years(ticker)
                if financials[0] is not None:
                    net_income_2025 = int(financials[0])
                    net_income_payload = {
                        'year': 2025,
                        'value': net_income_2025
                    }
                    net_income_response = requests.post(f'http://finefolionet:8080/valuation/MOEX/{ticker}/net-income', json=net_income_payload,verify=False)
                    if net_income_response.status_code == 200:
                        print(f"Successfully updated net income for {ticker} for 2025")
                    else:
                        print(f"Failed to update net income for {ticker} for 2025")
                payload = {}
                if financials[1] is not None:
                    eps = int(financials[1])
                    payload['earningsPerShareBasicTtm'] = eps
                if financials[2] is not None:
                    debt = int(financials[2])
                    payload['debt'] = debt
                if financials[3] is not None:
                    equity = int(financials[3])
                    payload['equity'] = equity
                if financials[4] is not None:
                    fcf = int(financials[4])
                    payload['freeCashFlowFy'] = fcf
                if financials[5] is not None:
                    dividends = int(financials[5])
                    payload['dividendsYield'] = dividends
                if financials[6] is not None:
                    interest_expenses = int(financials[6])
                    payload['interestExpenses'] = interest_expenses
                if financials[7] is not None:
                    net_debt = int(financials[7])
                    payload['netDebt'] = net_debt
                if len(payload) == 0:
                    print(f"No financial data found for {ticker}. Skipping update.")
                else:
                    print(f"Updating financial data for {ticker} with payload: {payload}")
                    response = requests.patch(f'http://finefolionet:8080/asset-fundamentals/MOEX/{ticker}', json=payload)
                    if response.status_code == 200:
                        print(f"Successfully updated {ticker}")
                    else:
                        print(f"Failed to update {ticker}")
                print("finished: " + ticker)
            else:
                print("ticker not found in file: " + ticker)
    else:
        print("No stocks to update.")