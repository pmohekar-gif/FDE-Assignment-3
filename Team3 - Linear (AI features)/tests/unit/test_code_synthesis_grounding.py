"""What the optional provider is actually allowed to see when it phrases an answer.

`docs/features/CODE_INTELLIGENCE_REFINEMENT_EXECUTION.md` promises the provider receives
"only the final redacted, bounded evidence set". It used to receive one composed sentence
of module names and line labels -- no code at all -- so the model could only re-word a
template while the result was presented as a grounded answer. These tests pin the real
contract in both directions: the evidence goes over, and nothing outside it does.
"""

from __future__ import annotations

from warrant.repository import CodeIntelligenceService, CodeSource


def source(path: str, snippet: str, start: int = 10) -> CodeSource:
    return CodeSource(
        path=path,
        start_line=start,
        end_line=start + 1,
        reason="matched",
        snippet=snippet,
        score=100.0,
        module=path.rsplit("/", 1)[0].replace("/", "."),
        edge="definition",
        rank_tier="exact_definition",
    )


def test_the_provider_receives_the_bounded_snippets_and_their_citations():
    facts = CodeIntelligenceService._provider_facts(
        "Strongest repository evidence is in warrant.policy.",
        [source("src/warrant/policy.py", "def decide(features):\n    return ALLOW")],
    )
    assert facts[0].startswith("Strongest repository evidence")
    assert len(facts) == 2
    assert "src/warrant/policy.py:10-11" in facts[1]
    assert "definition" in facts[1] and "exact_definition" in facts[1]
    assert "def decide(features):" in facts[1]


def test_only_the_budgeted_sources_reach_the_provider():
    kept = [source("a.py", "kept body", 1), source("b.py", "also kept", 2)]
    facts = CodeIntelligenceService._provider_facts("summary", kept)
    joined = "\n".join(facts)
    assert "kept body" in joined and "also kept" in joined
    # One fact per source plus the composed summary; nothing is invented or duplicated.
    assert len(facts) == len(kept) + 1


def test_a_source_without_a_snippet_contributes_no_empty_fact():
    facts = CodeIntelligenceService._provider_facts("summary", [source("a.py", "   ")])
    assert facts == ["summary"]
