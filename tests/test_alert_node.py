"""Unit tests for agents.alert_node."""

from unittest.mock import MagicMock, patch

from agents.alert_node import _extract_alert_config, _format_alerts_list, alert_node


def test_extract_alert_config_parses_json_from_llm_response():
    llm = MagicMock()
    llm.invoke.return_value = MagicMock(
        content='Antwort: {"name":"Kaffee","query_text":"kaffee","max_price":10}'
    )

    with patch("agents.alert_node.get_llm", return_value=llm):
        result = _extract_alert_config("kaffee bis 10 euro")

    assert result == {"name": "Kaffee", "query_text": "kaffee", "max_price": 10}


def test_extract_alert_config_falls_back_on_invalid_json():
    llm = MagicMock()
    llm.invoke.return_value = MagicMock(content="kein json")

    with patch("agents.alert_node.get_llm", return_value=llm):
        result = _extract_alert_config("sehr lange suchanfrage fuer testzwecke")

    assert result == {
        "name": "sehr lange suchanfrage fuer te",
        "query_text": "sehr lange suchanfrage fuer testzwecke",
    }


def test_format_alerts_list_empty():
    assert _format_alerts_list([]) == "Du hast noch keine aktiven Alerts."


def test_format_alerts_list_renders_optional_thresholds():
    alerts = [
        {
            "name": "Kaffee",
            "query_text": "bohnen",
            "max_price": 10,
            "min_discount": 20,
        }
    ]

    out = _format_alerts_list(alerts)

    assert "**Deine aktiven Alerts:**" in out
    assert "- **Kaffee**: bohnen | Max: €10 | Min: -20%" in out


def test_alert_node_requires_user_id():
    result = alert_node({"intent": "list_alerts", "user_query": "zeige alerts"})
    assert "musst du dich zuerst registrieren" in result["final_response"]


@patch("agents.alert_node.list_alerts")
def test_alert_node_list_branch(list_alerts_mock):
    list_alerts_mock.return_value = [{"name": "Kaffee", "query_text": "bohnen"}]

    result = alert_node(
        {
            "intent": "list_alerts",
            "user_query": "zeige alerts",
            "alert_config": {"user_id": "u1"},
        }
    )

    list_alerts_mock.assert_called_once_with("u1")
    assert result["active_alerts"] == [{"name": "Kaffee", "query_text": "bohnen"}]
    assert "Kaffee" in result["final_response"]


@patch("agents.alert_node.list_alerts", return_value=[{"name": "Kaffee", "query_text": "bohnen"}])
def test_alert_node_delete_missing_id_lists_alerts(_list_alerts_mock):
    result = alert_node(
        {
            "intent": "delete_alert",
            "user_query": "loesche kaffe alert",
            "alert_config": {"user_id": "u1"},
        }
    )

    assert "Bitte nenne die ID des Alerts" in result["final_response"]
    assert "Kaffee" in result["final_response"]


@patch("agents.alert_node.delete_alert", return_value=True)
def test_alert_node_delete_success(delete_alert_mock):
    result = alert_node(
        {
            "intent": "delete_alert",
            "user_query": "loesche kaffe alert",
            "alert_config": {"user_id": "u1", "alert_id": "a1"},
        }
    )

    delete_alert_mock.assert_called_once_with("u1", "a1")
    assert result["final_response"] == "Alert gelöscht ✓"


@patch("agents.alert_node.create_alert", return_value={"name": "Kaffee"})
@patch(
    "agents.alert_node._extract_alert_config",
    return_value={
        "name": "Kaffee",
        "query_text": "bohnen",
        "max_price": 10,
        "min_discount": 20,
        "categories": ["getraenke"],
    },
)
def test_alert_node_create_success(_extract_mock, create_alert_mock):
    result = alert_node(
        {
            "intent": "set_alert",
            "user_query": "kaffee bis 10 euro",
            "alert_config": {"user_id": "u1"},
        }
    )

    create_alert_mock.assert_called_once_with(
        user_id="u1",
        name="Kaffee",
        query_text="bohnen",
        max_price=10,
        min_discount=20,
        categories=["getraenke"],
    )
    assert result["alert_config"] == {"name": "Kaffee"}
    assert "✅ Alert **Kaffee** wurde erstellt!" in result["final_response"]
    assert "für: *bohnen* (max €10) (min -20%)." in result["final_response"]


@patch("agents.alert_node.create_alert", return_value=None)
@patch(
    "agents.alert_node._extract_alert_config",
    return_value={"name": "Kaffee", "query_text": "bohnen"},
)
def test_alert_node_create_failure(_extract_mock, _create_alert_mock):
    result = alert_node(
        {
            "intent": "set_alert",
            "user_query": "kaffee",
            "alert_config": {"user_id": "u1"},
        }
    )

    assert result["final_response"] == "Alert konnte nicht erstellt werden. Bitte versuche es erneut."
