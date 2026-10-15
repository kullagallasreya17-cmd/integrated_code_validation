FROM python:3.12-slim

WORKDIR /service

COPY services/bug-resource-service/requirements.txt ./requirements.txt
RUN pip install --no-cache-dir -r requirements.txt

COPY services/bug-resource-service/app ./app
COPY shared ./shared

RUN useradd --create-home --shell /usr/sbin/nologin appuser && chown -R appuser:appuser /service
USER appuser

EXPOSE 8000

CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]