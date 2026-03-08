import requests
import json

# Define the backtest request
# Feel free to change the parameters
backtest_request = {
    "start_date": "2023-01-01",
    "end_date": "2023-12-31",
    "symbol": "AAPL",
    "strategy": "constant_threshold",
    "threshold": 150.0,
    "hold_bars": 5,
}

# Send the request to the backend
# Make sure the backend is running before executing this script
print("Sending backtest request...")
try:
    response = requests.post("http://127.0.0.1:8000/api/backtest", json=backtest_request)
    response.raise_for_status()  # Raise an exception for bad status codes

    # Print the response
    print("Backtest successful!")
    print(json.dumps(response.json(), indent=2))

except requests.exceptions.RequestException as e:
    print(f"An error occurred: {e}")
    print("Please make sure the backend is running and accessible at http://127.0.0.1:8000")

