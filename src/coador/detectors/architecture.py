from __future__ import annotations

from pathlib import Path

from coador.detectors.base import BaseDetector, DetectionResult, Evidence
from coador.gradle import (
    parse_include_modules,
)
from coador.textscan import glob_files, grep_files, read_file_content


class LayeringHintsDetector(BaseDetector):
    @property
    def name(self) -> str:
        return "Layering Hints"

    @property
    def category(self) -> str:
        return "Architecture"

    def detect(self) -> DetectionResult:
        settings = self.find_file("settings.gradle.kts", "settings.gradle")
        if not settings:
            return DetectionResult.not_found("settings.gradle not found")

        content = read_file_content(settings, root=self.repo_root) or ""
        modules = parse_include_modules(content)
        if not modules:
            return DetectionResult.not_found("No modules found for grouping")

        groups: dict[str, int] = {}
        for module in modules:
            parts = module.lstrip(":").split(":")
            group = parts[0] if len(parts) >= 2 else "root"
            groups[group] = groups.get(group, 0) + 1

        summary = ", ".join(f"{k}({v})" for k, v in sorted(groups.items(), key=lambda x: -x[1]))
        evidence = [
            Evidence(
                file_path=self.relative_path(settings),
                line_start=1,
                line_end=1,
                snippet=f"Module groups: {summary}",
            )
        ]

        return DetectionResult(
            detected=True,
            description=summary,
            evidence=evidence,
        )


class DIFrameworkDetector(BaseDetector):
    @property
    def name(self) -> str:
        return "DI Framework"

    @property
    def category(self) -> str:
        return "Dependency Injection"

    def detect(self) -> DetectionResult:
        evidence: list[Evidence] = []
        frameworks: list[str] = []

        toml_path = self.find_file("gradle/libs.versions.toml")
        if toml_path:
            content = read_file_content(toml_path, root=self.repo_root) or ""
            content_lower = content.lower()

            if "hilt" in content_lower:
                frameworks.append("Hilt")
                matches = grep_files(self.repo_root, r"hilt", "gradle/libs.versions.toml")
                for m in matches:
                    evidence.append(
                        Evidence.from_match(
                            self.relative_path(m.file_path), m.line_number, m.line_content
                        )
                    )

            if "dagger" in content_lower and "hilt" not in content_lower:
                frameworks.append("Dagger 2")
                matches = grep_files(self.repo_root, r"dagger", "gradle/libs.versions.toml")
                for m in matches:
                    evidence.append(
                        Evidence.from_match(
                            self.relative_path(m.file_path), m.line_number, m.line_content
                        )
                    )

            if "koin" in content_lower:
                frameworks.append("Koin")

        annotation_matches = grep_files(
            self.repo_root,
            r"@(Component|Module|Inject|Provides|HiltAndroidApp|InstallIn)",
            "**/*.kt",
        )
        for m in annotation_matches:
            evidence.append(
                Evidence.from_match(self.relative_path(m.file_path), m.line_number, m.match_text)
            )

        if frameworks:
            return DetectionResult(
                detected=True,
                description=", ".join(frameworks),
                evidence=evidence,
            )

        return DetectionResult.not_found("No DI framework detected")


class NetworkingStackDetector(BaseDetector):
    @property
    def name(self) -> str:
        return "Networking Stack"

    @property
    def category(self) -> str:
        return "Networking"

    def detect(self) -> DetectionResult:
        evidence: list[Evidence] = []
        stacks: list[str] = []

        toml_path = self.find_file("gradle/libs.versions.toml")
        if toml_path:
            content = (read_file_content(toml_path, root=self.repo_root) or "").lower()

            if "retrofit" in content:
                stacks.append("Retrofit")
            if "okhttp" in content:
                stacks.append("OkHttp")
            if "ktor" in content:
                stacks.append("Ktor")

        interceptor_matches = grep_files(
            self.repo_root,
            r"Interceptor|addInterceptor|addNetworkInterceptor",
            "**/*.kt",
        )
        for m in interceptor_matches:
            evidence.append(
                Evidence.from_match(self.relative_path(m.file_path), m.line_number, m.line_content)
            )

        api_matches = grep_files(
            self.repo_root,
            r"@(GET|POST|PUT|DELETE|PATCH|HTTP)\s*\(",
            "**/*.kt",
        )
        for m in api_matches:
            evidence.append(
                Evidence.from_match(self.relative_path(m.file_path), m.line_number, m.match_text)
            )

        if stacks:
            return DetectionResult(
                detected=True,
                description=", ".join(stacks),
                evidence=evidence,
            )

        return DetectionResult.not_found("No networking stack detected")


