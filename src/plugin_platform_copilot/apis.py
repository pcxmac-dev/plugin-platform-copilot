"""What the plugin attaches to (plugin API 2.2, liminal_libs.sources.apis), as GitHub's own pages describe it (read
2026-11-11): GitHub's Copilot SDK (its docs and its source repository), what it reaches (Copilot's models, plans and AI
credits, Copilot's API service) and the local runtime it drives (the Copilot CLI's, a child process the SDK speaks
JSON-RPC to). The SDK's parts the plugin uses come first, then the rest of the SDK. The tables the evaluations are
costed and planned by stay the plugin's (PLANS, MODELS, SOURCES). The user, 2026-11-11: "each plugin should reflect
the the API its attached to, and present links that provide documentation ... it should also expose more of what the
API is about"."""
from __future__ import annotations

from liminal_libs.sources.apis import Api, Area, Call, Link

from .runtime import SDK_PACKAGE, SDK_WRITTEN_FOR

DOCS = "https://docs.github.com/en/"
SDK_DOCS = DOCS + "copilot/how-tos/copilot-sdk"
CLI_REF = DOCS + "copilot/reference/copilot-cli-reference/"
REPO = "https://github.com/github/copilot-sdk"
README = REPO + "/blob/main/python/README.md"
PRICING = DOCS + "copilot/reference/copilot-billing/models-and-pricing"
PLANS_PAGE = DOCS + "copilot/get-started/plans"
MODELS_PAGE = DOCS + "copilot/reference/ai-models/supported-models"
VERIFIED = "2026-11-11"  # the day these facts were read from GitHub's pages

CLIENT = "Client and runtime"
SESSIONS = "Sessions"
EVENTS = "Events and streaming"
MODELS = "Models"
QUOTA = "Account quota"

