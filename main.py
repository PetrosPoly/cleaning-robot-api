
"""
A FastAPI application that:
1) Reads a map from .txt or .json (in memory).
2) Cleans tiles based on a user-provided path.
3) Logs each cleaning session to a CSV file (session_history.csv).
4) Lets the user download the CSV through /history.

Run it via: uvicorn main_csv_file:app --reload
"""

from fastapi import FastAPI, UploadFile, File, HTTPException, Body
from fastapi.responses import JSONResponse, FileResponse, StreamingResponse
import json
import time
import os
import csv
from datetime import datetime

# Create the FastAPI app with a title and description
app = FastAPI(
    title="Cleaning Robot API (CSV File)",
    description="Logs cleaning sessions in a CSV file on disk.",
    version="1.0.0"
)

# Global in-memory map variables
map_data = {}
map_rows = 0
map_cols = 0

# We'll store session logs in a CSV file instead of in memory
HISTORY_FILE = "session_history.csv"

# In-memory session counter for new sessions
session_id = 1

def set_map_from_txt(file_content: str):
    """
    Parse a .txt file with 'o' (walkable) and 'x' (non-walkable),
    then update map_data, map_rows, and map_cols.
    """
    global map_data, map_rows, map_cols

    lines = file_content.strip().split("\n")
    map_rows = len(lines)
    map_cols = len(lines[0]) if map_rows > 0 else 0

    map_data = {}
    for y, line in enumerate(lines):
        for x, char in enumerate(line):
            map_data[(x, y)] = (char == 'o')

def set_map_from_json(file_content: str):
    """
    Parse a JSON map of the form:
      {
        "rows": <int>,
        "cols": <int>,
        "tiles": [
          {"x": 0, "y": 0, "walkable": true},
          ...
        ]
      }
    """
    global map_data, map_rows, map_cols

    data = json.loads(file_content)
    map_rows = data["rows"]
    map_cols = data["cols"]
    map_data = {}

    for tile in data["tiles"]:
        x, y = tile["x"], tile["y"]
        map_data[(x, y)] = tile["walkable"]

def append_session_to_csv(session_data: dict):
    """
    Append a single session record to the HISTORY_FILE CSV.
    If the file doesn't exist, create it and write a header row.
    """
    file_exists = os.path.exists(HISTORY_FILE)

    with open(HISTORY_FILE, "a", newline="", encoding="utf-8") as f:
        writer = csv.writer(f)
        if not file_exists:
            writer.writerow([
                "id", "start_time", "end_time", "final_state",
                "actions_count", "tiles_cleaned", "duration_seconds"
            ])
        writer.writerow([
            session_data["id"],
            session_data["start_time"],
            session_data["end_time"],
            session_data["final_state"],
            session_data["actions_count"],
            session_data["tiles_cleaned"],
            session_data["duration_seconds"]
        ])

def run_cleaning(start_x: int, start_y: int, actions: list, premium: bool = False):
    """
    Step through the map:
    - (start_x, start_y) is the initial tile.
    - 'actions' is a list of {direction: str, steps: int}.
    - 'premium' means skip re-cleaning tiles if we've already cleaned them.
    Return (cleaned_tiles, final_state).
    """
    # Validate starting tile
    if not (0 <= start_x < map_cols and 0 <= start_y < map_rows):
        return [], "error"
    if not map_data.get((start_x, start_y), False):
        return [], "error"

    # Track cleaned tiles
    cleaned_tiles = set()
    cleaned_tiles.add((start_x, start_y))

    current_x, current_y = start_x, start_y

    # Go through each action
    for action in actions:
        direction = action["direction"]
        steps = action["steps"]

        for _ in range(steps):
            if direction == "north":
                current_y -= 1
            elif direction == "south":
                current_y += 1
            elif direction == "east":
                current_x += 1
            elif direction == "west":
                current_x -= 1
            else:
                # Invalid direction
                return list(cleaned_tiles), "error"

            # Check bounds
            if not (0 <= current_x < map_cols and 0 <= current_y < map_rows):
                return list(cleaned_tiles), "error"
            # Check walkable
            if not map_data.get((current_x, current_y), False):
                return list(cleaned_tiles), "error"

            # Premium: skip if already in cleaned_tiles
            if not premium or (premium and (current_x, current_y) not in cleaned_tiles):
                cleaned_tiles.add((current_x, current_y))

    return list(cleaned_tiles), "completed"

@app.post("/set-map")
async def set_map(file: UploadFile = File(...)):
    """
    Upload a .txt or .json map to define the robot's environment.
    """
    contents = await file.read()
    file_str = contents.decode("utf-8")

    if file.filename.endswith(".txt"):
        set_map_from_txt(file_str)
    elif file.filename.endswith(".json"):
        set_map_from_json(file_str)
    else:
        raise HTTPException(status_code=400, detail="Only .txt or .json are supported.")

    return {"status": "map set", "rows": map_rows, "cols": map_cols}

@app.post("/clean")
def clean_endpoint(
    start_x: int = Body(...),
    start_y: int = Body(...),
    actions: list = Body(...),
    premium: bool = Body(False)
):
    """
    Execute cleaning based on the provided coordinates and actions.
    Each run is appended to a CSV file.
    """
    global session_id

    start_time = datetime.utcnow()
    start_timestamp = time.time()

    cleaned_tiles, final_state = run_cleaning(start_x, start_y, actions, premium)

    end_time = datetime.utcnow()
    end_timestamp = time.time()
    duration = end_timestamp - start_timestamp

    session_data = {
        "id": session_id,
        "start_time": start_time.isoformat(),
        "end_time": end_time.isoformat(),
        "final_state": final_state,
        "actions_count": len(actions),
        "tiles_cleaned": len(cleaned_tiles),
        "duration_seconds": duration
    }

    # Append to CSV file
    append_session_to_csv(session_data)
    session_id += 1

    response_body = {
        "cleaned_tiles": cleaned_tiles,
        "final_state": final_state
    }

    if final_state == "error":
        raise HTTPException(status_code=400, detail=response_body)

    return JSONResponse(content=response_body, status_code=200)

@app.get("/history")
def get_history():
    """
    Download the session_history.csv file with all past sessions.
    Returns 404 if no sessions exist.
    """
    if not os.path.exists(HISTORY_FILE):
        raise HTTPException(status_code=404, detail="No session history found.")

    # Define your header as a single CSV line
    HEADER = "id,start_time,end_time,final_state,actions_count,tiles_cleaned,duration_seconds\n"

    def generate_csv_with_header():
        # 1) Yield the header first
        yield HEADER
        # 2) Then read from the existing CSV file and yield its lines
        with open(HISTORY_FILE, "r", newline="", encoding="utf-8") as f:
            for line in f:
                yield line  # Reads each line from session_history.csv and yields it to the client.

    # Return a StreamingResponse which combines header + file content
    return StreamingResponse(  # StreamingResponse: dynamically add the header row
        generate_csv_with_header(),
        media_type="text/csv",
        headers={"Content-Disposition": "attachment; filename=session_history.csv"}  # Content-Disposition header forces the browser to download the file
    )

