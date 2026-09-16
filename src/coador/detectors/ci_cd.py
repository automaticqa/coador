from __future__ import annotations

import re
from pathlib import Path

from coador.detectors.base import BaseDetector, DetectionResult, Evidence
from coador.textscan import glob_files, grep_files, read_file_content, read_lines
from coador.yaml_lite import parse_yaml_jobs, parse_yaml_stages


class CIEntrypointsDetector(BaseDetector):
    @property
    def name(self) -> str:
        return "CI Entrypoints"

    @property
    def category(self) -> str:
        return "CI Configuration"

    def detect(self) -> DetectionResult:
        evidence: list[Evidence] = []
        entrypoints: list[str] = []

        gitlab_ci = self.find_file(".gitlab-ci.yml")
        if gitlab_ci:
            entrypoints.append(".gitlab-ci.yml")
            evidence.append(
                Evidence(
                    file_path=".gitlab-ci.yml",
                    line_start=1,
                    line_end=1,
                    snippet="GitLab CI main config",
                )
            )

            include_matches = grep_files(
                self.repo_root,
                r"^\s*-?\s*(local|project|remote|template):\s*",
                ".gitlab-ci.yml",
            )
            for m in include_matches:
                evidence.append(
                    Evidence.from_match(".gitlab-ci.yml", m.line_number, m.line_content)
                )

        for name, description in (
            ("Jenkinsfile", "Jenkins pipeline"),
            ("bitrise.yml", "Bitrise config"),
            ("azure-pipelines.yml", "Azure Pipelines config"),
            (".circleci/config.yml", "CircleCI config"),
        ):
            candidate = self.find_file(name)
            if candidate:
                entrypoints.append(name)
                evidence.append(
                    Evidence(file_path=name, line_start=1, line_end=1, snippet=description)
                )

        ci_yaml_files = glob_files(
            self.repo_root,
            (
                "ci/**/*.yml",
                "ci/**/*.yaml",
                ".gitlab/**/*.yml",
                ".gitlab/**/*.yaml",
                ".github/workflows/*.yml",
                ".github/workflows/*.yaml",
            ),
        )

        for f in ci_yaml_files:
            rel_path = self.relative_path(f)
            entrypoints.append(rel_path)
            evidence.append(
                Evidence(
                    file_path=rel_path,
                    line_start=1,
                    line_end=1,
                    snippet="CI config file",
                )
            )

        if entrypoints:
            return DetectionResult(
                detected=True,
                description=f"Found {len(entrypoints)} CI config files",
                evidence=evidence,
            )

        return DetectionResult.not_found("No CI configuration found")


class JobsStagesDetector(BaseDetector):
    @property
    def name(self) -> str:
        return "Jobs & Stages"

    @property
    def category(self) -> str:
        return "CI Pipeline"

    def detect(self) -> DetectionResult:
        evidence: list[Evidence] = []
        jobs: list[str] = []
        stages: list[str] = []

        gitlab_ci = self.find_file(".gitlab-ci.yml")
        if gitlab_ci:
            content = read_file_content(gitlab_ci, root=self.repo_root) or ""

            stages = parse_yaml_stages(content)
            jobs = parse_yaml_jobs(content)

            if stages:
                evidence.append(
                    Evidence(
                        file_path=".gitlab-ci.yml",
                        line_start=1,
                        line_end=1,
                        snippet=f"Stages: {', '.join(stages)}",
                    )
                )

            stage_matches = grep_files(
                self.repo_root,
                r"^\s*stage:\s*\w+",
                ".gitlab-ci.yml",
            )
            for m in stage_matches:
                evidence.append(
                    Evidence.from_match(".gitlab-ci.yml", m.line_number, m.line_content)
                )

        if jobs or stages:
            desc_parts = []
            if stages:
                desc_parts.append(f"{len(stages)} stages")
            if jobs:
                desc_parts.append(f"{len(jobs)} jobs")

            return DetectionResult(
                detected=True,
                description=", ".join(desc_parts),
                evidence=evidence,
            )

        return DetectionResult.not_found("No jobs/stages found")


class ScheduledSignalsDetector(BaseDetector):
    @property
    def name(self) -> str:
        return "Scheduled/Nightly Signals"

    @property
    def category(self) -> str:
        return "CI Triggers"

    def detect(self) -> DetectionResult:
        evidence: list[Evidence] = []

        schedule_matches = grep_files(
            self.repo_root,
            r'CI_PIPELINE_SOURCE\s*==\s*["\']schedule["\']|schedules|nightly',
            ("**/*.yml", "**/*.yaml"),
        )
        for m in schedule_matches:
            evidence.append(
                Evidence.from_match(self.relative_path(m.file_path), m.line_number, m.line_content)
            )

        if evidence:
            return DetectionResult(
                detected=True,
                description=f"Found {len(evidence)} schedule-related rules",
                evidence=evidence,
            )

        return DetectionResult.not_found("No scheduled signals found")


