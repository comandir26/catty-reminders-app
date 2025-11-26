FROM python:3.9-slim

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY app/ app/
COPY tests/ tests/
COPY testlib/ testlib/
COPY templates/ templates/
COPY static/ static/
COPY config.json .

CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8181"]

EXPOSE 8181