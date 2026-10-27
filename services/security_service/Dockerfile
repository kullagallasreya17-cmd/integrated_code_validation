FROM golang:1.23-alpine AS gitleaks-build

RUN go install github.com/zricethezav/gitleaks/v8@v8.21.2

FROM python:3.12-slim

WORKDIR /service

COPY services/security_service/requirements.txt ./requirements.txt
RUN pip install --no-cache-dir -r requirements.txt

COPY --from=gitleaks-build /go/bin/gitleaks /usr/local/bin/gitleaks
COPY services/security_service/app ./app

EXPOSE 8000

CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]