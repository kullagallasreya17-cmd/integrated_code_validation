# Build context is the repo root (see docker-compose.yml `build.context: .`)
FROM python:3.11-slim

WORKDIR /service

COPY services/orchestrator-service/requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY services/orchestrator-service/app ./app
COPY shared ./shared

ENV PYTHONPATH=/service

EXPOSE 8000

CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
