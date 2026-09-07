from fastapi import FastAPI

from routers.parcels import router as parcels_router
from fastapi.middleware.cors import CORSMiddleware
import os

app = FastAPI(title="TerraScope Backend API")

frontend_url = os.getenv("FRONTEND_URL", "http://localhost:5173")
app.add_middleware(
    CORSMiddleware,
    allow_origins=[frontend_url],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(parcels_router)


@app.get("/health")
def health() -> dict[str, str]:
    return {"service": "backend-api", "status": "ok"}
