# TerraScope Architecture

TerraScope separates evidence collection from investor-specific evaluation. The evidence snapshot is collected once and treated as immutable; changing sliders, profiles, property types, horizons, or preferences only re-runs the fast evaluation layer.

```mermaid
graph TD
    frontend[frontend]
    backend[backend-api]
    pipeline[data-pipeline]
    ml[ml-models]
    postgres[(postgres)]

    evidence[Immutable Evidence Snapshot]
    evaluation[Fast Evaluation Layer]
    settings[Slider / profile / property type / horizon / preference changes]

    appeears[NASA AppEEARS / HLS]
    osm[OpenStreetMap Overpass / Nominatim]
    elevation[Open-Elevation]
    groq[Groq API]
    rera[RERA seed dataset]
    uploads[User uploaded documents]

    frontend -->|search, draw AOI, configure evaluation| backend
    backend -->|build evidence once| pipeline
    pipeline -->|persist factual snapshot| evidence
    evidence -->|immutable record| postgres
    backend -->|evaluate snapshot + settings| ml
    evidence -->|read-only input| ml
    ml -->|store evaluation and verdict history| postgres

    pipeline --> appeears
    pipeline --> osm
    pipeline --> elevation
    pipeline --> rera
    backend -->|attach evidence| uploads
    ml -->|grounded reasoning when documents/API key exist| groq
    uploads -->|retrieval context| ml

    settings -->|changes only| evaluation
    evaluation -->|weighted rule-based scores, verdict, sensitivity| ml
    ml -.->|does not recollect satellite, OSM, elevation, or RERA evidence| pipeline

    subgraph COLLECTION[Immutable Evidence Snapshot]
        pipeline
        evidence
        appeears
        osm
        elevation
        rera
    end

    subgraph DECISION[Fast Evaluation Layer]
        settings
        evaluation
        ml
        groq
        uploads
    end
```

## Separation Of Responsibilities

- **Immutable Evidence Snapshot:** the blocking, factual collection stage. It uses the user-defined GeoJSON polygon as the canonical AOI, gathers satellite, infrastructure, elevation, RERA, and uploaded-document evidence, then persists the snapshot.
- **Fast Evaluation Layer:** the deterministic decision stage. It reads the immutable snapshot and applies profile-specific weights and preferences. Slider and profile changes stay here and must not call satellite, OSM, elevation, or RERA connectors again.
