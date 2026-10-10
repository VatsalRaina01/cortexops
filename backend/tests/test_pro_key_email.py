"""Pro key provisioning sends the key by email automatically (Stripe + PayPal) and can be re-sent by admins."""
from __future__ import annotations

import json
import re
import uuid

import pytest
from app.services import email as email_service
from conftest import INTERNAL_KEY

ADMIN = {"X-Internal-Key": INTERNAL_KEY}


class Outbox:
    def __init__(self):
        self.sent: list[dict] = []
        self.fail: set[str] = set()

    def provider(self, name):
        async def _send(api_key, to, subject, text):
            if name in self.fail:
                return False
            self.sent.append({"provider": name, "to": to, "subject": subject, "text": text})
            return True
        return _send

    def raw_key(self, i: int = -1) -> str:
        return re.search(r"export CORTEXOPS_API_KEY=(\S+)", self.sent[i]["text"]).group(1)


@pytest.fixture
def outbox(monkeypatch):
    box = Outbox()
    monkeypatch.setattr(email_service, "_send_resend", box.provider("resend"))
    monkeypatch.setattr(email_service, "_send_sendgrid", box.provider("sendgrid"))
    monkeypatch.setenv("RESEND_API_KEY", "re_test")
    monkeypatch.setenv("SENDGRID_API_KEY", "SG.test")
    return box


def _project() -> str:
    return f"proj-{uuid.uuid4().hex[:8]}"


def _stripe_checkout(client, project: str, *, metadata_email: str | None, customer_email: str | None = None):
    sess = {"id": f"cs_test_{uuid.uuid4().hex}", "metadata": {"project": project}}
    if metadata_email:
        sess["metadata"]["email"] = metadata_email
    if customer_email:
        sess["customer_details"] = {"email": customer_email}
    event = {"type": "checkout.session.completed", "data": {"object": sess}}
    r = client.post("/v1/billing/webhook/stripe", content=json.dumps(event))
    assert r.status_code == 200, r.text
    return r.json()


def _keys(client, project: str) -> list[dict]:
    return client.get("/v1/admin/keys", params={"project": project}, headers=ADMIN).json()


def _audit(client, project: str) -> list[dict]:
    return client.get("/v1/admin/auth-audit", params={"project": project}, headers=ADMIN).json()


def test_stripe_checkout_provisions_and_emails_key(client, outbox):
    project = _project()
    body = _stripe_checkout(client, project, metadata_email="dev@acme.io")
    assert body["provision"] == "provisioned"
    assert body["email"] == "sent"

    assert len(outbox.sent) == 1
    mail = outbox.sent[0]
    assert mail["provider"] == "resend"
    assert mail["to"] == "dev@acme.io"
    assert project in mail["text"]
    assert outbox.raw_key().startswith("cxo-")

    keys = _keys(client, project)
    assert [(k["tier"], k["is_active"]) for k in keys] == [("pro", True)]
    events = {(a["event"], a["outcome"]) for a in _audit(client, project)}
    assert ("pro_key_provisioned", "success") in events
    assert ("pro_key_email", "success") in events


def test_stripe_webhook_retry_is_idempotent(client, outbox):
    project = _project()
    _stripe_checkout(client, project, metadata_email="dev@acme.io")
    retry = _stripe_checkout(client, project, metadata_email="dev@acme.io")
    assert retry["provision"] == "already_provisioned"
    assert len(_keys(client, project)) == 1
    assert len(outbox.sent) == 1


def test_stripe_falls_back_to_customer_details_email(client, outbox):
    project = _project()
    _stripe_checkout(client, project, metadata_email=None, customer_email="billing@acme.io")
    assert outbox.sent[0]["to"] == "billing@acme.io"


def test_resend_failure_falls_back_to_sendgrid(client, outbox):
    outbox.fail.add("resend")
    project = _project()
    body = _stripe_checkout(client, project, metadata_email="dev@acme.io")
    assert body["email"] == "sent"
    assert outbox.sent[0]["provider"] == "sendgrid"


def test_undelivered_email_is_audited(client, monkeypatch):
    project = _project()
    body = _stripe_checkout(client, project, metadata_email="dev@acme.io")
    assert body["email"] == "not_configured"
    events = {(a["event"], a["outcome"], a["detail"]) for a in _audit(client, project)}
    assert ("pro_key_email", "failure", "status=not_configured") in events


def test_paypal_activation_provisions_and_emails_key(client, outbox):
    project = _project()
    event = {
        "event_type": "BILLING.SUBSCRIPTION.ACTIVATED",
        "resource": {
            "id": f"I-{uuid.uuid4().hex[:12].upper()}",
            "custom_id": project,
            "subscriber": {"email_address": "owner@acme.io"},
        },
    }
    r = client.post("/v1/billing/paypal/webhook", content=json.dumps(event))
    assert r.status_code == 200, r.text
    assert r.json()["email"] == "sent"
    assert outbox.sent[0]["to"] == "owner@acme.io"

    again = client.post("/v1/billing/paypal/webhook", content=json.dumps(event))
    assert again.json() == {"status": "already_provisioned"}
    assert len(outbox.sent) == 1


def test_admin_resend_rotates_and_emails_new_key(client, outbox):
    project = _project()
    _stripe_checkout(client, project, metadata_email="dev@acme.io")
    old = _keys(client, project)[0]
    first_raw = outbox.raw_key()

    r = client.post(f"/v1/admin/keys/{old['id']}/resend-email", json={"email": "dev@acme.io"}, headers=ADMIN)
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["old_key_id"] == old["id"]
    assert "cxo-" not in json.dumps(body)

    second_raw = outbox.raw_key()
    assert second_raw != first_raw
    keys = {k["id"]: k for k in _keys(client, project)}
    assert keys[old["id"]]["is_active"] is False
    assert keys[body["new_key_id"]]["is_active"] is True
    assert keys[body["new_key_id"]]["tier"] == "pro"


def test_admin_resend_failure_leaves_key_unchanged(client, outbox):
    project = _project()
    _stripe_checkout(client, project, metadata_email="dev@acme.io")
    old = _keys(client, project)[0]
    outbox.fail.update({"resend", "sendgrid"})

    r = client.post(f"/v1/admin/keys/{old['id']}/resend-email", json={"email": "dev@acme.io"}, headers=ADMIN)
    assert r.status_code == 502
    keys = _keys(client, project)
    assert [(k["id"], k["is_active"]) for k in keys] == [(old["id"], True)]


def test_admin_resend_requires_internal_key(client):
    r = client.post("/v1/admin/keys/whatever/resend-email", json={"email": "dev@acme.io"})
    assert r.status_code == 401
