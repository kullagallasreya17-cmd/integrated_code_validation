FROM python:3.12-slim

WORKDIR /service

RUN apt-get update \
	&& apt-get install -y --no-install-recommends socat \
	&& rm -rf /var/lib/apt/lists/*

COPY services/repair-service/requirements.txt ./requirements.txt
RUN pip install --no-cache-dir -r requirements.txt

COPY app ./app

EXPOSE 8000

CMD ["sh", "-c", "socat TCP-LISTEN:11434,bind=127.0.0.1,fork,reuseaddr TCP:host.docker.internal:${OLLAMA_HOST_PORT:-11434} & exec uvicorn app.main:app --host 0.0.0.0 --port 8000"]