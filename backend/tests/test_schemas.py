"""Tests de los contratos Pydantic de solicitudes y eventos."""

from __future__ import annotations

import pytest
from pydantic import ValidationError

from src.schemas import (FeedbackEvent, ImpressionEvent, RecommendationRequest,
                         RecommendationResponse)


def test_valid_request_normalizes_and_dedupes():
    req = RecommendationRequest.model_validate({
        "session_id": " sess-001 ",
        "cart": [24852, 13176, 24852],
        "navigation": [{"type": "view", "product_id": 47209}],
        "recent_history": [[24852, 13176], [47209, 47209]],
        "rejected": [22935, 22935],
        "inventory": {"21137": True, "22935": False},
        "k": 3,
    })
    assert req.session_id == "sess-001"
    assert req.cart == [24852, 13176]
    assert req.rejected == [22935]
    assert req.recent_history == [[24852, 13176], [47209]]
    assert req.inventory == {"21137": True, "22935": False}


@pytest.mark.parametrize("k", [0, 11, -1])
def test_k_bounds(k: int):
    with pytest.raises(ValidationError):
        RecommendationRequest(session_id="s", cart=[1], k=k)


@pytest.mark.parametrize("bad_cart", [[0], [-3], [1, -1]])
def test_cart_ids_must_be_positive(bad_cart: list[int]):
    with pytest.raises(ValidationError):
        RecommendationRequest(session_id="s", cart=bad_cart)


@pytest.mark.parametrize("bad_session", ["", "   "])
def test_session_id_not_empty(bad_session: str):
    with pytest.raises(ValidationError):
        RecommendationRequest(session_id=bad_session, cart=[1])


def test_inventory_must_be_boolean():
    with pytest.raises(ValidationError):
        RecommendationRequest(session_id="s", inventory={"1": "yes"})


def test_inventory_keys_must_be_numeric():
    with pytest.raises(ValidationError):
        RecommendationRequest(session_id="s", inventory={"abc": True})


def test_feedback_event_literal():
    with pytest.raises(ValidationError):
        FeedbackEvent(session_id="s", product_id=1, event="clicked")
    ev = FeedbackEvent(session_id="s", product_id=1, event="accepted")
    assert ev.event == "accepted"


def test_impression_requires_positive_ids():
    with pytest.raises(ValidationError):
        ImpressionEvent(session_id="s", recommendation_ids=[1, 0])


def test_recent_history_rejects_bad_ids():
    with pytest.raises(ValidationError):
        RecommendationRequest(session_id="s", recent_history=[[1, -2]])


def test_response_model_shape():
    resp = RecommendationResponse.model_validate({
        "session_id": "s",
        "recommendations": [{"product_id": 1, "score": 0.5, "reason": "r",
                             "source": "association_rule"}],
        "fallback": False,
        "model_version": "v",
        "latency_ms": 1.0,
    })
    assert resp.recommendations[0].source == "association_rule"
