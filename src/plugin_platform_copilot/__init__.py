"""Copilot (GitHub) for Liminal: an AI assistant plugin (liminal_libs.assistants, plugin API 2.0) that
evaluates standardized arguments through GitHub Copilot on your own GitHub token, by GitHub's Copilot
SDK, with Copilot's plans, models and prices written in, dated, and checked against GitHub's pages.

A Liminal plugin released on its own, registered under the entry point group `liminal.providers` as
`copilot`: the plugin `CopilotPlugin` (ASSISTANT below), its assistant `CopilotAssistant`
(assistant.py), the SDK driven by runtime.py. It relies on plugin API 2.0 and nothing of the apps.

The user, 2026-11-08: "also add an AI plugin for Copilot", beside the three asked for on 2026-11-03:
"AI plugins that have a vanilla API, are compliant with the rest of the plugin structure (setup /
connecting methods / etc) but allow interfacing with Claude, Grock and ChatGPT Codex via API key, an
email / account name".

The API: GitHub's Copilot SDK (github-copilot-sdk, generally available since 2026-06-02 and open to
every Copilot plan, Copilot Free among them, for personal use) is the documented way an application
reaches Copilot; it runs Copilot's runtime as a child process and the runtime makes the model calls.
GitHub Models (models.github.ai), the OpenAI-compatible endpoint that once answered on a GitHub token,
was retired on 2026-07-30 for every customer, and the chat endpoints and token exchange GitHub's
editors use are not documented for anyone else: neither is used. The SDK is the `sdk` extra
(`pip install "plugin-platform-copilot[sdk]"`, then `python -m copilot download-runtime` once).

What the user sets (the Plugins view's Setup, or the app's key script): `COPILOT_API_KEY` (read as
`COPILOT_GITHUB_TOKEN` too), the GitHub token: a fine-grained personal access token of your own
account with the Copilot Requests permission (a classic ghp_ token is refused before it is sent);
`COPILOT_ACCOUNT`, the GitHub account (or email) the token belongs to, shown with its evaluations and
sent to no one (the SDK takes no account field; Connect says whether the token is that account's);
its plan `COPILOT_PLAN` (free: Copilot Free; student, pro, pro-plus, max, business, enterprise, access),
its model `COPILOT_MODEL` (auto by default: Copilot chooses, the only model on Free and Student), its
caps on this machine `COPILOT_REQUESTS_PER_DAY` (50), `COPILOT_TOKENS_PER_DAY` (200,000),
`COPILOT_MAX_OUTPUT_TOKENS` (1,024; the SDK takes no output cap, so it is not sent), and
`COPILOT_EFFORT` (the reasoning level, where the model takes one).

The user, 2026-11-03: "the ai plugins should support free, and if that means they have no API access,
then so be it": Copilot Free reaches the SDK, so the free plan sends, through auto model selection
(an allowance of GitHub AI Credits a month, its size not published). "every time any of the three
vendors changes their plans/rates there will have to be a way to query through the plugin to update
itself, or worst case, just version up every time w/ CI catching the disparity between code and
latest rates through unit testing": Connect compares the models and prices the server lists with
the tables and shows the allowance left; the weekly CI run reads GitHub's pricing, plans and models
pages (SOURCES) and fails when a written-in figure is gone or a model's price or plans changed,
which is a new release of this plugin.
"""
from __future__ import annotations

from dataclasses import replace
from pathlib import Path

from liminal_libs.assistants import AssistantPlugin, Caps, Model, Plan, Source, Usage
from liminal_libs.layout import Database
from liminal_libs.sources.keys import KeyVar

from .assistant import AUTO, CopilotAssistant
from .runtime import SDK_WRITTEN_FOR, SdkRuntime

__all__ = ["ASSISTANT", "CopilotPlugin", "CopilotAssistant", "PLANS", "MODELS", "SOURCES", "VERIFIED", "AUTO",
           "INDIVIDUAL", "ORGANIZATION", "PRICING", "PLANS_PAGE", "MODELS_PAGE", "RUNTIME_HOME", "SDK_WRITTEN_FOR"]

