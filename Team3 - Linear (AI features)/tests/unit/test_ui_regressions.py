from warrant.providers import FixtureProvider
from warrant.retrieval import titles_are_near_duplicates
from warrant.schemas import ExtractionResult
from warrant.seed import HEADLINE_ISSUES


def test_fixture_extracts_sentence_level_acceptance_criteria():
    issue = HEADLINE_ISSUES[0]
    response = FixtureProvider().extract(
        f"{issue['title']}\n{issue['body']}", list(issue["paths"]), []
    )
    assert isinstance(response.value, ExtractionResult)
    criteria = response.value.acceptance_criteria
    assert 2 <= len(criteria) <= 3
    assert criteria[0] == "Expected: a second retry must not create another charge."
    assert criteria[1].endswith("double-submit.")
    assert all(not item.endswith(" and") for item in criteria)


def test_near_duplicate_title_detection_is_token_based():
    assert titles_are_near_duplicates(
        "Billing timeout after retry", "Billing: timeout after retry"
    )
    assert not titles_are_near_duplicates(
        "Billing timeout after retry during renewal",
        "Billing duplicate notification during a bulk operation",
    )
