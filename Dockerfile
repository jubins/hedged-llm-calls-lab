FROM python:3.12-slim
WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
COPY hedgekit hedgekit
COPY upstream upstream
COPY gateway gateway
EXPOSE 8000 8080