COPILOT_SDK = Api(
    name="GitHub Copilot SDK",
    maker="GitHub",
    about=("GitHub's SDK for putting Copilot's agent in an application (Python, TypeScript, Go, .NET, Java, Rust): a "
           "CopilotClient that starts Copilot's runtime and speaks JSON-RPC to it, sessions that take prompts and send "
           "back events, the models the account reaches and its allowance, with custom tools, permission handling, "
           "hooks, MCP servers, custom agents and skills, bring-your-own-key providers, structured output and "
           "telemetry. The runtime makes the model calls to GitHub Copilot and bills them to the account's plan."),
    kind="sdk",
    base=f"copilot ({SDK_PACKAGE}: the plugin's sdk extra)",
    version=f"{SDK_PACKAGE} {SDK_WRITTEN_FOR} (the 1.x API)",
    auth=("a GitHub token given as github_token, the machine's stored logins and environment tokens left out "
          "(use_logged_in_user False): a fine-grained personal access token with the Copilot Requests permission, "
          "or an OAuth (gho_) or GitHub App user (ghu_) token; a classic ghp_ token is not taken"),
    limits=("GitHub publishes no rate limits for Copilot (a limit is temporary: wait and try again); the limit that "
            "counts is the plan's monthly allowance of GitHub AI Credits: Pro 1,500, Pro+ 7,000, Max 20,000 a month, "
            "Business 1,900 and Enterprise 3,900 a user (pooled), Free and Student an allowance not published; it "
            "renews on the 1st at 00:00 UTC"),
    costs=("each answer in GitHub AI Credits (1 credit = $0.01) at its model's rate per million tokens (GPT-6 Luna and "
           "Claude Haiku 5.5 $0.10 in and $0.50 out, up to GPT-6 Astra and Claude Fable 5.1 $10 and $50), from the "
           "plan's allowance, then from a budget for additional usage where one is set; Pro $10, Pro+ $39 and Max "
           "$100 a month; Copilot access is metered from the first use"),
    links=(
        Link("Copilot SDK", SDK_DOCS, "docs"),
        Link("Python SDK reference", README, "reference"),
        Link("Source repository", REPO, "source"),
        Link("Changelog", REPO + "/blob/main/CHANGELOG.md", "changelog"),
        Link("Releases", REPO + "/releases", "changelog"),
        Link("The SDK generally available (2026-06-02)",
             "https://github.blog/changelog/2026-06-02-copilot-sdk-is-now-generally-available/", "changelog"),
        Link(f"{SDK_PACKAGE} on PyPI", "https://pypi.org/project/github-copilot-sdk/", "sdk"),
        Link("Authentication", SDK_DOCS + "/auth/authenticate", "auth"),
        Link("Managing your personal access tokens",
             DOCS + "authentication/keeping-your-account-and-data-secure/managing-your-personal-access-tokens", "auth"),
        Link("Usage and billing (the SDK)", SDK_DOCS + "/features/usage-and-billing", "guide"),
        Link("Models and pricing", PRICING, "pricing"),
        Link("Plans", PLANS_PAGE, "pricing"),
        Link("Usage limits", DOCS + "copilot/concepts/billing-and-usage/individuals/usage-limits", "limits"),
        Link("Supported models", MODELS_PAGE, "reference"),
        Link("GitHub status", "https://www.githubstatus.com/", "status"),
        Link("New fine-grained personal access token", "https://github.com/settings/personal-access-tokens/new",
             "console"),
        Link("GitHub Terms for Additional Products and Features",
             DOCS + "site-policy/github-terms/github-terms-for-additional-products-and-features", "terms"),
    ),
    areas=(
        Area(CLIENT, "CopilotClient: the runtime started (bundled, a local CLI, a server at a URI, or in-process), "
                     "stopped, its sign-in status", SDK_DOCS + "/setup/bundled-cli",
             covered=("started for each call and stopped after it, in the empty mode, its home the plugin's folder, its "
                      "environment without the machine's other credentials; its sign-in checked by Connect")),
        Area("Authentication", "a GitHub token, the signed-in user, an OAuth app, server-to-server tokens, or your own "
                               "model keys", SDK_DOCS + "/auth/authenticate",
             covered="the token given explicitly (github_token), the machine's logins left out"),
        Area(SESSIONS, "sessions created, resumed, listed and deleted; a prompt sent, its answer waited for, aborted",
             README, covered=("one session an answer: the model, the system message replaced by the argument's, "
                              "send_and_wait with a timeout, disconnected after")),
        Area(EVENTS, "a session's events: messages and their deltas, each model call's usage, errors, compaction",
             SDK_DOCS + "/features/streaming-events",
             covered="every event kept: assistant.usage for the tokens and Copilot's cost, session.error for a refusal; "
                     "no streaming"),
        Area(MODELS, "the models the account reaches: their policy, prices (AI credits per batch of tokens) and "
                     "reasoning levels", MODELS_PAGE,
             covered="Connect: the models listed compared with the table, their prices with the table's"),
        Area(QUOTA, "the account's allowances: entitlement, used, remaining, reset date",
             SDK_DOCS + "/features/usage-and-billing", covered="Connect: the allowance left"),
        Area("Tools and permissions", "custom tools, the built-in ones overridden or deferred, and a handler deciding "
                                      "each permission request", SDK_DOCS + "/features/changing-tools",
             covered="no tool at all (available_tools=[]) and every permission request refused"),
        Area("System message and context", "the agent's system message customized or replaced; long sessions "
                                           "compacted (infinite sessions)", SDK_DOCS + "/features/context-management",
             covered="the system message replaced; compaction off"),
        Area("Copilot's models and billing", "the models Copilot serves on each plan, billed in AI credits at each "
                                             "model's rate, from the plan's allowance", PRICING,
             covered="the plugin's tables (plans, models, prices) and the weekly page check"),
        Area("Copilot's API service", "where the runtime's requests go: Copilot's API service at *.githubcopilot.com "
                                      "(by plan) and api.github.com for the account",
             DOCS + "copilot/reference/copilot-allowlist-reference", covered="each answer's model calls, by the runtime"),
        Area("Hooks", "session hooks: before and after a tool, a prompt submitted, the session's lifecycle, errors",
             SDK_DOCS + "/hooks/hooks-overview"),
        Area("MCP servers", "MCP servers' tools offered to the agent", SDK_DOCS + "/features/mcp"),
        Area("Custom agents and skills", "agents of your own and skills the agent loads",
             SDK_DOCS + "/features/custom-agents"),
        Area("Bring your own key", "the agent on your own model provider's key (OpenAI, Azure, Anthropic ...)",
             SDK_DOCS + "/auth/byok"),
        Area("Session persistence and remote sessions", "sessions kept and resumed, cloud and remote sessions",
             SDK_DOCS + "/features/session-persistence"),
        Area("Image input and structured output", "images attached to a prompt; answers to a schema",
             SDK_DOCS + "/features/image-input"),
        Area("Observability", "the runtime's OpenTelemetry traces", SDK_DOCS + "/observability/opentelemetry"),
        Area("Copilot REST API", "GitHub's REST endpoints for Copilot seats, usage metrics, the coding agent and content "
                                 "exclusion (an organization's)", DOCS + "rest/copilot"),
    ),
    calls=(
        Call('CopilotClient(github_token, use_logged_in_user=False, mode="empty", base_directory, working_directory, '
             'env)', "a client for one call", CLIENT,
             used="the token explicit, the empty mode, the plugin's folder, a cleaned environment", docs=README),
        Call("CopilotClient.start()", "start the runtime", CLIENT, used="the runtime started for a call", docs=README),
        Call("CopilotClient.stop()", "stop the runtime gracefully", CLIENT, used="stopped after the call", docs=README),
        Call("CopilotClient.force_stop()", "stop the runtime without its cleanup", CLIENT,
             used="a runtime that will not stop gracefully", docs=README),
        Call("CopilotClient.get_auth_status()", "whether the runtime is signed in, and as whom", CLIENT,
             used="Connect: the token tried, the account named checked", docs=README),
        Call("CopilotClient.list_models()", "the models the account reaches", MODELS,
             used="Connect: the models and their prices compared with the table", docs=README),
        Call("client.rpc.account.get_quota(AccountGetQuotaRequest())", "the account's allowances", QUOTA,
             used="Connect: the allowance left", docs=SDK_DOCS + "/features/usage-and-billing"),
        Call('CopilotClient.create_session(model, system_message={"mode": "replace"}, available_tools=[], '
             'on_permission_request, streaming=False, infinite_sessions={"enabled": False}, on_event, '
             'reasoning_effort)', "a session for a prompt", SESSIONS, used="one session for each answer", docs=README),
        Call("CopilotSession.send_and_wait(prompt, timeout)", "send a prompt and wait for its answer", SESSIONS,
             used="each evaluation's answer, and Connect's probe", docs=README, costs=True),
        Call("CopilotSession.disconnect()", "end a session", SESSIONS, used="the session ended after its answer",
             docs=README),
        Call("CopilotSession.send(prompt)", "send a prompt, its answer as events", SESSIONS, docs=README, costs=True),
        Call("CopilotClient.resume_session(session_id)", "resume a kept session", SESSIONS,
             docs=SDK_DOCS + "/features/session-persistence"),
        Call("CopilotSession.set_tools(tools)", "change a live session's tools", "Tools and permissions",
             docs=SDK_DOCS + "/features/changing-tools"),
        Call("CopilotClient.ping()", "check the runtime answers", CLIENT, docs=README),
    ),
    verified=VERIFIED,
)

