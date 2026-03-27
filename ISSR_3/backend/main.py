import json
import csv
import os
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from models import EventLog

app = FastAPI()

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

OUTPUT_DIR = "output"
os.makedirs(OUTPUT_DIR, exist_ok=True)

JSON_FILE = os.path.join(OUTPUT_DIR, "logs.json")
CSV_FILE = os.path.join(OUTPUT_DIR, "logs.csv")

def init_files():
    if not os.path.exists(JSON_FILE):
        with open(JSON_FILE, "w") as f:
            json.dump([], f)
    if not os.path.exists(CSV_FILE):
        with open(CSV_FILE, "w", newline="") as f:
            writer = csv.writer(f)
            writer.writerow(["participant_id", "condition", "decision", "timestamp", "latency_ms"])

init_files()

@app.post("/api/log")
async def log_event(event: EventLog):
    try:
        if not os.path.exists(JSON_FILE):
            data = []
        else:
            with open(JSON_FILE, "r", encoding="utf-8") as f:
                try:
                    data = json.load(f)
                except json.JSONDecodeError:
                    data = []
        
        data.append(event.model_dump())
        
        with open(JSON_FILE, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=4)
    except Exception as e:
        print("JSON Write Error:", e)
        
    try:
        file_exists = os.path.exists(CSV_FILE)
        with open(CSV_FILE, "a", encoding="utf-8", newline="") as f:
            writer = csv.writer(f)
            if not file_exists:
                writer.writerow(["participant_id", "condition", "decision", "timestamp", "latency_ms"])
            writer.writerow([event.participant_id, event.condition, event.decision, event.timestamp, event.latency_ms])
            f.flush()
    except Exception as e:
        print("CSV Write Error:", e)
        
    return {"status": "success"}
