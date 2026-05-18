"""Unit tests for bot.handlers helper logic."""

from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from telegram.constants import ParseMode

import bot.handlers as handlers


def _make_update(chat_id="123", text="hello"):
    message = AsyncMock()
    message.text = text
    update = SimpleNamespace(
        effective_chat=SimpleNamespace(id=chat_id),
        message=message,
    )
    return update, message


def _make_ctx(args=None, user_data=None):
    return SimpleNamespace(args=args or [], user_data=user_data or {})


def test_set_graph_updates_global():
    graph = object()
    handlers.set_graph(graph)
    assert handlers._graph is graph


@pytest.mark.asyncio
async def test_cmd_suche_requires_query():
    update, message = _make_update()
    ctx = _make_ctx(args=[])

    await handlers.cmd_suche(update, ctx)

    message.reply_text.assert_awaited_once_with(
        "Bitte gib einen Suchbegriff an. Beispiel: /suche Laptop"
    )


@pytest.mark.asyncio
@patch("bot.handlers._run_graph_and_reply", new_callable=AsyncMock)
async def test_cmd_suche_runs_query_flow(run_graph_mock):
    update, _message = _make_update()
    ctx = _make_ctx(args=["bio", "apfel"])

    await handlers.cmd_suche(update, ctx)

    run_graph_mock.assert_awaited_once_with(update, ctx, "bio apfel", intent="query")


@pytest.mark.asyncio
async def test_cmd_vergleiche_requires_query():
    update, message = _make_update()
    ctx = _make_ctx(args=[])

    await handlers.cmd_vergleiche(update, ctx)

    message.reply_text.assert_awaited_once_with("Beispiel: /vergleiche Kopfhörer")


@pytest.mark.asyncio
@patch("bot.handlers._get_user_id", return_value=None)
async def test_cmd_alert_requires_registered_user(_get_user_id_mock):
    update, message = _make_update()
    ctx = _make_ctx(args=["Kaffee"])

    await handlers.cmd_alert(update, ctx)

    message.reply_text.assert_awaited_once_with("Starte zuerst mit /start.")


@pytest.mark.asyncio
@patch("bot.handlers._get_user_id", return_value="u1")
async def test_cmd_alert_requires_args(_get_user_id_mock):
    update, message = _make_update()
    ctx = _make_ctx(args=[])

    await handlers.cmd_alert(update, ctx)

    message.reply_html.assert_awaited_once()
    assert "Format: <b>Name | Suchanfrage</b>" in message.reply_html.await_args.args[0]


@pytest.mark.asyncio
@patch("bot.handlers._run_graph_and_reply", new_callable=AsyncMock)
@patch("bot.handlers._get_user_id", return_value="u1")
async def test_cmd_alert_runs_set_alert_flow(_get_user_id_mock, run_graph_mock):
    update, _message = _make_update()
    ctx = _make_ctx(args=["Kaffee", "|", "bohnen"])

    await handlers.cmd_alert(update, ctx)

    run_graph_mock.assert_awaited_once_with(
        update,
        ctx,
        "Kaffee | bohnen",
        intent="set_alert",
        user_id="u1",
    )


@pytest.mark.asyncio
@patch("bot.handlers.list_alerts", return_value=[])
@patch("bot.handlers._get_user_id", return_value="u1")
async def test_cmd_meinalerts_empty(_get_user_id_mock, _list_alerts_mock):
    update, message = _make_update()
    ctx = _make_ctx()

    await handlers.cmd_meinalerts(update, ctx)

    message.reply_text.assert_awaited_once_with("Du hast noch keine aktiven Alerts.")


@pytest.mark.asyncio
@patch(
    "bot.handlers.list_alerts",
    return_value=[{"name": "Kaffee", "query_text": "bohnen", "max_price": 10}],
)
@patch("bot.handlers._get_user_id", return_value="u1")
async def test_cmd_meinalerts_formats_html(_get_user_id_mock, _list_alerts_mock):
    update, message = _make_update()
    ctx = _make_ctx()

    await handlers.cmd_meinalerts(update, ctx)

    message.reply_html.assert_awaited_once()
    assert "Kaffee" in message.reply_html.await_args.args[0]
    assert "max €10" in message.reply_html.await_args.args[0]


@pytest.mark.asyncio
@patch("bot.handlers._run_graph_and_reply", new_callable=AsyncMock)
async def test_handle_text_routes_full_query(run_graph_mock):
    update, _message = _make_update(text="suche kaffee")
    ctx = _make_ctx()

    await handlers.handle_text(update, ctx)

    run_graph_mock.assert_awaited_once_with(update, ctx, "suche kaffee")


