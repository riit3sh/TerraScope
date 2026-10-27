"""Land Analyst provider choice: DeepInfra when its key is set, else Groq, else none."""

from __future__ import annotations

import json

import land_analyst


def test_deepinfra_wins_then_groq_then_none(monkeypatch) -> None:
    monkeypatch.setenv("GROQ_API_KEY", "gsk-test")
    monkeypatch.setenv("DEEPINFRA_API_KEY", "di-test")
    monkeypatch.delenv("DEEPINFRA_MODEL", raising=False)
    assert land_analyst.ai_provider()["name"] == "DeepInfra"
    assert land_analyst.ai_provider()["model"] == land_analyst.DEEPINFRA_DEFAULT_MODEL
    monkeypatch.delenv("DEEPINFRA_API_KEY")
    assert land_analyst.ai_provider()["name"] == "Groq"
    monkeypatch.setenv("GROQ_API_KEY", "demo-groq-api-key")
    assert land_analyst.ai_provider() is None


def test_deepinfra_request_uses_its_url_model_and_no_groq_only_fields(monkeypatch) -> None:
    monkeypatch.delenv("GROQ_API_KEY", raising=False)
    monkeypatch.setenv("DEEPINFRA_API_KEY", "di-test")
    monkeypatch.setenv("DEEPINFRA_MODEL", "some/model")
    sent = {}

    class Response:
        status_code = 200
        headers: dict = {}

        def raise_for_status(self):
            pass

        def json(self):
            return {"choices": [{"message": {"content": json.dumps({"answer_text": "Chinnambedu Road", "citations": []})}}]}

    def post(url, headers, json, timeout):
        sent.update(url=url, auth=headers["Authorization"], payload=json)
        return Response()

    monkeypatch.setattr(land_analyst.requests, "post", post)
    answer = land_analyst.ask_land_question({"evidence": []}, "name of the road")
    assert answer["answer_text"] == "Chinnambedu Road"
    assert sent["url"] == land_analyst.DEEPINFRA_API_URL and sent["auth"] == "Bearer di-test"
    assert sent["payload"]["model"] == "some/model"
    assert "include_reasoning" not in sent["payload"] and "reasoning_effort" not in sent["payload"]
