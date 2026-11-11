# Changelog

## 0.2.0 (2026-11-11)

Its API on its page (plugin API 2.2, liminal-libs 1.49.0; the user: "each plugin should reflect the the API its attached
to, and present links that provide documentation, the plugin interface should more or less contain what it already
has, BUT, it should also expose more of what the API is about"). `CopilotPlugin.apis` (apis.py) holds two cards, from
GitHub's pages, verified 2026-11-11:
- the GitHub Copilot SDK: what it is, the package and the 1.x release it is written for, how the token is given, the
  limits (no rate limits published; the plans' monthly AI credits), what it costs, and GitHub's pages (the SDK's docs,
  the Python reference, the source repository, its changelog and releases, PyPI, authentication and tokens, the SDK's
  usage and billing, models and pricing, plans, usage limits, supported models, the status page, the new-token page, the
  terms); every part of it (the client and its runtime, authentication, sessions, events, models, the account's quota,
  tools and permissions, the system message, Copilot's models and billing and its API service, which the plugin uses;
  hooks, MCP servers, custom agents and skills, your own model keys, persistence, images and structured output,
  observability and Copilot's REST API, which it does not) and its calls (the ten the runtime makes, and others);
- the Copilot runtime it drives (the Copilot CLI's, the SDK's child process over JSON-RPC): its transports, the empty
  mode, its home, its download, its sign-in, its network, and the setup, CLI reference, allowlist and protocol pages.

`PRICING`, `PLANS_PAGE` and `MODELS_PAGE` come from apis.py. Nothing it sends or shows changes; the instance keeps
nothing of a run, so `api_facts()` says nothing. Needs liminal-libs>=1.49.0. A test runs the real runtime on a recording
fake SDK and checks that the card names exactly the SDK calls it makes; the weekly page check asks each address too.

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