class PersistenceDetector(BaseDetector):
    @property
    def name(self) -> str:
        return "Persistence"

    @property
    def category(self) -> str:
        return "Data Storage"

    def detect(self) -> DetectionResult:
        evidence: list[Evidence] = []
        mechanisms: list[str] = []

        toml_path = self.find_file("gradle/libs.versions.toml")
        if toml_path:
            content = (read_file_content(toml_path, root=self.repo_root) or "").lower()

            if "room" in content:
                mechanisms.append("Room")
            if "datastore" in content:
                mechanisms.append("DataStore")

        room_imports = grep_files(
            self.repo_root,
            r"import\s+androidx\.room",
            "**/*.kt",
        )
        if room_imports:
            if "Room" not in mechanisms:
                mechanisms.append("Room")
            for m in room_imports:
                evidence.append(
                    Evidence.from_match(
                        self.relative_path(m.file_path), m.line_number, m.line_content
                    )
                )

        room_annotations = grep_files(
            self.repo_root,
            r"@(Entity|Dao|Database|Insert|Update|Delete)",
            "**/*.kt",
        )
        for m in room_annotations:
            line = m.line_content
            if any(
                tag in line
                for tag in ("@Entity", "@Dao", "@Database", "@Insert", "@Update", "@Delete")
            ):
                evidence.append(
                    Evidence.from_match(
                        self.relative_path(m.file_path), m.line_number, m.line_content
                    )
                )

        sp_matches = grep_files(
            self.repo_root,
            r"SharedPreferences|getSharedPreferences|PreferenceManager",
            "**/*.kt",
        )
        if sp_matches:
            mechanisms.append("SharedPreferences")
            for m in sp_matches:
                evidence.append(
                    Evidence.from_match(
                        self.relative_path(m.file_path), m.line_number, m.line_content
                    )
                )

        if mechanisms:
            return DetectionResult(
                detected=True,
                description=", ".join(mechanisms),
                evidence=evidence,
            )

        return DetectionResult.not_found("No persistence mechanism detected")


class NavigationDetector(BaseDetector):
    @property
    def name(self) -> str:
        return "Navigation"

    @property
    def category(self) -> str:
        return "Navigation"

    def detect(self) -> DetectionResult:
        evidence: list[Evidence] = []
        mechanisms: list[str] = []

        toml_path = self.find_file("gradle/libs.versions.toml")
        if toml_path:
            content = (read_file_content(toml_path, root=self.repo_root) or "").lower()

            if "navigation" in content:
                mechanisms.append("Jetpack Navigation")

        navhost_matches = grep_files(
            self.repo_root,
            r"NavHost|NavController|navController|navigate\s*\(",
            "**/*.kt",
        )
        for m in navhost_matches:
            evidence.append(
                Evidence.from_match(self.relative_path(m.file_path), m.line_number, m.line_content)
            )

        deeplink_matches = grep_files(
            self.repo_root,
            r"deepLink|DeepLink|uriPattern",
            "**/*.kt",
        )
        if deeplink_matches:
            mechanisms.append("Deep Links")
            for m in deeplink_matches:
                evidence.append(
                    Evidence.from_match(
                        self.relative_path(m.file_path), m.line_number, m.line_content
                    )
                )

        nav_graphs = glob_files(self.repo_root, "**/navigation/*.xml")
        if nav_graphs:
            mechanisms.append("Navigation XML graphs")
            for ng in nav_graphs:
                evidence.append(
                    Evidence(
                        file_path=self.relative_path(ng),
                        line_start=1,
                        line_end=1,
                        snippet="Navigation graph file",
                    )
                )

        if mechanisms:
            return DetectionResult(
                detected=True,
                description=", ".join(mechanisms),
                evidence=evidence,
            )

        return DetectionResult.not_found("No navigation mechanism detected")


