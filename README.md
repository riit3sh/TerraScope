# TerraScope

TerraScope is a local-first geospatial intelligence platform scaffold for bringing together satellite data ingestion, change detection, retrieval-augmented workflows, scoring, and a web interface. This repository contains only the service boundaries and developer tooling needed to begin implementation; it intentionally has no business logic yet.

## Folder Structure

```text
terrascope/
├── docs/schema/                    # Shared data and API schema notes
├── data-pipeline/                  # Data ingestion package and connectors
│   ├── connectors/
│   ├── db/
│   └── src/terrascope_data_pipeline/
├── ml-models/                      # ML service package and model areas
│   ├── change_detection/
│   ├── rag_pipeline/
│   ├── scoring_engine/
│   └── src/terrascope_ml_models/
├── backend-api/                    # Public API package
│   ├── routers/
│   └── src/terrascope_backend_api/
├── frontend/                       # Vite + React + TypeScript + Tailwind app
├── docker-compose.yml              # Local development services
├── .env.example                    # Placeholder environment variables
└── README.md
```

## Local Development

1. Copy `.env.example` to `.env` and adjust values for your local environment if needed.
2. Start the local stack:

   ```bash
   docker-compose up --build
   ```

3. Open the frontend at [http://localhost:5173](http://localhost:5173). The service endpoints are available at `http://localhost:8000`, `http://localhost:8001`, and `http://localhost:8002`.

The Compose stack is for local demo use only. Service-to-service URLs use Compose service names such as `http://data-pipeline:8001` and `http://ml-models:8002` inside the network.

## Contributing

Work is organized by track. Create a branch for the area you are changing: `data-integration`, `ml-pipeline`, or `frontend-ui`. Keep commits focused, open a pull request from the track branch into `main`, and wait for review before merging. Cross-track changes should still have a clear primary track and call out any coordination needs in the pull request description.

