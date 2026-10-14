"""Run the Review 2 local RAG demonstration."""

from __future__ import annotations

import json

# Only fall back to sibling imports when run as a script; inside the package a
# failed import (e.g. chromadb missing) must surface as itself.
if __package__:
    from .ingest import build_vector_index
    from .reason import generate_grounded_answer
    from .sample_documents import SAMPLE_DOCUMENTS
else:  # pragma: no cover - direct script execution.
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
