from __future__ import annotations

from coador.model import Evidence, Layer, Profile, ResultKind, Section
from coador.search import LexicalRetriever, search
from coador.search.lexical import tokenize


def test_identifiers_split_into_their_words() -> None:
    tokens = tokenize("testInstrumentationRunner")
    assert "testinstrumentationrunner" in tokens
    assert {"test", "instrumentation", "runner"} <= set(tokens)


def test_punctuation_separates_tokens() -> None:
    assert {"libs", "versions", "toml"} <= set(tokenize("libs.versions.toml"))
    assert {"core", "network"} <= set(tokenize(":core:network"))


def test_acronyms_are_kept_whole() -> None:
    assert "uistate" in tokenize("UiState")
    assert {"ui", "state"} <= set(tokenize("UiState"))


def test_question_words_are_dropped_but_never_all_of_them() -> None:
    assert tokenize("how do I run the tests", drop_stop_words=True) == ["run", "tests"]
    assert tokenize("how do I", drop_stop_words=True) == ["how", "do", "i"]


def test_search_finds_the_section_that_is_about_the_query(fixture_profile: Profile) -> None:
    hits = search(fixture_profile, "hilt", limit=3)
    assert hits
    assert hits[0].section.id in {"di_framework", "ui_test_application_class"}
    assert "hilt" in hits[0].matched_terms


def test_natural_language_queries_reach_the_right_layer(fixture_profile: Profile) -> None:
    expectations = {
        "which database is used": ("03_architecture", "persistence"),
        "what is the DI framework": ("03_architecture", "di_framework"),
        "how are flaky tests retried in CI": ("09_ci_cd", "retry_flakiness_handling"),
    }
    for query, expected in expectations.items():
        hits = search(fixture_profile, query, limit=3)
        found = [(hit.layer_id, hit.section.id) for hit in hits]
        assert expected in found, f"{query!r} -> {found}"


def test_a_detected_section_outranks_the_same_subject_reported_absent() -> None:
    profile = Profile(
        project_name="x",
        layers=[
            Layer(
                id="08_ui_testing",
                title="UI Testing",
                sections=[
                    Section(
                        id="deep_links_webview_helpers",
                        title="Deep Links / WebView Helpers",
                        detected=False,
                        summary="No deep link or WebView helpers detected",
                    ),
                    Section(
                        id="deep_link_inventory",
                        title="Deep Link Inventory",
                        detected=True,
                        summary="1 deep link declared",
                        kind=ResultKind.INVENTORY,
                        items=["https://example.com/login"],
                    ),
                ],
            )
        ],
    )
    hits = search(profile, "deep link", limit=2)
    assert hits[0].section.id == "deep_link_inventory"


def test_search_can_be_restricted_to_one_layer(fixture_profile: Profile) -> None:
    hits = search(fixture_profile, "test", limit=20, layer_id="09_ci_cd")
    assert hits
    assert {hit.layer_id for hit in hits} == {"09_ci_cd"}


def test_evidence_content_is_searchable(fixture_profile: Profile) -> None:
    hits = search(fixture_profile, "MockWebServer", limit=5)
    assert any(hit.section.id == "test_dependency_substitution" for hit in hits)


def test_unknown_terms_return_nothing(fixture_profile: Profile) -> None:
    assert search(fixture_profile, "zzzz-not-a-real-term", limit=5) == []


def test_empty_profile_and_empty_query_are_handled(fixture_profile: Profile) -> None:
    assert search(Profile(project_name="empty"), "hilt") == []
    assert search(fixture_profile, "   ") == []


def test_hits_serialise_for_json_output(fixture_profile: Profile) -> None:
    hit = search(fixture_profile, "retrofit", limit=1)[0]
    data = hit.to_dict()
    assert data["layer"] == "03_architecture"
    assert data["section"] == "networking_stack"
    assert isinstance(data["score"], float)


def test_the_index_is_reusable_across_queries(fixture_profile: Profile) -> None:
    retriever = LexicalRetriever(fixture_profile)
    assert retriever.search("hilt")
    assert retriever.search("gradle")


def test_long_sections_do_not_dominate() -> None:
    """Length normalisation: a short exact match beats a long section mentioning the term once."""
    long_evidence = [
        Evidence.from_source(f"file{i}.kt", "\n" * (i - 1) + "unrelated content here", i)
        for i in range(1, 201)
    ]
    profile = Profile(
        project_name="x",
        layers=[
            Layer(
                id="03_architecture",
                title="Architecture",
                sections=[
                    Section(
                        id="navigation",
                        title="Navigation",
                        detected=True,
                        summary="Jetpack Navigation",
                        evidence=[
                            *long_evidence,
                            Evidence.from_source("a.kt", "room", 1),
                        ],
                    ),
                    Section(
                        id="persistence",
                        title="Persistence",
                        detected=True,
                        summary="Room",
                    ),
                ],
            )
        ],
    )
    assert search(profile, "room", limit=2)[0].section.id == "persistence"


def test_index_and_matches_do_not_expose_mutated_source_fields() -> None:
    section = Section(id="navigation", title="Navigation", detected=True, summary="safe")
    section.summary = 'token = "CANARY"'
    profile = Profile(
        project_name="x",
        layers=[Layer(id="03_architecture", title="Architecture", sections=[section])],
    )
    assert search(profile, "CANARY") == []
    hit = search(profile, "token")[0]
    assert "CANARY" not in str(hit.to_dict())
