FROM python:3.11-slim
WORKDIR /app
COPY data-pipeline/requirements.txt data-pipeline/pyproject.toml ./
COPY data-pipeline/src ./src
COPY data-pipeline/connectors ./connectors
COPY data-pipeline/db ./db
COPY data-pipeline/etl_pipeline.py data-pipeline/internal_api.py ./
COPY docs/schema ./docs/schema
RUN pip install --no-cache-dir -r requirements.txt && pip install --no-cache-dir .
EXPOSE 8001
CMD ["uvicorn", "internal_api:app", "--host", "0.0.0.0", "--port", "8001"]