VERIFIED = "2026-11-08"  # the day the tables below were checked against SOURCES
RUNTIME_HOME = "assistants/copilot/"  # the Copilot runtime's home (COPILOT_HOME), in the data folder

# Copilot's plans (docs.github.com/en/copilot/get-started/plans and .../billing-and-usage/individuals/billing,
# 2026-11-08): usage is billed in GitHub AI Credits (1 AI credit = $0.01 USD), tokens at each model's
# published rate; every plan has a monthly allowance (renewed on the 1st, 00:00 UTC, unused credits lost)
# except Copilot access, metered from the first use. GitHub publishes no rate limits for any plan.
# The paid individual plans: the price a month in dollars, the base credits, the flex allotment, the total.
INDIVIDUAL = {"pro": (10, 1_000, 500, 1_500), "pro-plus": (39, 3_900, 3_100, 7_000), "max": (100, 10_000, 10_000, 20_000)}
# The organizations' plans: the price a granted seat a month in dollars, the AI credits a user a month (pooled).
ORGANIZATION = {"business": (19, 1_900), "enterprise": (39, 3_900)}
BUDGET = "the plan's allowance, unless you set a budget for additional usage (a $0 budget that stops usage keeps it so)"


def _individual(name: str) -> str:
    usd, base, flex, total = INDIVIDUAL[name]
    return f"${usd} a month: {total:,} AI credits a month ({base:,} base and {flex:,} flex)"


def _organization(name: str) -> str:
    usd, credits = ORGANIZATION[name]
    return f"${usd} a seat a month: {credits:,} AI credits a user a month, pooled in the organization"


PLANS = (
    Plan("free", "Copilot Free", models=(AUTO,), price="free: an allowance of GitHub AI Credits a month (its size not published)",
         note="auto model selection only (Copilot chooses the model); for an individual without Copilot through an "
              "organization; the Copilot SDK is open to it for personal use; the allowance renews on the 1st (00:00 UTC)"),
    Plan("student", "Copilot Student", models=(AUTO,),
         price="free for verified students: an allowance of GitHub AI Credits a month (its size not published)",
         note="auto model selection only (Copilot chooses the model)"),
    Plan("pro", "Copilot Pro", price=_individual("pro"), spend_cap=BUDGET,
         note="a selection of models: not Claude Opus or Fable, GPT-6 Astra, the Sol models or Gemini 4 Argon"),
    Plan("pro-plus", "Copilot Pro+", price=_individual("pro-plus"), spend_cap=BUDGET, note="every model in the table"),
    Plan("max", "Copilot Max", price=_individual("max"), spend_cap=BUDGET,
         note="every model in the table, with priority access to the premium ones"),
    Plan("business", "Copilot Business", price=_organization("business"),
         spend_cap="the organization's pool of credits, then its budget for additional usage",
         note="the organization's policies decide the models and whether the Copilot CLI (the SDK's runtime) may run"),
    Plan("enterprise", "Copilot Enterprise", price=_organization("enterprise"),
         spend_cap="the enterprise's pool of credits, then its budget for additional usage",
         note="the enterprise's policies decide the models and whether the Copilot CLI (the SDK's runtime) may run"),
    Plan("access", "Copilot access", price="$0 a seat with GitHub Enterprise Cloud, $10 a user a month as Copilot "
                                           "Standalone: no allowance included",
         spend_cap="none included: every answer is metered at the model's rate",
         note="Copilot Enterprise's models and features, for eligible enterprises; billed from the first use"),
)

PAID = ("pro", "pro-plus", "max", "business", "enterprise", "access")  # every paid plan reaches these (Pro's selection)
PREMIUM = ("pro-plus", "max", "business", "enterprise", "access")  # Pro+ and up: not on Pro
MILLION = 1_000_000  # the context window Copilot's CLI runtime (the SDK's) offers the models that have one that long
FABLE = ("Powerful; a cache write $12.50; Anthropic keeps its prompts and answers by default (its safety classifiers); "
         "in an organization an administrator enables it")

