from fastapi import FastAPI

app = FastAPI(title="TerraScope Data Pipeline")


@app.get("/health")
def health() -> dict[str, str]:
    return {"service": "data-pipeline", "status": "ok"}

