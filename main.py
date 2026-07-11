from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from contextlib import asynccontextmanager
from pytz import timezone
from jobs import moex_data_update, us_data_update

from apscheduler.schedulers.background import BackgroundScheduler

from routers import healthcheck

scheduler = BackgroundScheduler()
moscow_tz = timezone('Europe/Moscow')
scheduler.add_job(
    moex_data_update.run_update, 
    'cron',
    #day_of_week='sun',
    hour=5,
    minute=00,
    timezone=moscow_tz,
    id='weekly_5am_moscow_moex_fundamentals')

scheduler.add_job(
    us_data_update.run_update, 
    'cron',
    #day_of_week='sun',
    hour=6,
    minute=00,
    timezone=moscow_tz,
    id='weekly_6am_moscow_us_net_income')


@asynccontextmanager
async def lifespan(app: FastAPI):
    scheduler.start()
    yield
    
app = FastAPI(title="Finefolio Scrapper", lifespan=lifespan)

origins = [
    "https://localhost",        # Если вы заходите по https на локалке
    "https://valestor.com",   # Ваш реальный домен
    "http://localhost:5001",         # Если используется http
]

app.add_middleware(
    CORSMiddleware,
    allow_origins=origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(healthcheck.router, prefix="/healthcheck", tags=["Health Check"])