# Copilot's text models (docs.github.com/en/copilot/reference/copilot-billing/models-and-pricing and
# .../ai-models/supported-models, 2026-11-08), with the ids Copilot's runtime takes: prices per million
# tokens at the default tier (input, output, a cached input token), the context window, the plans that
# reach it, whether its reasoning level can be set (COPILOT_EFFORT); auto first (the default), then the
# cheapest first. Cache writes (Anthropic's models, GPT-5.6 and later) have a price of their own, in the
# notes: an answer's cost here counts them as input. Left out: GPT-5.4 nano (only in the Codex extension
# for VS Code, not in the CLI), Claude Opus 4.8 fast mode (a preview), Claude Sonnet 4.6 (retired
# 2026-09-01, kept on annual plans only).
MODELS = (
    Model(AUTO, "Auto (Copilot chooses)", 0.0, 0.0,
          note="Copilot picks the model for each prompt among those the plan and its policies allow, and bills it at that "
               "model's rate (paid plans: 10% off in Copilot Chat and cloud agent); an answer names the model chosen and "
               "costs that model's price here; the only model on Free and Student"),
    Model("gpt-6-luna", "GPT-6 Luna", 0.10, 0.50, 0.01, MILLION, PAID, True,
          note="Lightweight, the cheapest; prompts over 272K tokens cost $0.20 in and $0.75 out; a cache write $0.125"),
    Model("claude-haiku-5.5", "Claude Haiku 5.5", 0.10, 0.50, 0.01, MILLION, PAID, True,
          note="Lightweight; prompts over 100K tokens cost $0.50 in and $2.50 out; a cache write $0.125"),
    Model("gpt-5.6-luna", "GPT-5.6 Luna", 0.20, 1.20, 0.02, MILLION, PAID, True,
          note="Lightweight; prompts over 200K tokens cost $0.40 in and $1.80 out; a cache write $0.25"),
    Model("mai-code-1.1-flash", "MAI-Code-1.1-Flash", 0.20, 1.20, 0.02, None, PAID,
          note="Lightweight, Microsoft's; its checkpoints change over time"),
    Model("gemini-3.8-flash", "Gemini 3.8 Flash", 0.75, 3.75, 0.075, None, PAID,
          note="Versatile; promotional prices through 2026-12-31"),
    Model("claude-haiku-4.5", "Claude Haiku 4.5", 1.00, 5.00, 0.10, None, PAID, note="Versatile; a cache write $1.25"),
    Model("gpt-6.1-terra", "GPT-6.1 Terra", 1.00, 5.00, 0.05, MILLION, PAID, True,
          note="Versatile; prompts over 272K tokens cost $2.00 in and $7.50 out; a cache write $1.25"),
    Model("gpt-5.3-codex", "GPT-5.3-Codex", 1.75, 14.00, 0.175, MILLION, PAID, True,
          note="Powerful; Copilot's long-term support model, the one used when no other is available"),
    Model("claude-sonnet-5", "Claude Sonnet 5", 2.00, 10.00, 0.20, MILLION, PAID, True, note="Versatile; a cache write $2.50"),
    Model("claude-sonnet-5.5", "Claude Sonnet 5.5", 2.00, 10.00, 0.10, MILLION, PAID, True,
          note="Versatile; a cache write $2.50"),
    Model("gpt-5.6-terra", "GPT-5.6 Terra", 2.00, 12.00, 0.20, MILLION, PAID, True,
          note="Versatile; prompts over 272K tokens cost $4.00 in and $18.00 out; a cache write $2.50"),
    Model("grok-4.5", "Grok 4.5", 2.00, 6.00, 0.50, None, PAID,
          note="Versatile; prompts over 200K tokens cost $4.00 in and $12.00 out"),
    Model("grok-4.6", "Grok 4.6", 2.00, 6.00, 0.50, None, PAID,
          note="Versatile; prompts over 200K tokens cost $4.00 in and $12.00 out"),
    Model("grok-4.7", "Grok 4.7", 2.00, 6.00, 0.50, None, PAID,
          note="Versatile; prompts over 200K tokens cost $4.00 in and $12.00 out"),
    Model("gpt-6-sol", "GPT-6 Sol", 2.00, 10.00, 0.20, MILLION, PREMIUM, True,
          note="Powerful; prompts over 272K tokens cost $4.00 in and $15.00 out; a cache write $2.50"),
    Model("gpt-6.1-sol", "GPT-6.1 Sol", 2.00, 10.00, 0.10, MILLION, PREMIUM, True,
          note="Powerful; prompts over 272K tokens cost $4.00 in and $15.00 out; a cache write $2.50"),
    Model("gemini-4-argon", "Gemini 4 Argon", 2.00, 10.00, 0.10, None, PREMIUM,
          note="Powerful; promotional prices until 2026-12-01"),
    Model("kimi-k3", "Kimi K3", 3.00, 15.00, 0.30, MILLION, PAID, True, note="Powerful, Moonshot AI's"),
    Model("gpt-5.6-sol", "GPT-5.6 Sol", 4.00, 20.00, 0.40, MILLION, PREMIUM, True,
          note="Powerful; prompts over 272K tokens cost $8.00 in and $30.00 out; a cache write $5.00"),
    Model("claude-opus-5.5", "Claude Opus 5.5", 4.00, 20.00, 0.20, MILLION, PREMIUM, True,
          note="Powerful; a cache write $5.00"),
    Model("claude-opus-4.8", "Claude Opus 4.8", 5.00, 25.00, 0.50, MILLION, PREMIUM, True,
          note="Powerful; a cache write $6.25"),
    Model("claude-opus-5", "Claude Opus 5", 5.00, 25.00, 0.50, MILLION, PREMIUM, True, note="Powerful; a cache write $6.25"),
    Model("gpt-6-astra", "GPT-6 Astra", 10.00, 50.00, 1.00, MILLION, PREMIUM, True,
          note="Powerful, OpenAI's flagship; prompts over 272K tokens cost $20.00 in and $75.00 out; a cache write $12.50"),
    Model("claude-fable-5", "Claude Fable 5", 10.00, 50.00, 1.00, MILLION, PREMIUM, True, note=FABLE),
    Model("claude-fable-5.1", "Claude Fable 5.1", 10.00, 50.00, 0.25, MILLION, PREMIUM, True, note=FABLE),
)

