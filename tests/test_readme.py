from pathlib import Path

NOW_IN_ANDROID_REF = "12f80da6518e161ed16a06a68e71fb8a873576d6"


def test_readme_leads_with_hook_and_product_narrative_before_technical_reference() -> None:
    readme = Path("README.md").read_text(encoding="utf-8")

    assert readme.startswith(
        "# Coador\n\n"
        "**Give AI agents a map of your Android project before they start reading the code.**"
    )
    headings = (
        "## Why no AI in the scanner?",
        "## How it works",
        "## Practical example",
        "## Local and verifiable",
        "## Not a replacement for source code",
        "## Installation",
        "## CLI",
        "## MCP",
        "## Examples",
        "## Project status",
        "## License",
    )
    positions = [readme.index(heading) for heading in headings]

    assert positions == sorted(positions)
    assert "Faster context. Less repeated discovery. Lower token usage." in readme
    assert "How do I add and run an instrumentation UI test" in readme
    assert f"git -C nowinandroid checkout {NOW_IN_ANDROID_REF}" in readme
    assert "scan nowinandroid --kb-dir ../nowinandroid-coador" in readme
    assert "source: heuristic" in readme
    assert "not a complete Gradle task enumeration" in readme


def test_readme_demo_links_to_pinned_source_evidence() -> None:
    readme = Path("README.md").read_text(encoding="utf-8")
    pinned_root = f"https://github.com/android/nowinandroid/blob/{NOW_IN_ANDROID_REF}/"

    expected_citations = (
        "app/src/androidTest/kotlin/com/google/samples/apps/nowinandroid/ui/"
        "NavigationTest.kt#L58-L80",
        "app/build.gradle.kts#L31-L39",
        "core/testing/src/main/kotlin/com/google/samples/apps/nowinandroid/core/testing/"
        "NiaTestRunner.kt#L17-L30",
        "core/data-test/src/main/kotlin/com/google/samples/apps/nowinandroid/core/data/test/"
        "TestDataModule.kt#L32-L51",
        ".github/workflows/Build.yaml#L239-L247",
    )

    for citation in expected_citations:
        assert f"{pinned_root}{citation}" in readme
