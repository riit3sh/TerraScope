FROM python:3.11-slim
WORKDIR /app
COPY ml-models/requirements.txt ml-models/pyproject.toml ./
COPY ml-models/src ./src
COPY ml-models/change_detection ./change_detection
COPY ml-models/rag_pipeline ./rag_pipeline
COPY ml-models/scoring_engine ./scoring_engine
COPY ml-models/pipeline.py ./pipeline.py
COPY docs/schema ./docs/schema
RUN pip install --no-cache-dir -r requirements.txt && pip install --no-cache-dir .
EXPOSE 8002
CMD ["uvicorn", "pipeline:app", "--host", "0.0.0.0", "--port", "8002"]