class StateManagementDetector(BaseDetector):
    @property
    def name(self) -> str:
        return "State Management"

    @property
    def category(self) -> str:
        return "State Management"

    def detect(self) -> DetectionResult:
        evidence: list[Evidence] = []
        patterns: list[str] = []

        stateflow_matches = grep_files(
            self.repo_root,
            r"StateFlow|MutableStateFlow|stateIn",
            "**/*.kt",
        )
        if stateflow_matches:
            patterns.append("StateFlow")
            for m in stateflow_matches:
                evidence.append(
                    Evidence.from_match(
                        self.relative_path(m.file_path), m.line_number, m.line_content
                    )
                )

        livedata_matches = grep_files(
            self.repo_root,
            r"LiveData|MutableLiveData|observeAsState",
            "**/*.kt",
        )
        if livedata_matches:
            patterns.append("LiveData")
            for m in livedata_matches:
                evidence.append(
                    Evidence.from_match(
                        self.relative_path(m.file_path), m.line_number, m.line_content
                    )
                )

        uistate_matches = grep_files(
            self.repo_root,
            r"UiState|ViewState|ScreenState",
            "**/*.kt",
        )
        if uistate_matches:
            patterns.append("UiState pattern")
            for m in uistate_matches:
                evidence.append(
                    Evidence.from_match(
                        self.relative_path(m.file_path), m.line_number, m.line_content
                    )
                )

        if patterns:
            return DetectionResult(
                detected=True,
                description=", ".join(patterns),
                evidence=evidence,
            )

        return DetectionResult.not_found("No state management pattern detected")


class ConcurrencyDetector(BaseDetector):
    @property
    def name(self) -> str:
        return "Concurrency"

    @property
    def category(self) -> str:
        return "Concurrency"

    def detect(self) -> DetectionResult:
        evidence: list[Evidence] = []
        patterns: list[str] = []

        coroutine_matches = grep_files(
            self.repo_root,
            r"suspend\s+fun|CoroutineScope|viewModelScope|lifecycleScope",
            "**/*.kt",
        )
        if coroutine_matches:
            patterns.append("Coroutines")
            for m in coroutine_matches:
                evidence.append(
                    Evidence.from_match(
                        self.relative_path(m.file_path), m.line_number, m.line_content
                    )
                )

        dispatcher_matches = grep_files(
            self.repo_root,
            r"Dispatchers\.(IO|Main|Default)|CoroutineDispatcher",
            "**/*.kt",
        )
        if dispatcher_matches:
            patterns.append("Dispatcher injection")
            for m in dispatcher_matches:
                evidence.append(
                    Evidence.from_match(
                        self.relative_path(m.file_path), m.line_number, m.line_content
                    )
                )

        flow_matches = grep_files(
            self.repo_root,
            r"\.collect\s*\{|\.collectLatest|flowOf|channelFlow",
            "**/*.kt",
        )
        if flow_matches:
            patterns.append("Flow")
            for m in flow_matches:
                evidence.append(
                    Evidence.from_match(
                        self.relative_path(m.file_path), m.line_number, m.line_content
                    )
                )

        if patterns:
            return DetectionResult(
                detected=True,
                description=", ".join(patterns),
                evidence=evidence,
            )

        return DetectionResult.not_found("No concurrency pattern detected")


class AuthSessionDetector(BaseDetector):
    @property
    def name(self) -> str:
        return "Auth/Session"

    @property
    def category(self) -> str:
        return "Authentication"

    def detect(self) -> DetectionResult:
        evidence: list[Evidence] = []
        mechanisms: list[str] = []

        token_matches = grep_files(
            self.repo_root,
            r"accessToken|refreshToken|bearerToken|Authorization",
            "**/*.kt",
        )
        if token_matches:
            mechanisms.append("Token-based auth")
            for m in token_matches:
                evidence.append(
                    Evidence.from_match(
                        self.relative_path(m.file_path), m.line_number, m.line_content
                    )
                )

        oauth_matches = grep_files(
            self.repo_root,
            r"OAuth|AppAuth|openid|PKCE",
            "**/*.kt",
        )
        if oauth_matches:
            mechanisms.append("OAuth/OpenID")
            for m in oauth_matches:
                evidence.append(
                    Evidence.from_match(
                        self.relative_path(m.file_path), m.line_number, m.line_content
                    )
                )

        session_matches = grep_files(
            self.repo_root,
            r"SessionManager|UserSession|isLoggedIn|logout",
            "**/*.kt",
        )
        if session_matches:
            mechanisms.append("Session management")
            for m in session_matches:
                evidence.append(
                    Evidence.from_match(
                        self.relative_path(m.file_path), m.line_number, m.line_content
                    )
                )

        if mechanisms:
            return DetectionResult(
                detected=True,
                description=", ".join(mechanisms),
                evidence=evidence,
            )

        return DetectionResult.not_found("No auth mechanism detected")


