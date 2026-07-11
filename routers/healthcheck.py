from fastapi import APIRouter, HTTPException

from models.healthcheck_status import HealthCheckStatus

router = APIRouter()

@router.get("/status", response_model=HealthCheckStatus)
def health_check():
    return HealthCheckStatus(isAlive=True)
