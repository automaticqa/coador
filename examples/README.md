# Examples

## Local Android example

The [mini Android fixture](../tests/fixtures/mini_android) is a synthetic
multi-module project included under this repository's MIT license. It uses
fictional application IDs, example domains and non-functional test credentials.
It demonstrates Compose UI, Hilt, network fakes, test runners and CI configuration.

After installing Coador from the checkout, run from the repository root:

```bash
coador scan tests/fixtures/mini_android --kb-dir /tmp/coador-example
coador overview tests/fixtures/mini_android --kb-dir /tmp/coador-example
coador show 07_testing instrumentation_runner tests/fixtures/mini_android --kb-dir /tmp/coador-example
coador search "test runner" tests/fixtures/mini_android --kb-dir /tmp/coador-example
```

The scan generates the current schema v3 profile and Markdown layers outside the
source tree. The profile reports project `mini-android`, with runner
`com.example.mini.HiltTestRunner` supported by fixture source evidence.
No Android SDK, Gradle execution or network is needed. The fixture illustrates
static scanning; it is not a claim that an APK has been built or its UI tests run.

Generated profiles and manifests are not committed. Regenerate them using the
installed version so examples reflect the current model and detectors.

## Public Android projects

The [README walkthrough](../README.md#practical-example) and
[onboarding recipes](../docs/onboarding-recipes.md) cite pinned revisions of
Google's public Android repositories, including
[Now in Android](https://github.com/android/nowinandroid/tree/12f80da6518e161ed16a06a68e71fb8a873576d6).
Now in Android and the Android sample sources referenced there are Apache-2.0
licensed; quoted upstream material retains its original license and attribution.

Those walkthroughs require downloading public source. Keep generated knowledge
outside each checkout with `--kb-dir`.
