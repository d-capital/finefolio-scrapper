import requests
import numpy as np
import pandas as pd
from datetime import datetime, timedelta
import statsmodels.api as sm
import apimoex
import time

def get_prices_from_moex(ticker:str, boardid:str, market: str) -> pd.DataFrame:
    end_date = datetime.now().strftime('%Y-%m-%d')
    start_date = (datetime.now() - timedelta(days=3*365)).strftime('%Y-%m-%d')
    with requests.Session() as session:
        data = apimoex.get_market_history(session, ticker, start_date, end_date)
        df = pd.DataFrame(data)
        df.set_index('TRADEDATE', inplace=True)
        return df[df['BOARDID']==boardid]
    
def get_index_prices_from_moex(ticker:str, boardid:str, market: str) -> pd.DataFrame:
    end_date = datetime.now().strftime('%Y-%m-%d')
    start_date = (datetime.now() - timedelta(days=3*365)).strftime('%Y-%m-%d')
    with requests.Session() as session:
        data = apimoex.get_board_history(session, 'IMOEX', board='SNDX',start=start_date,end=end_date, market='index')
        df = pd.DataFrame(data)
        df.set_index('TRADEDATE', inplace=True)
        return df

def get_beta(ticker: str, index_price) -> float:
    stock_prices = get_prices_from_moex(ticker,'TQBR', 'shares')#TQOB for bonds, TQBR for stocks
    stock_close_prices = stock_prices['CLOSE']
    index_close_price = index_price['CLOSE']
    stock_returns = np.log(stock_close_prices / stock_close_prices.shift(1))
    index_returns = np.log(index_close_price / index_close_price.shift(1))
    returns = pd.concat([stock_returns, index_returns], axis=1).dropna()
    returns.columns = ['Stock', 'Index']
    # Linear Regression
    X = sm.add_constant(returns['Index'])
    model = sm.OLS(returns['Stock'], X).fit()
    beta = model.params['Index']
    return beta

def run_update():
    moex_data = pd.read_csv("moex_data.csv")
    moex_tickers = moex_data['Ticker'].to_list()
    index_price = get_index_prices_from_moex("IMOEX",'SNDX', 'index')#TQOB for bonds, TQBR for stocks
    for ticker in moex_tickers:
        payload = {}
        time.sleep(30)  # Sleep for 15 seconds to avoid hitting the API rate limit
        beta = get_beta(ticker, index_price)
        payload['beta'] = beta
        print(f"Updating beta for {ticker} with payload: {payload}")
        print(f"Beta: {beta}")
        response = requests.patch(f'http://finefolionet:8080/asset-fundamentals/MOEX/{ticker}', json=payload)
        if response.status_code == 200:
            print(f"Successfully updated beta for {ticker}")
        else:
            print(f"Failed to update beta for {ticker}")
    print("Finished beta update job.")
        