# Dev image (used by docker-compose.yml). For production use Dockerfile.prod at
# the repo root, which also bundles migrations + the entrypoint.
FROM python:3.11-slim
WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
COPY app ./app
EXPOSE 8000
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
