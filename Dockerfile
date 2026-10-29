FROM python:3.13-slim
ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1
WORKDIR /app
COPY requirements*.txt ./
RUN pip install --no-cache-dir -r requirements-production.txt && useradd --create-home shelf
COPY --chown=shelf:shelf app ./app
COPY --chown=shelf:shelf migrations ./migrations
COPY --chown=shelf:shelf wsgi.py ./
RUN mkdir -p /app/instance && chown shelf:shelf /app/instance
USER shelf
EXPOSE 8000
CMD ["gunicorn", "--bind", "0.0.0.0:8000", "--workers", "2", "--threads", "8", "--timeout", "120", "wsgi:app"]
