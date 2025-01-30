from fastapi import FastAPI, UploadFile, File, HTTPException, Body
from fastapi.responses import JSONResponse, StreamingResponse
import json
import time
import io
import csv
import json
from datetime import datetime

# Custon functions
from functions import set_map_from_txt, set_map_from_json

# -----------------------------------------------------------------------------
# FASTAPI APP INSTANCE
# -----------------------------------------------------------------------------
# We create a FastAPI "app" which will handle incoming HTTP requests.
app = FastAPI(
    title="Cleaning Robot API (In-Memory)",
    description="A minimal REST API controlling a cleaning robot.",
    version="1.0.0"
)

# -----------------------------------------------------------------------------
# GLOBAL VARIABLES FOR MAP
# -----------------------------------------------------------------------------
# We store the map as a dictionary of { (x, y): bool }, indicating True if walkable, False if non-walkable.
# map_rows and map_cols track the size of the grid.
map_data = {}
map_rows = 0
map_cols = 0

# -----------------------------------------------------------------------------
# GLOBAL LIST FOR CLEANING SESSIONS
# -----------------------------------------------------------------------------
# Each session is stored as a dictionary with keys: id, start_time, end_time, final_state, actions_count, tiles_cleaned, duration_seconds
# We also keep a session_id counter so each session can have a unique ID.
cleaning_history = []
session_id = 1

