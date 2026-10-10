"""Trace ingest carries prompt version and sampling metadata end to end."""
from __future__ import annotations

import uuid

from conftest import PROJECT


def _ingest(client, **extra):
    body = {
        "project": PROJECT,
        "case_id": f"case-{uuid.uuid4().hex[:8]}",
        "input": {"q": "refund status"},
        "output": {"answer": "approved"},
        "total_latency_ms": 42.0,
        "status": "completed",
        **extra,
    }
    r = client.post("/v1/traces", json=body)
    assert r.status_code == 201, r.text
    return r.json()


def test_ingest_returns_prompt_fields(client):
    tag = f"refund-{uuid.uuid4().hex[:6]}"
    data = _ingest(
        client, prompt_name=tag, prompt_version="v3", environment="production",
        metadata={"sample_rate": 0.25, "sampled": True},
    )
    assert data["prompt_name"] == tag
    assert data["prompt_version"] == "v3"
    assert data["environment"] == "production"
    assert data["sampled"] is True

    detail = client.get(f"/v1/traces/{data['trace_id']}").json()
    assert detail["prompt_version"] == "v3"
    assert detail["raw_trace"]["metadata"] == {"sample_rate": 0.25, "sampled": True}


def test_legacy_payload_without_prompt(client):
    data = _ingest(client, environment=None)
    assert data["prompt_name"] is None
    assert data["sampled"] is None
    assert data["environment"] == "development"


def test_list_filters_by_prompt(client):
    tag = f"triage-{uuid.uuid4().hex[:6]}"
    v1 = _ingest(client, prompt_name=tag, prompt_version="v1")
    v2 = _ingest(client, prompt_name=tag, prompt_version="v2")
    _ingest(client, prompt_name=f"{tag}-other", prompt_version="v1")

    by_name = client.get("/v1/traces", params={"project": PROJECT, "prompt_name": tag}).json()
    assert {t["trace_id"] for t in by_name} == {v1["trace_id"], v2["trace_id"]}

    by_version = client.get(
        "/v1/traces", params={"project": PROJECT, "prompt_name": tag, "prompt_version": "v2"},
    ).json()
    assert [t["trace_id"] for t in by_version] == [v2["trace_id"]]


def test_prompt_filter_treats_wildcards_literally(client):
    tag = f"pct-{uuid.uuid4().hex[:6]}"
    _ingest(client, prompt_name=f"{tag}-abc", prompt_version="v1")
    r = client.get("/v1/traces", params={"project": PROJECT, "prompt_name": f"{tag}%"}).json()
    assert r == []