RUNTIME = "Transports"

COPILOT_RUNTIME = Api(
    name="Copilot runtime (the SDK's CLI server)",
    maker="GitHub",
    about=("Copilot's agent runtime, the Copilot CLI's, which the SDK starts as a child process and speaks JSON-RPC to "
           "over its stdio (or over TCP, to a server already running, or in-process): it signs in with the token, "
           "calls Copilot's models and bills them, and keeps its state in its home (COPILOT_HOME). The Python SDK pins "
           "a runtime version, fetched once with python -m copilot download-runtime (else on first use) and cached "
           "for the user."),
    kind="command",
    base="copilot-runtime (fetched by python -m copilot download-runtime, cached under "
         "%LOCALAPPDATA%\\github-copilot-sdk\\cli\\<version>)",
    version=f"the runtime {SDK_PACKAGE} {SDK_WRITTEN_FOR} pins (its protocol: sdk-protocol-version.json)",
    auth=("the token the SDK gives it; the plugin leaves the machine's stored logins, GH_TOKEN, GITHUB_TOKEN, COPILOT_* "
          "and every other credential out of its environment"),
    limits="",
    costs="its model calls are billed to the account's plan (the SDK's card)",
    links=(
        Link("Default setup (bundled CLI)", SDK_DOCS + "/setup/bundled-cli", "docs"),
        Link("Local CLI setup", SDK_DOCS + "/setup/local-cli", "guide"),
        Link("In-process runtime", SDK_DOCS + "/setup/in-process-runtime", "guide"),
        Link("Multi-tenancy and the empty mode", SDK_DOCS + "/setup/multi-tenancy", "guide"),
        Link("Copilot CLI programmatic reference", CLI_REF + "cli-programmatic-reference", "reference"),
        Link("Copilot CLI command reference", CLI_REF + "cli-command-reference", "reference"),
        Link("Copilot CLI configuration directory", CLI_REF + "cli-config-dir-reference", "reference"),
        Link("Authenticating Copilot CLI", DOCS + "copilot/how-tos/copilot-cli/set-up-copilot-cli/authenticate-copilot-cli",
             "auth"),
        Link("Copilot allowlist reference", DOCS + "copilot/reference/copilot-allowlist-reference", "reference"),
        Link("SDK protocol version", REPO + "/blob/main/sdk-protocol-version.json", "spec"),
        Link("Compatibility", SDK_DOCS + "/troubleshooting/compatibility", "guide"),
        Link("Debugging", SDK_DOCS + "/troubleshooting/debugging", "guide"),
    ),
    areas=(
        Area(RUNTIME, "stdio (a child process), TCP, a server already running at a URI, or in-process (FFI)",
             SDK_DOCS + "/setup/choosing-a-setup-path",
             covered="stdio: a child process for each call, JSON-RPC over its standard streams"),
        Area("The empty mode", "no environment context, telemetry, custom instructions, host files or git, session "
                               "store, memory or skills", SDK_DOCS + "/setup/multi-tenancy",
             covered="every runtime the plugin starts"),
        Area("Its home", "where it keeps its state and configuration (COPILOT_HOME, ~/.copilot by default)",
             CLI_REF + "cli-config-dir-reference", covered="assistants/copilot/ in the data folder"),
        Area("Its download", "the pinned runtime fetched and checked against the release's SHA256SUMS",
             SDK_DOCS + "/setup/bundled-cli", covered="asked of you once at install: the plugin never downloads it"),
        Area("Its sign-in", "a token, the stored login of the CLI, or the environment's GH_TOKEN or GITHUB_TOKEN",
             DOCS + "copilot/how-tos/copilot-cli/set-up-copilot-cli/authenticate-copilot-cli",
             covered="the plugin's token only"),
        Area("Its network", "Copilot's API service at *.githubcopilot.com (by plan), api.github.com, telemetry hosts",
             DOCS + "copilot/reference/copilot-allowlist-reference", covered="each answer's model calls"),
        Area("The CLI's own commands", "the Copilot CLI run by a person or a script: its commands and options",
             CLI_REF + "cli-command-reference"),
    ),
    calls=(
        Call("copilot-runtime (a child process, JSON-RPC over stdio)", "the runtime the SDK starts", RUNTIME,
             used="started by CopilotClient.start() for each call, stopped after it", docs=SDK_DOCS + "/setup/bundled-cli"),
        Call("python -m copilot download-runtime", "fetch the pinned runtime once", "Its download",
             docs=SDK_DOCS + "/setup/bundled-cli"),
        Call("python -m copilot download-runtime --in-process", "fetch the in-process runtime's library too",
             "Its download", docs=README),
        Call("RuntimeConnection.for_tcp(port)", "a runtime on a TCP port", RUNTIME, docs=README),
        Call("RuntimeConnection.for_uri(url)", "a runtime already running", RUNTIME, docs=SDK_DOCS + "/setup/local-cli"),
    ),
    verified=VERIFIED,
)

APIS = (COPILOT_SDK, COPILOT_RUNTIME)
