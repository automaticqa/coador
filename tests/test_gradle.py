from __future__ import annotations

from coador.gradle import (
    extract_build_types,
    extract_container_names,
    extract_flavor_names,
    parse_gradle_block,
    parse_include_modules,
    parse_plugins,
    parse_project_dependencies,
)

KOTLIN_DSL = """
android {
    buildTypes {
        debug { isMinifyEnabled = false }
        release {
            isMinifyEnabled = true
            proguardFiles(getDefaultProguardFile("x"), "rules.pro")
        }
    }
    productFlavors {
        create("demo") {
            dimension = "brand"
            buildConfigField("String", "KEY", "\\"value\\"")
        }
        create("prod") { dimension = "brand" }
    }
}
"""

GROOVY_DSL = """
android {
    buildTypes {
        debug { }
        staging {
            if (project.hasProperty("x")) { println "y" } else { println "z" }
            firebaseAppDistribution { groups = "qa" }
        }
    }
    productFlavors {
        alphaAT { dimension "brand" }
        betaCZ { dimension "brand" }
    }
}
"""


def test_build_types_of_both_dialects() -> None:
    assert extract_build_types(KOTLIN_DSL) == ["debug", "release"]
    assert extract_build_types(GROOVY_DSL) == ["debug", "staging"]


def test_flavours_of_both_dialects() -> None:
    assert extract_flavor_names(KOTLIN_DSL) == ["demo", "prod"]
    assert extract_flavor_names(GROOVY_DSL) == ["alphaAT", "betaCZ"]


def test_nested_configuration_is_not_mistaken_for_an_entry() -> None:
    assert "firebaseAppDistribution" not in extract_build_types(GROOVY_DSL)
    assert "else" not in extract_build_types(GROOVY_DSL)
    assert "buildConfigField" not in extract_flavor_names(KOTLIN_DSL)


def test_flavours_created_in_a_loop_are_not_guessed() -> None:
    dynamic = """
    android {
        productFlavors {
            Flavor.values().forEach { flavor -> create(flavor.name) { dimension = "x" } }
        }
    }
    """
    assert extract_flavor_names(dynamic) == []


def test_container_names_are_unique_and_ordered() -> None:
    block = '{ create("a") { }\n create("b") { }\n create("a") { } }'
    assert extract_container_names(block) == ["a", "b"]


def test_missing_block_yields_nothing() -> None:
    assert extract_flavor_names("android { }") == []
    assert extract_build_types("") == []
    assert parse_gradle_block("android { }", "productFlavors") is None


def test_include_modules_from_both_dialects() -> None:
    kotlin = 'include(":app")\ninclude(":core:network", ":core:ui")\n'
    groovy = "include ':app',\n        ':feature:login'\n"
    assert parse_include_modules(kotlin) == [":app", ":core:network", ":core:ui"]
    assert parse_include_modules(groovy) == [":app", ":feature:login"]


def test_project_dependencies_include_type_safe_accessors() -> None:
    content = 'implementation(project(":core:network"))\nimplementation(projects.feature.login)\n'
    assert parse_project_dependencies(content) == [":core:network", ":feature:login"]


def test_plugins_from_ids_aliases_and_legacy_apply() -> None:
    content = """
    plugins {
        id("com.android.application")
        alias(libs.plugins.kotlin.android)
    }
    apply plugin: 'kotlin-kapt'
    """
    plugins = parse_plugins(content)
    assert "com.android.application" in plugins
    assert "kotlin-kapt" in plugins
    assert any("kotlin" in plugin for plugin in plugins)