PRICING = "https://docs.github.com/en/copilot/reference/copilot-billing/models-and-pricing"
PLANS_PAGE = "https://docs.github.com/en/copilot/get-started/plans"
MODELS_PAGE = "https://docs.github.com/en/copilot/reference/ai-models/supported-models"

# Where the tables come from, with what each page must still show (verify.check_sources, weekly in CI; the
# models' prices and plans are compared row by row there too: tests/test_vendor_pages.py).
SOURCES = (
    Source(PRICING, "the models' prices", "1 AI credit = $0.01 USD", tuple(m.title for m in MODELS[1:])),
    Source(PLANS_PAGE, "the plans, their prices and AI credits", "Discover the plans available for Copilot.",
           (*(p.title for p in PLANS), *(f"${v[0]} USD" for v in (*INDIVIDUAL.values(), *ORGANIZATION.values())),
            *(f"{n:,}" for v in INDIVIDUAL.values() for n in v[1:]), *(f"{v[1]:,}" for v in ORGANIZATION.values()),
            "auto model selection only")),
    Source("https://docs.github.com/en/copilot/concepts/billing-and-usage/individuals/billing",
           "the allowances, their renewal and additional usage",
           "Your Copilot plan includes a monthly allowance of GitHub AI Credits.",
           ("1 AI credit = $0.01 USD", "first day of each calendar month", "auto model selection only", "Copilot CLI")),
    Source(MODELS_PAGE, "the models on each plan and in the Copilot CLI", "Learn about the supported AI models in GitHub Copilot.",
           ("Copilot Student and Copilot Free users have access to models through auto model selection only",
            *(m.title for m in MODELS[1:]))),
    Source("https://docs.github.com/en/copilot/how-tos/copilot-cli/set-up-copilot-cli/authenticate-copilot-cli",
           "the tokens Copilot's runtime takes", "Authenticating with environment variables",
           ("Copilot Requests", "github_pat_", "ghp_", "COPILOT_GITHUB_TOKEN")),
    Source("https://docs.github.com/en/copilot/how-tos/copilot-sdk/features/usage-and-billing",
           "the SDK's prices, usage and quota fields Connect reads", "AI credit cost per batch of input tokens",
           ("billing.tokenPrices.inputPrice", "billing.tokenPrices.batchSize", "totalNanoAiu", "premium_interactions",
            "entitlementRequests")),
    Source("https://github.blog/changelog/2026-06-02-copilot-sdk-is-now-generally-available/",
           "the SDK on every plan, Copilot Free among them", "Copilot SDK",
           ("Copilot Free", "personal use", "pip install github-copilot-sdk")),
)


