# FlightGrab – use with Render Docker runtime if Python build isn't available
FROM python:3.11-slim

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . .

# Render injects PORT at runtime
EXPOSE 10000
CMD uvicorn app:app --host 0.0.0.0 --port $PORT
