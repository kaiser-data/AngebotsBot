"""Unit tests for agents.store_node batch upsert path."""

from unittest.mock import MagicMock, patch

from agents.store_node import store_node


def _offer(ext: str) -> dict:
    return {
        "external_id": ext,
        "title": f"Offer {ext}",
        "url": f"https://example/{ext}",
        "price": 1.99,
        "store": "Lidl",
        "category": "Milch",
    }


def test_store_node_batches_upsert_via_shared_helper():
    offers = [_offer("a"), _offer("b")]
    returned = [
        {"id": "uuid-a", "external_id": "a"},
        {"id": "uuid-b", "external_id": "b"},
    ]

    with patch("agents.store_node.upsert_offers", return_value=returned) as upsert:
        with patch("agents.store_node.get_supabase") as get_sb:
            with patch("providers.embeddings.drain_embedding_queue", return_value=0):
                result = store_node({"scraped_offers": offers, "analyzed_offers": []})

    upsert.assert_called_once_with(offers)
    get_sb.assert_not_called()  # no analyses → no extra client use required
    assert result == {"offers_stored": ["uuid-a", "uuid-b"], "db_errors": []}


def test_store_node_upserts_analyses_in_batch_when_present():
    offers = [_offer("a")]
    returned = [{"id": "uuid-a", "external_id": "a"}]
    analyses = [{
        "external_id": "a",
        "product_name": "Milch",
        "brand": "Ja!",
        "condition": "neu",
        "key_features": ["1L"],
        "quality_score": 8,
        "deal_verdict": "Gut",
        "tags": ["milch"],
        "raw_llm_response": "{}",
    }]

    sb = MagicMock()
    sb.table.return_value.upsert.return_value.execute.return_value = MagicMock(data=[])

    with patch("agents.store_node.upsert_offers", return_value=returned):
        with patch("agents.store_node.get_supabase", return_value=sb):
            with patch("providers.embeddings.drain_embedding_queue", return_value=0):
                result = store_node({
                    "scraped_offers": offers,
                    "analyzed_offers": analyses,
                })

    sb.table.assert_called_with("offer_analyses")
    assert result["offers_stored"] == ["uuid-a"]
    assert result["db_errors"] == []


def test_store_node_empty_offers():
    assert store_node({"scraped_offers": [], "analyzed_offers": []}) == {
        "offers_stored": [],
        "db_errors": [],
    }
