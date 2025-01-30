# Cleaning Robot REST API

This project implements a **Cleaning Robot** REST application in Python using **FastAPI**. The robot can be remotely controlled, accepts maps in `.txt` or `.json` format, and logs its cleaning sessions. Users can also download a CSV dump of previous sessions.

## Table of Contents

1. [Prerequisites](#prerequisites)  
2. [Project Structure](#project-structure)  
3. [Setup Instructions](#setup-instructions)  
4. [Running the Application](#running-the-application)  
5. [Experimenting With the API](#experimenting-with-the-api)  
6. [Example Endpoints](#example-endpoints)  
7. [Notes](#notes)  
8. [Troubleshooting](#troubleshooting)  
9. [License](#license)  
10. [Contact](#contact)  

---

## Prerequisites

- **Python 3.8+**  
- **pip** (or another Python package manager)

---

## Project Structure

A typical layout might look like:

```plaintext
my_cleaning_robot/
├── main.py              # Main FastAPI script (CSV-based approach)
├── map.txt              # Example text map
├── requirements.txt     # List of required libraries
├── session_history.csv  # CSV file with sessions (auto-created on first run)
└── README.md            # This file
```

---

## Setup Instructions

1. **Create and Activate a Virtual Environment**

   ```bash
   # Create a virtual environment named 'venv'
   python -m venv venv

   # Activate the virtual environment (Linux/Mac)
   source venv/bin/activate
   ```

2. **Install Required Dependencies**
    
    ```bash
    pip install -r requirements.txt
    ```

---

## Running the Application

1. **Launch the Server**
    
    ```bash
    uvicorn main:app --reload
    ```
   *(Ensure that `main.py` is the correct entry point. If `main_csv_file.py` is used, then rename it in the command above.)*

2. **Check Logs**
    
    You should see something like:
    ```bash
    INFO:     Uvicorn running on http://127.0.0.1:8000 (Press CTRL+C to quit)
    ```

---

## Example Endpoints

1. **Upload a map:**

   ```bash
    curl -X POST -F "file=@map.txt" http://127.0.0.1:8000/set-map
    ```
    
2. **Clean (/clean):**

    ```bash
    curl -X POST http://127.0.0.1:8000/clean      -H "Content-Type: application/json"      -d '{
           "start_x": 0,
           "start_y": 0,
           "actions": [
             {"direction":"east","steps":2},
             {"direction":"south","steps":1}
           ],
           "premium": false
         }'
    ```

3. **Get History (/history):**

    ```bash
    curl -X GET http://127.0.0.1:8000/history -O
    ```

---

## Notes

- Ensure that the map files are correctly formatted in `.txt` or `.json`.
- The `session_history.csv` file is auto-created on the first run if it doesn't exist.

---

## Troubleshooting

- **Issue:** Server doesn't start.
  - **Solution:** Ensure all dependencies are installed and the virtual environment is activated.

- **Issue:** Map upload fails.
  - **Solution:** Verify the map file format and structure.

---

## License

This project is licensed under the [MIT License](LICENSE).

---

## Contact

For any queries or support, please contact [your.email@example.com](mailto:your.email@example.com).
