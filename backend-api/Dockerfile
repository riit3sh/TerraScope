FROM python:3.11-slim
WORKDIR /app
COPY requirements.txt pyproject.toml ./
COPY src ./src
COPY routers ./routers
RUN pip install --no-cache-dir -r requirements.txt && pip install --no-cache-dir .
EXPOSE 8000
CMD ["uvicorn", "terrascope_backend_api.main:app", "--host", "0.0.0.0", "--port", "8000"]

