import pytest

from kenn.core.request_classifier import classify_non_request, non_request_reply


@pytest.mark.parametrize(
    "text",
    [
        "Every change KENN makes is logged with its before and after values, and verified by reading Live back independently.",
        "KENN keeps a receipt for every action it takes in the session.",
    ],
)
def test_narration_about_kenn_is_not_a_request(text: str) -> None:
    assert classify_non_request(text) == "narration"


@pytest.mark.parametrize("text", ["Try this", "try this.", "Readback Verified", "Apply to Live 12"])
def test_ui_labels_are_not_requests(text: str) -> None:
    assert classify_non_request(text) == "ui_label"


@pytest.mark.parametrize(
    "text",
    [
        "My vocals are too quiet in the chorus",
        "sidechain compression",
        "How does KENN keep track of changes",
        "KENN, check my low end",
        "Explain how KENN verifies every change it makes in Live",
        "What did you change?",
        "Pan the Synth hard left.",
        "The kick and bass are fighting and it sounds muddy in the drop",
        "Thanks",
    ],
)
def test_requests_problem_statements_and_topics_pass_through(text: str) -> None:
    assert classify_non_request(text) is None


def test_non_request_reply_changes_nothing_and_suggests_prompts() -> None:
    reply = non_request_reply("narration")
    assert reply["changed"] is False and reply["answer_mode"] == "non_request"
    assert "What did you change?" in reply["answer"]