class ContentPlatformDetector(BaseDetector):
    @property
    def name(self) -> str:
        return "Content Platform Integration"

    @property
    def category(self) -> str:
        return "Content"

    def detect(self) -> DetectionResult:
        evidence: list[Evidence] = []

        matches = grep_files(
            self.repo_root,
            r"kontent|kentico|contentful",
            "**/*.gradle*",
        )
        if not matches:
            matches = grep_files(
                self.repo_root,
                r"kontent|kentico|contentful",
                "**/*.kt",
            )
        for m in matches:
            evidence.append(
                Evidence.from_match(self.relative_path(m.file_path), m.line_number, m.line_content)
            )

        if evidence:
            return DetectionResult(
                detected=True,
                description="Content platform signals",
                evidence=evidence,
            )

        return DetectionResult.not_found("No content platform signals found")


class MarketingEngagementDetector(BaseDetector):
    @property
    def name(self) -> str:
        return "Marketing/Engagement"

    @property
    def category(self) -> str:
        return "Engagement"

    def detect(self) -> DetectionResult:
        evidence: list[Evidence] = []

        matches = grep_files(
            self.repo_root,
            r"onesignal|braze|appsflyer|adjust|firebase\.messaging|inapp|campaign|engagement|push",
            "**/*.gradle*",
        )
        if not matches:
            matches = grep_files(
                self.repo_root,
                r"onesignal|braze|appsflyer|adjust|firebase\.messaging|inapp|campaign|engagement|push",
                "**/*.kt",
            )
        for m in matches:
            evidence.append(
                Evidence.from_match(self.relative_path(m.file_path), m.line_number, m.line_content)
            )

        if evidence:
            return DetectionResult(
                detected=True,
                description="Marketing/engagement signals",
                evidence=evidence,
            )

        return DetectionResult.not_found("No marketing/engagement signals found")


class AnalyticsCrashDetector(BaseDetector):
    @property
    def name(self) -> str:
        return "Analytics/Crash"

    @property
    def category(self) -> str:
        return "Analytics & Crash Reporting"

    def detect(self) -> DetectionResult:
        evidence: list[Evidence] = []
        services: list[str] = []

        toml_path = self.find_file("gradle/libs.versions.toml")
        if toml_path:
            content = (read_file_content(toml_path, root=self.repo_root) or "").lower()

            if "firebase" in content and "analytics" in content:
                services.append("Firebase Analytics")
            if "crashlytics" in content:
                services.append("Crashlytics")
            if "sentry" in content:
                services.append("Sentry")
            if "appcenter" in content:
                services.append("AppCenter")

        analytics_matches = grep_files(
            self.repo_root,
            r"FirebaseAnalytics|logEvent|trackEvent|Analytics\.",
            "**/*.kt",
        )
        for m in analytics_matches:
            evidence.append(
                Evidence.from_match(self.relative_path(m.file_path), m.line_number, m.line_content)
            )

        if services:
            return DetectionResult(
                detected=True,
                description=", ".join(services),
                evidence=evidence,
            )

        return DetectionResult.not_found("No analytics/crash service detected")


class FeatureFlagsDetector(BaseDetector):
    @property
    def name(self) -> str:
        return "Feature Flags"

    @property
    def category(self) -> str:
        return "Feature Flags"

    def detect(self) -> DetectionResult:
        evidence: list[Evidence] = []
        mechanisms: list[str] = []

        toml_path = self.find_file("gradle/libs.versions.toml")
        if toml_path:
            content = (read_file_content(toml_path, root=self.repo_root) or "").lower()

            if "remoteconfig" in content or "remote-config" in content:
                mechanisms.append("Firebase Remote Config")

        flag_matches = grep_files(
            self.repo_root,
            r"featureFlag|FeatureToggle|isFeatureEnabled|RemoteConfig",
            "**/*.kt",
        )
        if flag_matches:
            if "Feature flags" not in mechanisms:
                mechanisms.append("Feature flags")
            for m in flag_matches:
                evidence.append(
                    Evidence.from_match(
                        self.relative_path(m.file_path), m.line_number, m.line_content
                    )
                )

        if mechanisms:
            return DetectionResult(
                detected=True,
                description=", ".join(mechanisms),
                evidence=evidence,
            )

        return DetectionResult.not_found("No feature flags detected")


def get_architecture_detectors(repo_root: Path) -> list[BaseDetector]:
    return [
        LayeringHintsDetector(repo_root),
        DIFrameworkDetector(repo_root),
        NetworkingStackDetector(repo_root),
        PersistenceDetector(repo_root),
        NavigationDetector(repo_root),
        StateManagementDetector(repo_root),
        ConcurrencyDetector(repo_root),
        AuthSessionDetector(repo_root),
        ContentPlatformDetector(repo_root),
        MarketingEngagementDetector(repo_root),
        AnalyticsCrashDetector(repo_root),
        FeatureFlagsDetector(repo_root),
    ]