class MarathonIntegrationDetector(BaseDetector):
    @property
    def name(self) -> str:
        return "Marathon Integration"

    @property
    def category(self) -> str:
        return "Test Runner"

    def detect(self) -> DetectionResult:
        evidence: list[Evidence] = []
        signals: list[str] = []

        marathonfile = self.find_file("Marathonfile", "marathonfile.yaml", "marathon.yaml")
        if marathonfile:
            signals.append("Marathonfile")
            evidence.append(
                Evidence(
                    file_path=self.relative_path(marathonfile),
                    line_start=1,
                    line_end=1,
                    snippet="Marathon configuration file",
                )
            )

            lines = read_lines(marathonfile, root=self.repo_root)
            for i, line in enumerate(lines, start=1):
                if any(k in line.lower() for k in ["pool", "batch", "retry", "output"]):
                    evidence.append(
                        Evidence(
                            file_path=self.relative_path(marathonfile),
                            line_start=i,
                            line_end=i,
                            snippet=line.strip(),
                        )
                    )

        marathon_cmd_matches = grep_files(
            self.repo_root,
            r"marathon\s+(-|run|--)",
            ("**/*.yml", "**/*.yaml"),
        )
        if marathon_cmd_matches:
            signals.append("Marathon commands")
            for m in marathon_cmd_matches:
                evidence.append(
                    Evidence.from_match(
                        self.relative_path(m.file_path), m.line_number, m.line_content
                    )
                )

        generator_files = glob_files(self.repo_root, "**/marathonfilegen*.kts")
        generator_files.extend(glob_files(self.repo_root, "**/marathon/**/*.kts"))
        for gf in generator_files:
            signals.append("Marathon generator")
            evidence.append(
                Evidence(
                    file_path=self.relative_path(gf),
                    line_start=1,
                    line_end=1,
                    snippet=gf.name,
                )
            )

        if signals:
            return DetectionResult(
                detected=True,
                description=", ".join(dict.fromkeys(signals)),
                evidence=evidence,
            )

        return DetectionResult.not_found("No Marathon integration found")


class VariablesControlDetector(BaseDetector):
    @property
    def name(self) -> str:
        return "Variables Controlling Runs"

    @property
    def category(self) -> str:
        return "CI Variables"

    def detect(self) -> DetectionResult:
        evidence: list[Evidence] = []
        variables: list[str] = []

        var_patterns = [
            r"\$SUITE|\$\{SUITE\}|SUITE:",
            r"\$FLAVOR|\$\{FLAVOR\}|FLAVOR:",
            r"\$EMULATOR_COUNT|\$\{EMULATOR_COUNT\}",
            r"\$SHARD|\$\{SHARD\}|shards?:",
            r"\$RETRY|\$\{RETRY\}|retry:",
        ]

        for pattern in var_patterns:
            matches = grep_files(
                self.repo_root,
                pattern,
                ("**/*.yml", "**/*.yaml"),
            )
            for m in matches:
                if m.match_text not in variables:
                    variables.append(m.match_text)
                evidence.append(
                    Evidence.from_match(
                        self.relative_path(m.file_path), m.line_number, m.line_content
                    )
                )

        if evidence:
            return DetectionResult(
                detected=True,
                description=f"Found {len(variables)} control variables",
                evidence=evidence,
            )

        return DetectionResult.not_found("No control variables found")


