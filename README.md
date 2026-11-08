# plugin-platform-copilot

Copilot for [Liminal](https://github.com/pcxmac-dev/liminal-charts): an AI assistant plugin (plugin API
2.0, `liminal_libs.assistants`, a platform plugin) that evaluates standardized arguments (a question
over headlines, an assessment, a report; a judge over earlier answers) through GitHub Copilot on your
own GitHub token, with Copilot's plans, models and prices written in.

The user, 2026-11-08: "also add an AI plugin for Copilot", beside the three asked for on 2026-11-03:
"AI plugins that have a vanilla API, are compliant with the rest of the plugin structure (setup /
connecting methods / etc) but allow interfacing with Claude, Grock and ChatGPT Codex via API key, an
email / account name"; "the ai plugins should support free"; each with "the different plans and
capabilities written in to it", "CI catching the disparity between code and latest rates through unit
testing".

## How it reaches Copilot

Through GitHub's [Copilot SDK](https://github.com/github/copilot-sdk) (`github-copilot-sdk`, generally
available since 2026-06-02 and open to every Copilot plan, Copilot Free among them for personal use):
the documented way an application talks to Copilot. The SDK runs Copilot's runtime (the Copilot CLI's)
as a child process; the runtime makes the model calls and bills them to your plan. The plugin starts
it for a call and stops it after, in the SDK's locked-down "empty" mode, with no tool at all (every
permission request refused), your argument's system prompt in place of the agent's, your token passed
explicitly (your stored Copilot or `gh` logins and any `GH_TOKEN`/`GITHUB_TOKEN` ignored), and a child
environment without the machine's other credentials. Its home is `assistants/copilot/` in the data
folder.

GitHub Models (`models.github.ai`), the OpenAI-compatible endpoint that once answered on a GitHub
token, was retired on 2026-07-30 for every customer; the chat endpoints and token exchange GitHub's own
editors use are not documented for anyone else. Neither is used.

## Setup

- `copilot` on the Plugins view (the AI assistants group): Setup takes `COPILOT_API_KEY` (read as
  `COPILOT_GITHUB_TOKEN` too), the GitHub token, and `COPILOT_ACCOUNT`, the GitHub account (or email)
  the token belongs to, shown with its evaluations and sent to no one (the SDK takes no account field;
  Connect says whether the token is that account's).
- The token: on GitHub, [Fine-grained personal access tokens](https://github.com/settings/personal-access-tokens/new),
  the resource owner your **personal account** (not an organization), repository access **Public
  repositories** (nothing of a repository is needed), and under **Permissions**, the **Account** tab,
  **Add permissions**, **Copilot Requests**; then **Generate token**. An OAuth token (`gho_`) or a
  GitHub App user token (`ghu_`) is taken too; a classic token (`ghp_`) is not, and the plugin refuses
  it before sending anything.
- Plan: `COPILOT_PLAN`, the plan your account is on (Copilot sends no limits the plans differ by, so
  the plan is what you choose). `free` by default, which sends:

  | `COPILOT_PLAN` | Plan | Price | AI credits a month | Models |
  | --- | --- | --- | --- | --- |
  | `free` | Copilot Free | free | an allowance (its size not published) | auto only |
  | `student` | Copilot Student | free for verified students | an allowance (not published) | auto only |
  | `pro` | Copilot Pro | $10 a month | 1,500 (1,000 base, 500 flex) | a selection: no Opus, Fable, Sol, Astra or Gemini 4 Argon |
  | `pro-plus` | Copilot Pro+ | $39 a month | 7,000 (3,900 base, 3,100 flex) | every model in the table |
  | `max` | Copilot Max | $100 a month | 20,000 (10,000 base, 10,000 flex) | every model, priority access |
  | `business` | Copilot Business | $19 a seat a month | 1,900 a user, pooled | as the organization's policies allow |
  | `enterprise` | Copilot Enterprise | $39 a seat a month | 3,900 a user, pooled | as the enterprise's policies allow |
  | `access` | Copilot access | $0 with GitHub Enterprise Cloud, $10 standalone | none: metered from the first use | Enterprise's |

  1 AI credit = $0.01; tokens are billed at each model's published rate; the allowance renews on the
  1st of each month at 00:00 UTC. Past it, a paid plan goes on only with a budget for additional
  usage (a $0 budget with "Stop usage when budget limit is reached" keeps it from ever spending more).
  GitHub publishes no rate limits for any plan.
- Model: `COPILOT_MODEL`, `auto` by default (Copilot chooses the model for each prompt; the only one
  on Free and Student; an answer records the model that answered and costs that model's price). The
  table holds Copilot's 25 text models with their ids, prices per million tokens (input, a cached
  input token, output), plans, context and reasoning: GPT-6 Luna and Claude Haiku 5.5 the cheapest
  ($0.10 in, $0.50 out), up to GPT-6 Astra and Claude Fable 5.1 ($10 and $50). `COPILOT_EFFORT` sets
  the reasoning level where the model takes one.
- Caps on this machine, every database together: `COPILOT_REQUESTS_PER_DAY` (50),
  `COPILOT_TOKENS_PER_DAY` (200,000), `COPILOT_MAX_OUTPUT_TOKENS` (1,024: kept for the Plugins view;
  the SDK takes no output cap, so it is not sent).
- Connect checks the token (the runtime's sign-in), lists the models the server has for your account
  and compares them and their prices with the table, checks the account named, shows the allowance
  left, and sends one answer of a few tokens with Copilot's own count of its cost.

Nothing is sent from an offline copy of the app (`LIMINAL_OFFLINE`).

## Install

Into the app's environment, from the app's folder, with the SDK, then its runtime once:

```powershell
.venv\Scripts\python.exe -m pip install "plugin-platform-copilot[sdk] @ git+https://github.com/pcxmac-dev/plugin-platform-copilot@main"
.venv\Scripts\python.exe -m copilot download-runtime
```

Python 3.11 or later (the SDK's floor). Without the `sdk` extra the plugin loads and is set up, and
Connect says the SDK is missing. The app loads it on its next start. Save the token with the app's
`tools/set-key.ps1` or on the Plugins view (it is read from your user environment variables only,
never written to a file).

## Tests

`python -m pytest -q`: fake answers and a fake SDK, nothing imported, started or sent.
`LIMINAL_VENDOR_PAGES=1` adds the weekly page check (every model's price and plans, its place in the
Copilot CLI and every plan's allowance against GitHub's pages, row by row); with the `sdk` extra
installed, `tests/test_sdk_surface.py` checks the SDK's options and types the runtime relies on.
