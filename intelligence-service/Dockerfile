FROM python:3.11-slim

WORKDIR /app

COPY intelligence-service/requirements.txt ./intelligence-service/requirements.txt

RUN pip install --no-cache-dir -r intelligence-service/requirements.txt

COPY intelligence-service ./intelligence-service
COPY shared-contracts ./shared-contracts

WORKDIR /app/intelligence-service

EXPOSE 8004

CMD ["python", "-m", "uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8004"]