class CopilotPlugin(AssistantPlugin):
    """Copilot: the plugin (see the module's docstring)."""

    ICON = "copilot"  # its maker's logo (icons.js, liminal-libs 1.33.0): GitHub Copilot's pilot, a head with goggles
    name = "copilot"
    title = "Copilot"
    about = "GitHub Copilot's models through GitHub's Copilot SDK: evaluations of standardized arguments on your GitHub token"
    vendor = "GitHub"
    signup = "https://github.com/settings/personal-access-tokens/new"
    order = 503
    api = "2.0"
    assistant = CopilotAssistant
    plans = PLANS
    models = MODELS
    default_model = AUTO
    verified = VERIFIED
    sources = SOURCES
    caps = Caps()  # 50 requests and 200,000 tokens a day on this machine, 1,024 output tokens an answer (not sent)
    efforts = ("", "low", "medium", "high", "xhigh", "max")  # the SDK's reasoning_effort; "" leaves the model's default
    key_aliases = ("COPILOT_GITHUB_TOKEN",)  # the variable Copilot's own runtime reads first
    account_label = "account (GitHub username or email)"
    account_hint = ("the GitHub account the token belongs to: shown with its evaluations, sent to no one (the SDK takes no "
                    "account field); Connect says whether the token is that account's")
    databases = (Database(RUNTIME_HOME, "the Copilot runtime's home (COPILOT_HOME): its empty mode keeps no session there",
                          engine="files"),)

    @property
    def keys(self) -> tuple[KeyVar, ...]:
        key, account = super().keys
        return (replace(key, label="GitHub token (Copilot Requests)",
                        hint="a fine-grained personal access token (github_pat_) of your own account with the Copilot "
                             "Requests account permission; a classic ghp_ token is not taken"), account)

    @property
    def plan_note(self) -> str:
        return ("its plan is what you choose: Copilot sends no limits the plans differ by; Connect checks the token, "
                f"compares the models and prices listed with the tables and shows the allowance left (the tables "
                f"verified {self.verified or 'at release'})")

    def cost(self, model_id: str, usage: Usage) -> float | None:
        """What an answer cost by the table's prices; None for auto (billed at the rate of the model it
        chose: an answer names that model, and costs its price) and for a model the table has not."""
        return None if model_id == AUTO else super().cost(model_id, usage)

    def build(self, settings, session=None, now=None):
        """Its Assistant, the runtime's home beside the settings' main file (the data folder)."""
        a = super().build(settings, session=session, now=now)
        db = getattr(settings, "db_path", None)
        if isinstance(a.runtime, SdkRuntime) and db and str(db) != ":memory:":
            a.runtime.home = Path(db).parent / RUNTIME_HOME
        return a


ASSISTANT = CopilotPlugin()