class EmulatorProvisioningDetector(BaseDetector):
    @property
    def name(self) -> str:
        return "Emulator/Device Provisioning"

    @property
    def category(self) -> str:
        return "Device Infrastructure"

    def detect(self) -> DetectionResult:
        evidence: list[Evidence] = []
        signals: list[str] = []

        runner_tag_matches = grep_files(
            self.repo_root,
            r"tags:\s*\n\s*-\s*\w+|tags:\s*\[",
            ("**/*.yml", "**/*.yaml"),
            multiline=True,
        )
        if runner_tag_matches:
            signals.append("Runner tags")
            for m in runner_tag_matches:
                evidence.append(
                    Evidence.from_match(
                        self.relative_path(m.file_path), m.line_number, m.line_content
                    )
                )

        docker_matches = grep_files(
            self.repo_root,
            r"image:\s*\S+emulator|image:\s*\S+android|docker.*emulator",
            ("**/*.yml", "**/*.yaml"),
        )
        if docker_matches:
            signals.append("Docker emulator images")
            for m in docker_matches:
                evidence.append(
                    Evidence.from_match(
                        self.relative_path(m.file_path), m.line_number, m.line_content
                    )
                )

        kvm_matches = grep_files(
            self.repo_root,
            r"kvm|KVM|/dev/kvm",
            ("**/*.yml", "**/*.yaml"),
        )
        if kvm_matches:
            signals.append("KVM")
            for m in kvm_matches:
                evidence.append(
                    Evidence.from_match(
                        self.relative_path(m.file_path), m.line_number, m.line_content
                    )
                )

        avd_scripts = glob_files(self.repo_root, "**/create_avd*")
        avd_scripts.extend(glob_files(self.repo_root, "**/start_emulator*"))
        for script in avd_scripts:
            signals.append("AVD scripts")
            evidence.append(
                Evidence(
                    file_path=self.relative_path(script),
                    line_start=1,
                    line_end=1,
                    snippet=script.name,
                )
            )

        if signals:
            return DetectionResult(
                detected=True,
                description=", ".join(dict.fromkeys(signals)),
                evidence=evidence,
            )

        return DetectionResult.not_found("No emulator provisioning found")


class ArtifactsReportsDetector(BaseDetector):
    @property
    def name(self) -> str:
        return "Artifacts & Reports"

    @property
    def category(self) -> str:
        return "CI Artifacts"

    def detect(self) -> DetectionResult:
        evidence: list[Evidence] = []
        types: list[str] = []

        artifacts_matches = grep_files(
            self.repo_root,
            r"artifacts:\s*\n|paths:\s*\n\s*-",
            ("**/*.yml", "**/*.yaml"),
            multiline=True,
        )
        if artifacts_matches:
            types.append("artifacts")
            for m in artifacts_matches:
                evidence.append(
                    Evidence.from_match(
                        self.relative_path(m.file_path), m.line_number, m.line_content
                    )
                )

        junit_matches = grep_files(
            self.repo_root,
            r"reports:\s*\n\s*junit:|junit:\s*",
            ("**/*.yml", "**/*.yaml"),
            multiline=True,
        )
        if junit_matches:
            types.append("JUnit reports")
            for m in junit_matches:
                evidence.append(
                    Evidence.from_match(
                        self.relative_path(m.file_path), m.line_number, m.line_content
                    )
                )

        allure_matches = grep_files(
            self.repo_root,
            r"allure|Allure|ALLURE",
            ("**/*.yml", "**/*.yaml"),
        )
        if allure_matches:
            types.append("Allure")
            for m in allure_matches:
                evidence.append(
                    Evidence.from_match(
                        self.relative_path(m.file_path), m.line_number, m.line_content
                    )
                )

        path_matches = grep_files(
            self.repo_root,
            r"^\s*(?:(?:junit|path|outputDir)\s*:\s*|-\s+)(?:[^#\n]*)(?:build/|reports?|results?|screenshots?)[^#\n]*$",
            ("**/*.yml", "**/*.yaml", "Marathonfile"),
        )
        paths: list[str] = []
        for match in path_matches:
            value = re.sub(
                r"^\s*(?:(?:junit|path|outputDir)\s*:\s*|[-]\s+)",
                "",
                match.line_content,
                flags=re.IGNORECASE,
            ).strip(" '\"")
            if value:
                paths.append(value)
            evidence.append(
                Evidence.from_match(
                    self.relative_path(match.file_path), match.line_number, match.line_content
                )
            )

        if types:
            unique_paths = list(dict.fromkeys(paths))
            description = "Observed CI outputs: " + ", ".join(types)
            if unique_paths:
                description += "; paths: " + ", ".join(unique_paths[:8])
            return DetectionResult(
                detected=True,
                description=description,
                evidence=evidence,
                limitations=[
                    "Evidence reports repository declarations; artifact availability after a run "
                    "is not verified",
                    *(
                        [f"{len(unique_paths) - 8} additional paths are available in evidence"]
                        if len(unique_paths) > 8
                        else []
                    ),
                ],
            )

        return DetectionResult(
            detected=False,
            description="No CI artifacts or reports observed",
            limitations=["Dynamic CI includes and externally configured jobs are not resolved"],
        )