# -----------------------------------------------------------------------------
# UTILITY FUNCTIONS TO PARSE MAP FILES
# -----------------------------------------------------------------------------
def set_map_from_txt(file_content: str):
    """
    Parse a .txt map where:
      'o' -> walkable tile
      'x' -> non-walkable tile
    We fill map_data, map_rows, map_cols based on the lines in the file.
    """
    global map_data, map_rows, map_cols

    # Split the file content by newlines to get each row.
    lines = file_content.strip().split("\n")

    # The number of rows is simply how many lines we have.
    map_rows = len(lines)
    # The number of columns is the length of the first line (if there is one).
    map_cols = len(lines[0])

    # Reset map_data for the new map.
    map_data = {}
    # Iterate over each line (row index = y).
    for y, line in enumerate(lines):
        # For each character (column index = x) in the line,
        # check if it's 'o' or 'x' and store in map_data.
        for x, char in enumerate(line):
            map_data[(x, y)] = (char == 'o')  # True if 'o', False if 'x'

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
    We then update map_data, map_rows, and map_cols accordingly.
    """
    global map_data, map_rows, map_cols

    # Convert the JSON string into a Python dict.
    data = json.loads(file_content)

    # Extract the dimensions: number of rows and columns.
    map_rows = data["rows"]
    map_cols = data["cols"]

    # Reset map_data.
    map_data = {}

    # Read each tile in the "tiles" array.
    for tile in data["tiles"]:
        x = tile["x"]
        y = tile["y"]
        # 'walkable' is True or False.
        map_data[(x, y)] = tile["walkable"]

# -----------------------------------------------------------------------------
# ENDPOINT: /set-map
# -----------------------------------------------------------------------------
# This endpoint receives a file (either .txt or .json) to define the robot's environment.

@app.post("/set-map")
async def set_map(file: UploadFile = File(...)):
    """
    Accepts a file upload. The file must be .txt or .json.
    We parse the file and store the map layout in memory.
    """
    # Read the uploaded file as bytes.
    contents = await file.read()
    # Decode the bytes into a UTF-8 string (both text and JSON are text-based).
    file_str = contents.decode("utf-8")

    # Check the file extension to decide how to parse it.
    if file.filename.endswith(".txt"):
        set_map_from_txt(file_str)
    elif file.filename.endswith(".json"):
        set_map_from_json(file_str)
    else:
        # If neither .txt nor .json, we reject with a 400 (Bad Request).
        raise HTTPException(status_code=400, detail="Unsupported file format. Use .txt or .json.")

    # Return a summary of what was parsed: number of rows and columns.
    return {
        "status": "map set",
        "rows": map_rows,
        "cols": map_cols
    }

# -----------------------------------------------------------------------------
# ROBOT CLEANING LOGIC
# -----------------------------------------------------------------------------
# This function handles the step-by-step movement of the robot.

def run_cleaning(start_x: int, start_y: int, actions: list, premium: bool = False):
    """
    - start_x, start_y: the initial coordinates of the robot.
    - actions: a list of dictionaries, each with "direction" and "steps".
      e.g. [ {"direction":"east","steps":2}, ... ]
    - premium: if True, skip adding tiles to "cleaned" if they've already been cleaned.

    Returns: (cleaned_tiles_list, final_state)
      cleaned_tiles_list -> all tiles visited/cleaned
      final_state -> "completed" if no collision, "error" if collision occurs
    """

    # Check if the starting position is within bounds AND walkable.
    if not (0 <= start_x < map_cols and 0 <= start_y < map_rows):
        return [], "error"  # out of bounds => error
    if not map_data.get((start_x, start_y), False):
        return [], "error"  # not walkable => error

    # Use a set to track cleaned tiles (set avoids duplicates).
    cleaned_tiles = set()
    # Clean the starting tile.
    cleaned_tiles.add((start_x, start_y))

    # Current position starts at the provided start_x, start_y.
    current_x, current_y = start_x, start_y

    # Iterate through each action in the list.
    for action in actions:
        # Direction is one of "north", "south", "east", "west".
        direction = action["direction"]
        # Steps is how many times we move in that direction.
        steps = action["steps"]

        # Move step by step in the given direction.
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
                # Invalid direction => return partial result + error.
                return list(cleaned_tiles), "error"

            # After moving, check if we're in a valid, walkable tile.
            if not (0 <= current_x < map_cols and 0 <= current_y < map_rows):
                return list(cleaned_tiles), "error"
            if not map_data.get((current_x, current_y), False):
                return list(cleaned_tiles), "error"

            # If "premium" is True, skip cleaning if it's already cleaned.
            # If "premium" is False, we always clean the new tile.
            if not premium or (premium and (current_x, current_y) not in cleaned_tiles):
                cleaned_tiles.add((current_x, current_y))

    # If we finish all actions without error, return the list of cleaned tiles and "completed".
    return list(cleaned_tiles), "completed"

# -----------------------------------------------------------------------------
# ENDPOINT: /clean
# -----------------------------------------------------------------------------
# Takes a JSON body with start_x, start_y, actions, and premium.
# Logs the session in the in-memory list, and returns the result.

@app.post("/clean")
def clean_endpoint(
    start_x: int = Body(...),  # Body(...) indicates we read this from the JSON body.
    start_y: int = Body(...),
    actions: list = Body(...),
    premium: bool = Body(False)
):
    """
    The main cleaning endpoint:
      - start_x, start_y: the initial coordinates for the robot.
      - actions: a list of moves (direction + steps).
      - premium: whether to skip re-cleaning already cleaned tiles.
    On collision, return an error. Otherwise, return the cleaned tiles.
    """

    # Use the global session_id variable to assign an ID to this session.
    global session_id

    # Record the start time in UTC (naive datetime). 
    # We also record a timestamp in seconds to measure duration.
    start_time = datetime.utcnow()
    start_timestamp = time.time()

    # Run the cleaning logic to get cleaned tiles + final state.
    cleaned_tiles, final_state = run_cleaning(start_x, start_y, actions, premium)

    # Record the end time and measure the duration.
    end_time = datetime.utcnow()
    end_timestamp = time.time()
    duration_seconds = end_timestamp - start_timestamp

    # Build a dictionary describing this session.
    session_data = {
        "id": session_id,
        "start_time": start_time.isoformat(),   # convert datetime to string
        "end_time": end_time.isoformat(),
        "final_state": final_state,
        "actions_count": len(actions),
        "tiles_cleaned": len(cleaned_tiles),
        "duration_seconds": duration_seconds
    }

    # Append the session info to our in-memory list.
    cleaning_history.append(session_data)
    # Increment the session ID for the next call.
    session_id += 1

    # Prepare the response JSON.
    response_body = {
        "cleaned_tiles": cleaned_tiles,
        "final_state": final_state
    }

    # If final_state is "error", we raise an HTTP 400 with partial data.
    if final_state == "error":
        raise HTTPException(status_code=400, detail=response_body)

    # Otherwise, everything went well; return a 200 with the cleaned tiles.
    return JSONResponse(content=response_body, status_code=200)

# -----------------------------------------------------------------------------
# 9) ENDPOINT: /history
# -----------------------------------------------------------------------------
# Returns a CSV dump of all stored sessions in memory.

@app.get("/history")
def get_history():
    """
    Returns a CSV of all past cleaning sessions stored in memory.
    Columns: id, start_time, end_time, final_state, actions_count, tiles_cleaned, duration_seconds
    """
    # Create a StringIO object to store CSV data in memory.
    output = io.StringIO()
    # Create a CSV writer to write rows into this "output".
    writer = csv.writer(output)

    # Write a header row.
    writer.writerow([
        "id", 
        "start_time", 
        "end_time", 
        "final_state", 
        "actions_count", 
        "tiles_cleaned", 
        "duration_seconds"
    ])

    # Write each session in "cleaning_history" as a row.
    for session in cleaning_history:
        writer.writerow([
            session["id"],
            session["start_time"],
            session["end_time"],
            session["final_state"],
            session["actions_count"],
            session["tiles_cleaned"],
            session["duration_seconds"]
        ])

    # Move the cursor to the start of the StringIO stream.
    output.seek(0)

    # Return the stream as a CSV file using StreamingResponse.
    return StreamingResponse(output, media_type="text/csv")
