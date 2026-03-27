from pydantic import BaseModel

class EventLog(BaseModel):
    participant_id: str
    condition: str
    decision: str
    timestamp: str
    latency_ms: float
