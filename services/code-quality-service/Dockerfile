# Build context is the repo root (see docker-compose.yml `build.context: .`)
# so this Dockerfile can pull in the shared/ package alongside the service.
FROM python:3.11-slim

WORKDIR /service

COPY services/code-quality-service/requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY services/code-quality-service/app ./app
COPY shared ./shared

ENV PYTHONPATH=/service

EXPOSE 8000

CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
