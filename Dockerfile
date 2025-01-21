FROM python:3.13-slim

WORKDIR /app

COPY requirements.txt .

RUN pip install --no-cache-dir --upgrade pip && \
    pip install --no-cache-dir -r requirements.txt

COPY ccbot.py .

CMD ["sh", "-c", "export SLACK_WEBHOOK_URL=$(cat /run/secrets/slack_webhook_url) && python app.py"]

CMD ["python", "ccbot.py"]
