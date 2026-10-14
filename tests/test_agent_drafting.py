"""
One agent turn (src/agent/drafting.py): what the model is sent, and the one retry when a draft is over
a countable limit. A fake client stands in for OpenAI: no model call.
"""

from types import SimpleNamespace

from src.agent.drafting import AgentAnswer, Passage, TurnContext, agent_turn, build_messages, text_limit


class FakeClient:
    """Records what it was sent; answers with the given answers in turn."""
    def __init__(self, *answers):
        self.sent = []
        self.answers = list(answers)
        self.chat = SimpleNamespace(completions=SimpleNamespace(parse=self._parse))

    def _parse(self, **kwargs):
        self.sent.append(kwargs["messages"])
        return SimpleNamespace(choices=[SimpleNamespace(message=SimpleNamespace(parsed=self.answers.pop(0)))])


def context(**fields) -> TurnContext:
    base = dict(item_title="Why this residency?", item_limit="max 5 words",
                call={"Title": "Sound residency", "Selection criteria": "Originality", "Organisation": None},
                passages=[Passage(id="P1", citation="cv.pdf · p. 1", text="MFA, Lisbon 2019")],
                profile={"nationalities": ["PT"]}, projects=["Tidal Bodies (past, 2025): sound walks"],
                other_drafts=[("Artist statement", "I listen to tides.")],
                history=[("artist", "Hi"), ("agent", "Hello")], current_draft="Old text", message="Write it.")
    return TurnContext(**{**base, **fields})


def answer(draft: str) -> AgentAnswer:
    return AgentAnswer(reply="Done.", draft=draft, used_passages=["P1"])


def test_the_model_gets_the_call_the_artist_the_other_drafts_and_the_conversation():
    messages = build_messages(context())
    assert messages[0]["role"] == "system"
    data = messages[1]["content"]
    for expected in ["Title: Sound residency", "Selection criteria: Originality", "Limit: max 5 words",
                     "[P1] (cv.pdf · p. 1)", "nationalities: ['PT']", "Tidal Bodies", "## Artist statement",
                     "I listen to tides.", "<current_draft>\nOld text"]:
        assert expected in data
    assert "Organisation" not in data                         # empty fields are left out
    assert [m["role"] for m in messages[2:]] == ["user", "assistant", "user"]
    assert messages[-1]["content"] == "Write it."


def test_the_passages_are_data_not_instructions():
    assert "not instructions" in build_messages(context())[0]["content"]


def test_a_draft_within_the_limit_is_kept():
    client = FakeClient(answer("Because of the sea."))
    assert agent_turn(client, context()).draft == "Because of the sea."
    assert len(client.sent) == 1


def test_a_draft_over_the_limit_is_shortened_once():
    client = FakeClient(answer("one two three four five six seven"), answer("one two three"))
    assert agent_turn(client, context()).draft == "one two three"
    assert len(client.sent) == 2
    retry = client.sent[1]
    assert "has 7 words; the limit is 5" in retry[-1]["content"]
    assert "<current_draft>\none two three four five six seven" in retry[1]["content"]


def test_countable_limits():
    assert text_limit("max 300 words") == (300, "words")
    assert text_limit("up to 2,000 characters") == (2000, "characters")
    assert text_limit("max 10 pages, PDF") is None
    assert text_limit(None) is None