class NotificationsDetector(BaseDetector):
    @property
    def name(self) -> str:
        return "Notifications"

    @property
    def category(self) -> str:
        return "CI Notifications"

    def detect(self) -> DetectionResult:
        evidence: list[Evidence] = []

        channels = {
            "Teams": (
                r"teams\.microsoft\.com|outlook\.office\.com/webhook|office\.com/webhook"
                r"|microsoft\s*teams|TEAMS_WEBHOOK"
            ),
            "Slack": r"hooks\.slack\.com|SLACK_WEBHOOK|slackSend|slack-notify",
            "Discord": r"discord\.com/api/webhooks|DISCORD_WEBHOOK",
            "Telegram": r"api\.telegram\.org|TELEGRAM_(BOT_)?TOKEN",
            "E-mail": r"^\s*email:|mailto:|send-?mail",
            "Generic webhook": r"WEBHOOK_URL|webhook_url",
        }

        found: list[str] = []
        for channel, pattern in channels.items():
            matches = grep_files(
                self.repo_root,
                pattern,
                ("**/*.yml", "**/*.yaml", "**/*.sh", "Jenkinsfile"),
            )
            if not matches:
                continue
            found.append(channel)
            for m in matches:
                evidence.append(
                    Evidence.from_match(
                        self.relative_path(m.file_path), m.line_number, m.line_content
                    )
                )

        if found:
            return DetectionResult(
                detected=True,
                description=", ".join(found),
                evidence=evidence,
            )

        return DetectionResult.not_found("No notification hooks found")


class CachingDetector(BaseDetector):
    @property
    def name(self) -> str:
        return "Caching"

    @property
    def category(self) -> str:
        return "CI Optimization"

    def detect(self) -> DetectionResult:
        evidence: list[Evidence] = []

        cache_matches = grep_files(
            self.repo_root,
            r"cache:\s*\n|key:\s*|policy:\s*",
            ("**/*.yml", "**/*.yaml"),
            multiline=True,
        )
        for m in cache_matches:
            evidence.append(
                Evidence.from_match(self.relative_path(m.file_path), m.line_number, m.line_content)
            )

        gradle_cache_matches = grep_files(
            self.repo_root,
            r"\.gradle|gradle-cache|GRADLE_USER_HOME",
            ("**/*.yml", "**/*.yaml"),
        )
        for m in gradle_cache_matches:
            evidence.append(
                Evidence.from_match(self.relative_path(m.file_path), m.line_number, m.line_content)
            )

        if evidence:
            return DetectionResult(
                detected=True,
                description=f"Found {len(evidence)} cache configurations",
                evidence=evidence,
            )

        return DetectionResult.not_found("No caching configuration found")


class RetryFlakinessDetector(BaseDetector):
    @property
    def name(self) -> str:
        return "Retry/Flakiness Handling"

    @property
    def category(self) -> str:
        return "Test Stability"

    def detect(self) -> DetectionResult:
        evidence: list[Evidence] = []
        mechanisms: list[str] = []

        gitlab_retry_matches = grep_files(
            self.repo_root,
            r"^\s*retry:\s*\d+|retry:\s*\n\s*max:",
            ("**/*.yml", "**/*.yaml"),
            multiline=True,
        )
        if gitlab_retry_matches:
            mechanisms.append("GitLab retry")
            for m in gitlab_retry_matches:
                evidence.append(
                    Evidence.from_match(
                        self.relative_path(m.file_path), m.line_number, m.line_content
                    )
                )

        marathon_retry_matches = grep_files(
            self.repo_root,
            r"retryStrategy|strictMode|flakyTests",
            "**/Marathonfile*",
        )
        marathon_retry_matches.extend(
            grep_files(
                self.repo_root,
                r"retryStrategy|strictMode|flakyTests",
                "**/marathon*.yaml",
            )
        )
        if marathon_retry_matches:
            mechanisms.append("Marathon retry")
            for m in marathon_retry_matches:
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

        return DetectionResult.not_found("No retry/flakiness handling found")


def get_ci_cd_detectors(repo_root: Path) -> list[BaseDetector]:
    return [
        CIEntrypointsDetector(repo_root),
        JobsStagesDetector(repo_root),
        ScheduledSignalsDetector(repo_root),
        MarathonIntegrationDetector(repo_root),
        VariablesControlDetector(repo_root),
        EmulatorProvisioningDetector(repo_root),
        ArtifactsReportsDetector(repo_root),
        NotificationsDetector(repo_root),
        CachingDetector(repo_root),
        RetryFlakinessDetector(repo_root),
    ]
