# Changelog

## 0.1.0 (2026-11-08)

The first release: `CopilotPlugin` (an `AssistantPlugin`, plugin API 2.0) and `CopilotAssistant` on
GitHub's Copilot SDK (`github-copilot-sdk` 1.x, the `sdk` extra), GitHub Models having been retired on
2026-07-30. The SDK's runtime is started for a call and stopped after it, in its empty mode, with no
tool, every permission request refused, the token passed explicitly and the machine's other
credentials kept out of its environment.

The plans (Copilot Free, which sends through auto model selection; Student; Pro, Pro+ and Max with
their AI credits; Business, Enterprise and Copilot access), the 25 text models with Copilot's ids,
their prices per million tokens, plans, context and reasoning (auto by default), and the pages they
were written from, verified 2026-11-08. Connect checks the token, compares the models and prices the
server lists with the tables, checks the account named and shows the allowance left; the weekly CI run
reads GitHub's pages again and compares every model's price and plans and every plan's allowance row by
row. `COPILOT_API_KEY` (read as `COPILOT_GITHUB_TOKEN` too) and `COPILOT_ACCOUNT`; a classic `ghp_`
token is refused before anything is sent; every error is said in words and scrubbed of the token and
the account. Its icon is its maker's logo, GitHub Copilot's pilot (`ICON = "copilot"`, liminal-libs
1.33.0's icons.js).
