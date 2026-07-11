from pydantic import BaseModel

class HealthCheckStatus(BaseModel):
    isAlive: bool