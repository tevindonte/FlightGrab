# Official Playwright Python image - includes Chromium + all system deps
FROM mcr.microsoft.com/playwright/python:v1.58.0-noble

WORKDIR /app

# Match Playwright version in requirements
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY main.py .

# Cloud Run sets PORT at runtime
ENV PORT=8080
EXPOSE 8080
CMD uvicorn main:app --host 0.0.0.0 --port ${PORT}
