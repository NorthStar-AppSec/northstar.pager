FROM python:3.13-slim
RUN pip install --no-cache-dir "anthropic>=1,<2"
WORKDIR /app
COPY alert.py .
ENV ALERT_DB=/data/alerts.db PYTHONUNBUFFERED=1
RUN python alert.py --check
CMD ["python", "alert.py"]
