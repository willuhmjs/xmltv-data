FROM python:3.11-slim

WORKDIR /app

RUN pip install --no-cache-dir requests

COPY tvtv2xmltv_cron.py .

RUN chmod +x tvtv2xmltv_cron.py

CMD ["python", "tvtv2xmltv_cron.py"]
