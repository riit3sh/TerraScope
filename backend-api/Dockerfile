FROM python:3.11-slim
WORKDIR /app
# Built from the repository root so the shared valuation package is in context.
COPY backend-api/requirements.txt backend-api/pyproject.toml ./
COPY backend-api/src ./src
COPY backend-api/routers ./routers
COPY valuation ./valuation
RUN pip install --no-cache-dir --retries 10 --timeout 180 -r requirements.txt && pip install --no-cache-dir .
EXPOSE 8000
CMD ["uvicorn", "terrascope_backend_api.main:app", "--host", "0.0.0.0", "--port", "8000"]
