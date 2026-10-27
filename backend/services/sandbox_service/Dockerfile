FROM mcr.microsoft.com/dotnet/sdk:8.0-bookworm-slim AS dotnet-sdk

FROM python:3.11-slim-bookworm

WORKDIR /app

RUN apt-get update && apt-get install -y --no-install-recommends \
    ca-certificates \
    default-jdk-headless \
    gcc \
    g++ \
    golang-go \
    mono-mcs \
    mono-runtime \
    libmono-system-data4.0-cil \
    nodejs \
    node-typescript \
    npm \
    cppcheck \
    checkstyle \
    libcommons-cli-java \
    && npm install --global eslint@9 \
    && rm -rf /var/lib/apt/lists/*

COPY --from=dotnet-sdk /usr/share/dotnet /usr/share/dotnet
RUN ln -s /usr/share/dotnet/dotnet /usr/bin/dotnet

ENV DOTNET_ROOT=/usr/share/dotnet

COPY backend/services/sandbox_service/checkstyle.xml /opt/coding-validation-checkstyle.xml

COPY backend/services/sandbox_service/requirements.txt .

RUN pip install --no-cache-dir -r requirements.txt

COPY backend/services/sandbox_service/app ./app
COPY backend/shared ./shared

ENV PYTHONPATH=/app

EXPOSE 8004

CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8004"]