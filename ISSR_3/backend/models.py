from pydantic import BaseModel, Field

class EventLog(BaseModel):
    participant_id: str = Field(..., description="User ID")
    condition: str = Field(..., description="Experiment group")
    decision: str = Field(..., description="User decision")
    timestamp: str = Field(..., description="Event time")
    latency_ms: float = Field(..., description="Decision time (ms)")