@pytest.mark.asyncio
async def test_run_graph_and_reply_handles_missing_graph():
    prev_graph = handlers._graph
    handlers._graph = None
    try:
        update, message = _make_update()
        ctx = _make_ctx()

        await handlers._run_graph_and_reply(update, ctx, "frage")

        message.reply_text.assert_awaited_once_with("Bot noch nicht bereit. Bitte warte kurz.")
    finally:
        handlers._graph = prev_graph


@pytest.mark.asyncio
async def test_run_graph_and_reply_handles_graph_exception():
    prev_graph = handlers._graph
    handlers._graph = SimpleNamespace(ainvoke=AsyncMock(side_effect=RuntimeError("kaputt")))
    try:
        update, message = _make_update()
        ctx = _make_ctx()

        await handlers._run_graph_and_reply(update, ctx, "frage")

        message.reply_text.assert_awaited_once_with("Fehler: kaputt")
    finally:
        handlers._graph = prev_graph


@pytest.mark.asyncio
@patch("bot.handlers._get_user_id", return_value="u1")
@patch("bot.handlers.offers_list_html", return_value="<b>cards</b>")
async def test_run_graph_and_reply_appends_offer_cards(_offers_list_mock, _get_user_id_mock):
    prev_graph = handlers._graph
    handlers._graph = SimpleNamespace(
        ainvoke=AsyncMock(
            return_value={
                "final_response": "Antwort",
                "query_results": [{"title": "A"}],
                "intent": "query",
            }
        )
    )
    try:
        update, message = _make_update()
        ctx = _make_ctx(user_data={"user_id": "u1"})

        await handlers._run_graph_and_reply(update, ctx, "frage")

        message.reply_html.assert_awaited_once_with("Antwort\n\n<b>cards</b>")
    finally:
        handlers._graph = prev_graph


@pytest.mark.asyncio
@patch("bot.handlers._get_user_id", return_value="u1")
@patch("bot.handlers.comparison_table_html", return_value="<b>vergleich</b>")
async def test_run_graph_and_reply_uses_comparison_format_for_compare(
    _comparison_table_mock, _get_user_id_mock
):
    prev_graph = handlers._graph
    handlers._graph = SimpleNamespace(
        ainvoke=AsyncMock(
            return_value={
                "final_response": "Antwort",
                "query_results": [{"title": "A"}],
                "intent": "compare",
            }
        )
    )
    try:
        update, message = _make_update()
        ctx = _make_ctx(user_data={"user_id": "u1"})

        await handlers._run_graph_and_reply(update, ctx, "frage")

        message.reply_html.assert_awaited_once_with("<b>vergleich</b>")
    finally:
        handlers._graph = prev_graph


@pytest.mark.asyncio
@patch("bot.handlers._get_user_id", return_value="u1")
async def test_run_graph_and_reply_truncates_and_edits_message(_get_user_id_mock):
    prev_graph = handlers._graph
    handlers._graph = SimpleNamespace(
        ainvoke=AsyncMock(
            return_value={
                "final_response": "x" * 5000,
                "query_results": [],
                "intent": "query",
            }
        )
    )
    edit_message = AsyncMock()
    try:
        update, _message = _make_update()
        ctx = _make_ctx(user_data={"user_id": "u1"})

        await handlers._run_graph_and_reply(update, ctx, "frage", edit_message=edit_message)

        edit_message.edit_text.assert_awaited_once()
        args, kwargs = edit_message.edit_text.await_args
        assert len(args[0]) == 3992
        assert args[0].endswith("\n…")
        assert kwargs["parse_mode"] == ParseMode.HTML
    finally:
        handlers._graph = prev_graph


@patch("bot.handlers.get_or_create_user", return_value={"id": "u1"})
def test_get_user_id_uses_cached_user_and_falls_back_to_create(_get_or_create_user_mock):
    update, _message = _make_update(chat_id="777")
    ctx = _make_ctx(user_data={})

    result = handlers._get_user_id(update, ctx)

    assert result == "u1"
    assert ctx.user_data["user_id"] == "u1"


@patch("bot.handlers.get_or_create_user")
def test_get_user_id_returns_existing_ctx_user_without_lookup(get_or_create_user_mock):
    update, _message = _make_update(chat_id="777")
    ctx = _make_ctx(user_data={"user_id": "u9"})

    result = handlers._get_user_id(update, ctx)

    assert result == "u9"
    get_or_create_user_mock.assert_not_called()
