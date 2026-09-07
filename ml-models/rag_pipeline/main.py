"""Run the Review 2 local RAG demonstration."""

from __future__ import annotations

import json

try:
    from .ingest import build_vector_index
    from .reason import generate_grounded_answer
    from .sample_documents import SAMPLE_DOCUMENTS
except ImportError:  # pragma: no cover - supports direct script execution.
    from ingest import build_vector_index
    from reason import generate_grounded_answer
    from sample_documents import SAMPLE_DOCUMENTS


if __name__ == "__main__":
    index_result = build_vector_index(SAMPLE_DOCUMENTS)
    answer = generate_grounded_answer(
        "Is this parcel's title clear and is there an active RERA registration?",
        "parcel-pune-001",
    )
    print(json.dumps({"index": index_result, "grounded_answer": answer}, indent=2))
