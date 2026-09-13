# Verification — GitHub metadata and HEAD

Executed 2026-08-06 via GitHub REST (`gh api repos/<owner>/<repo>`) plus independent `git ls-remote <html_url> refs/heads/<default_branch>`.

| requested/canonical repo | HEAD | pushed_at UTC | SPDX | archived |
|---|---|---|---|---|
| microsoft/agent-framework | 74a144085a5fd05921b473001528f3ae0725b76a | 2026-08-05T22:15:36Z | MIT | false |
| UKGovernmentBEIS/inspect_ai | a7523133367edde0ea2859a271b36a40de77f948 | 2026-08-05T22:21:00Z | MIT | false |
| harbor-framework/harbor | 4698544ea9d5ee95d01b05aeaa9ccbd161d5a7f6 | 2026-08-06T04:34:08Z | Apache-2.0 | false |
| cline/cline | 81cce3d70e10244cdde40dbd0eb0bb711c93006d | 2026-08-06T08:09:40Z | Apache-2.0 | false |
| jayminwest/overstory | ff38f3f76f084abcc34f519bcaa69580f6e53cf1 | 2026-05-28T17:12:46Z | MIT | **true** |
| Arize-ai/openinference | 8053d845d90ae1ad4796c7e2c5eaf807e932f5b4 | 2026-08-05T15:30:22Z | Apache-2.0 | false |
| open-telemetry/semantic-conventions-genai | 4a39b6ef1363fab57bc40e18c82abb32cc89ebcd | 2026-08-05T14:13:32Z | Apache-2.0 | false |
| SWE-agent/SWE-ReX | 5c995c365dfb1fd5bc56fda688be5d8538f9931f | 2026-08-03T22:06:15Z | MIT | false |
| alibaba/OpenSandbox → opensandbox-group/OpenSandbox | 47d85df848f957f5e7b3231e435ef9333a57537c | 2026-08-06T05:57:38Z | Apache-2.0 | false |
| microsoft/magentic-ui | d3c9d13c39288257286a66daabf7c5b5fb72ee69 | 2026-08-05T23:43:11Z | MIT | false |
| dagworks-inc/burr → apache/burr | a05875f09687b958bd83a5767be25d37821bee83 | 2026-08-05T19:53:51Z | Apache-2.0 | false |
| SWE-agent/SWE-agent | 3ea751c087f32b16e039a2233dd6eefecef325d5 | 2026-08-03T22:06:16Z | MIT | false |
| aaif-goose/goose | dafdbb7364cb8f145a71e2fd4e080136e225ad14 | 2026-08-06T07:15:41Z | Apache-2.0 | false |
| OpenHands/software-agent-sdk | da6f5463be9364e55db40435017549340c73bdea | 2026-08-06T07:30:29Z | MIT | false |
| ThousandBirdsInc/chidori | 4bd624028cda6026b7040e57d94dc9c70096f46d | 2026-08-06T04:16:18Z | Apache-2.0 | false |
| letta-ai/letta-code | 455b13bfa127aae80bdca90aeaf793e1dfea9a7b | 2026-08-06T08:01:04Z | Apache-2.0 | false |
| getzep/graphiti | 425bf2481b51437e43455e09d241c5f46e3d95f3 | 2026-08-05T07:38:13Z | Apache-2.0 | false |
| pydantic/pydantic-ai | 916fc83e8929470679db5ac1b3065bda5d5f4253 | 2026-08-06T05:17:31Z | MIT | false |
| assistant-ui/assistant-ui | e70da91866a5ac880472fbcf23039909270f7623 | 2026-08-06T08:08:22Z | MIT | false |

Follow-up entity verification outside the original 19 after Overstory archive discovery:

| repo | HEAD | license/status evidence |
|---|---|---|
| jayminwest/warren | 8eb58af4317c0fc91194edceddbb8f3c25570cf0 | MIT; active; upstream successor named by Overstory; v0.14.0 plus 31 HEAD commits |

Interpretation limits:

- This table defines exactly what “metadata-verified set” means; it is not every repository encountered in Wave 1.
- `pushed_at`, archive, release and HEAD are temporal. Re-run before implementation.
- SPDX metadata is a technical screen, not legal review.
- Source/test files were inspected, but external suites were not executed.
