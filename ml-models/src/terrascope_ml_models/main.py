from fastapi import FastAPI

app = FastAPI(title="TerraScope ML Models")


@app.get("/health")
def health() -> dict[str, str]:
    return {"service": "ml-models", "status": "ok"}

