"""The Copilot plugin on fake answers: it loads as an assistant plugin, its tables hold together, the free
plan sends through auto, a session is asked the model, the argument's own system prompt, the user's
text and the effort (never the token, nothing about the account), an answer's usage, model and cost are
read, Copilot's refusals are said in words with the token scrubbed, Connect checks the token, the models
and their prices and shows the allowance, the machine's caps hold, and the SDK's runtime is driven
locked down (a fake SDK module under the real SdkRuntime: nothing imported, no process started)."""
from __future__ import annotations

import re
from datetime import datetime, timezone
from pathlib import Path
from types import SimpleNamespace

import pytest

from liminal_libs.assistants import Answer, Offline, Question, Usage, evaluate
from liminal_libs.config import ConfigError
from liminal_libs.errors import BudgetExhausted, NotEntitled, RateLimited, SourceError, Unauthorized

import plugin_platform_copilot as copilot
from plugin_platform_copilot import ASSISTANT, INDIVIDUAL, MODELS, ORGANIZATION, PLANS, SOURCES, CopilotPlugin
from plugin_platform_copilot.runtime import ANSWER_SECONDS, Ask, CopilotError, SdkRuntime, child_env, classify

from conftest import FakeQuotaRequest, FakeReject, FakeRuntime, answer, event, listed

NOW = datetime(2026, 11, 8, 15, 0, tzinfo=timezone.utc)
KEY, EMAIL, LOGIN = "github_pat_11TESTONLY0000000000_scratchtokenfortests", "me@example.com", "octocat"


def test_it_loads_as_an_assistant_plugin(installed):
    found = installed(ASSISTANT)
    assert list(found) == ["copilot"] and isinstance(found["copilot"], CopilotPlugin)
    p = found["copilot"]
    assert p.KIND == "assistant" and p.SYSTEM == "platform" and p.api == "2.0" and p.vendor == "GitHub"
    assert p.origin == "package: plugin_platform_copilot"
    import liminal_libs

    icons = (Path(liminal_libs.__file__).parent / "ui" / "static" / "icons.js").read_text(encoding="utf-8")
    assert p.ICON == "copilot" and re.search(r"^\s*copilot:", icons, flags=re.MULTILINE)  # its maker's logo, the library's
    key, account = p.keys
    assert (key.name, account.name) == ("COPILOT_API_KEY", "COPILOT_ACCOUNT") and key.aliases == ("COPILOT_GITHUB_TOKEN",)
    assert key.secret and not account.secret and "Copilot Requests" in key.hint and "ghp_" in key.hint
    assert p.plan_vars == ("COPILOT_PLAN", "COPILOT_MODEL", "COPILOT_REQUESTS_PER_DAY", "COPILOT_TOKENS_PER_DAY")
    assert p.options == ("COPILOT_MAX_OUTPUT_TOKENS", "COPILOT_EFFORT") and p.has_scan and p.has_settings
    assert p.plan_choices["COPILOT_PLAN"][0] == "free" and p.plan_choices["COPILOT_MODEL"][0] == "auto"
    assert p.plan_choices["COPILOT_EFFORT"] == ("", "low", "medium", "high", "xhigh", "max")
    assert [d.where for d in p.databases] == ["assistants/copilot/"] and p.refusal() is None
    from liminal_libs.sources import registry

    assert registry.errors() == []
    assert set(registry.variables()) >= {"COPILOT_API_KEY", "COPILOT_GITHUB_TOKEN", "COPILOT_ACCOUNT", "COPILOT_PLAN",
                                          "COPILOT_MODEL", "COPILOT_EFFORT"}


def test_the_tables_hold_together():
    assert [p.name for p in PLANS] == ["free", "student", "pro", "pro-plus", "max", "business", "enterprise", "access"]
    assert all(p.api_access and not (p.rpm or p.tpm or p.rpd) for p in PLANS)  # each reaches the SDK; no limits published
    free, student, pro, plus = (ASSISTANT.plan_of(n) for n in ("free", "student", "pro", "pro-plus"))
    assert ASSISTANT.free_plan is free and ASSISTANT.reach(free) == ASSISTANT.reach(student) == ("auto",)
    ids = [m.id for m in MODELS]
    assert ids[0] == ASSISTANT.default_model == "auto" and len(set(ids)) == len(ids) == 26  # auto and 25 text models
    assert all(re.fullmatch(r"[a-z0-9][a-z0-9.-]*", i) for i in ids)  # Copilot's own ids: claude-haiku-5.5, gpt-6.1-sol
    assert set(ASSISTANT.reach(plus)) == set(ids) and ASSISTANT.reach(ASSISTANT.plan_of("access")) == ASSISTANT.reach(plus)
    assert "claude-opus-5.5" not in ASSISTANT.reach(pro) and {"auto", "gpt-6-luna", "claude-sonnet-5"} <= set(ASSISTANT.reach(pro))
    paid = MODELS[1:]
    assert all(0 < m.cached_usd < m.input_usd < m.output_usd for m in paid)
    assert [m.input_usd for m in paid] == sorted(m.input_usd for m in paid)  # the cheapest first, after auto
    assert all(m.plans and all(ASSISTANT.plan_of(n) for n in m.plans) for m in paid)
    assert ASSISTANT.cost("gpt-6-luna", Usage(1_000_000, 1_000_000, 0, 0)) == 0.6
    assert ASSISTANT.cost("claude-opus-5.5", Usage(1_000_000, 0, 1_000_000, 0)) == 0.2  # every input token a cached one
    assert ASSISTANT.cost("auto", Usage(10, 10)) is None  # billed at the rate of the model it chose
    assert INDIVIDUAL["pro"] == (10, 1_000, 500, 1_500) and "1,500 AI credits" in pro.price and "7,000" in plus.price
    assert ORGANIZATION == {"business": (19, 1_900), "enterprise": (39, 3_900)}
    assert copilot.VERIFIED == "2026-11-08" and ASSISTANT.verified == copilot.VERIFIED
    assert all(s.url.startswith(("https://docs.github.com/", "https://github.blog/")) and s.sentinel and s.markers
               for s in SOURCES)
    assert set(SOURCES[0].markers) == {m.title for m in paid}  # every model's name must stay on the pricing page


def test_the_free_plan_sends_through_auto_and_the_request_is_the_arguments_own(installed, settings_for):
    installed(ASSISTANT)
    settings = settings_for(COPILOT_GITHUB_TOKEN=KEY, COPILOT_ACCOUNT=EMAIL)
    own = settings.plugin("copilot")
    assert own.has_key and own.plan == "free" and own.model == "auto"
    assert ASSISTANT.keys_set(settings) and ASSISTANT.served(settings) and ASSISTANT.free_note(settings) == ""
    rt = FakeRuntime(answers=[answer("The exchange is closed.\nVerdict: no")])
    q = Question("Is the market open?", answer=Answer("verdict", scale=("yes", "no")))
    ev = evaluate(q, settings, assistant="copilot", session=rt, now=lambda: NOW)
    (ask,) = rt.asks
    assert isinstance(ask, Ask) and ask.model == "auto" and ask.effort == "" and ask.timeout == ANSWER_SECONDS
    assert ask.system.startswith("You are an analyst's assistant") and "Verdict:" in ask.system
    assert ask.prompt == "Question: Is the market open?"
    assert KEY not in repr(ask) and EMAIL not in repr(ask)  # never the token, nothing about the account
    assert rt.opened == rt.closed == 1 and [c[0] for c in rt.calls] == ["ask"]  # started for the answer, stopped after
    assert ev.assistant == "copilot" and ev.provider == "GitHub" and ev.verdict == "no" and ev.ok and ev.stop == "end_turn"
    assert ev.model == "gpt-6-luna"  # the model auto chose answered, and is what the evaluation records
    assert ev.usage == Usage(120, 30, 20, 8) and ev.request_id == "svc-req-1"
    assert ev.cost_usd == pytest.approx(ASSISTANT.model_of("gpt-6-luna").cost(Usage(120, 30, 20, 8)))  # that model's price
    with pytest.raises(ConfigError, match="not on the Copilot Free plan"):
        ASSISTANT.settings({"COPILOT_API_KEY": KEY, "COPILOT_MODEL": "claude-sonnet-5"})
    rt = FakeRuntime()
    a = ASSISTANT.build(settings, session=rt, now=lambda: NOW)
    with pytest.raises(NotEntitled, match="Copilot Free plan does not reach claude-sonnet-5"):
        a.evaluate(q, "claude-sonnet-5")
    assert rt.opened == 0  # refused before the runtime was started


def test_a_paid_plans_request_carries_the_model_and_the_effort(installed, settings_for):
    installed(ASSISTANT)
    settings = settings_for(COPILOT_API_KEY=KEY, COPILOT_PLAN="pro", COPILOT_MODEL="claude-haiku-5.5", COPILOT_EFFORT="low",
                            COPILOT_MAX_OUTPUT_TOKENS="512")
    own = settings.plugin("copilot")
    assert (own.plan, own.model, own.effort, own.caps.max_output_tokens) == ("pro", "claude-haiku-5.5", "low", 512)
    rt = FakeRuntime(answers=[answer('{"verdict": "bearish", "score": 3}', model="claude-haiku-5.5", wrote=10,
                                     sub={"input": 40, "output": 5, "cache_read": 0, "reasoning": 0})])
    fields = Question("Score it", answer=Answer("fields", fields=("verdict", "score")))
    ev = evaluate(fields, settings, assistant="copilot", session=rt, now=lambda: NOW)
    (ask,) = rt.asks
    assert (ask.model, ask.effort) == ("claude-haiku-5.5", "low") and "JSON object" in ask.system
    assert ev.fields == {"verdict": "bearish", "score": 3} and ev.verdict == "bearish" and ev.model == "claude-haiku-5.5"
    assert ev.usage == Usage(160, 35, 20, 8, 2)  # a sub-agent's call is billed too; the cache writes are within the input
    q = Question("Is it open?", answer=Answer("verdict", scale=("yes", "no")))
    cut = evaluate(q, settings, assistant="copilot", session=FakeRuntime(answers=[answer("Verdict: yes", finish="length")]),
                   now=lambda: NOW)
    assert cut.stop == "length" and cut.verdict == "yes"
    declined = evaluate(q, settings, assistant="copilot", now=lambda: NOW,
                        session=FakeRuntime(answers=[answer("", finish="content_filter", filtered=True)]))
    assert declined.stop == "refusal" and declined.verdict is None and not declined.ok
    a = ASSISTANT.build(settings, session=FakeRuntime(), now=lambda: NOW)
    apart = a.parse({"usage": [{"input": 50, "cache_read": 100, "cache_write": 10, "output": 5}]})
    assert apart.usage == Usage(160, 5, 100, 0)  # an input count without its cache reads and writes is added to


def test_no_key_and_a_classic_token_send_nothing(installed, settings_for):
    installed(ASSISTANT)
    rt = FakeRuntime()
    with pytest.raises(Unauthorized, match="no key"):
        evaluate(Question("x"), settings_for(COPILOT_PLAN="pro"), assistant="copilot", session=rt)
    classic = settings_for(COPILOT_API_KEY="ghp_" + "0" * 36)
    assert ASSISTANT.keys_set(classic)
    with pytest.raises(Unauthorized, match="classic personal access token"):
        evaluate(Question("x"), classic, assistant="copilot", session=rt)
    ((what, ok, detail),) = ASSISTANT.run_scan(ASSISTANT.build(classic, session=rt, now=lambda: NOW)).results
    assert (what, ok) == ("the key", False) and detail.startswith("not sent: copilot: a classic personal access token")
    with pytest.raises(Unauthorized, match="classic"):
        ASSISTANT.build(classic, session=rt, now=lambda: NOW).models()
    with pytest.raises(Offline):  # nothing is sent from an offline copy of the app
        evaluate(Question("x"), settings_for(COPILOT_API_KEY=KEY, LIMINAL_OFFLINE="1"), assistant="copilot", session=rt)
    assert rt.opened == 0 and rt.calls == []


def test_copilots_refusals_are_said_in_words_with_the_token_scrubbed(installed, settings_for):
    installed(ASSISTANT)
    settings = settings_for(COPILOT_API_KEY=KEY, COPILOT_ACCOUNT=LOGIN, COPILOT_PLAN="pro")

    def run(refusal, **runtime):
        rt = FakeRuntime(answers=[refusal], **runtime)
        a = ASSISTANT.build(settings, session=rt, now=lambda: NOW)
        with pytest.raises(SourceError) as caught:
            a.evaluate(Question("x"))
        return type(caught.value), caught.value.message, rt

    kind, msg, rt = run(CopilotError(f"Authentication failed: the token {KEY} of {LOGIN} lacks a permission", 401,
                                     "authentication"))
    assert kind is Unauthorized and KEY not in msg and LOGIN not in msg and "the token … of … lacks" in msg
    assert msg.startswith("the token was refused") and "Copilot Requests" in msg and rt.opened == rt.closed == 1
    kind, msg, _ = run(CopilotError("Access denied by policy settings", 403, "authorization"))
    assert kind is NotEntitled and msg.startswith("not allowed: Access denied by policy settings") and "Copilot CLI" in msg
    kind, msg, _ = run(CopilotError("You have used all of your AI credits", 429, "quota"))
    assert kind is NotEntitled and msg.startswith("no AI credits left for it") and "1st at 00:00 UTC" in msg
    kind, msg, _ = run(CopilotError("Too many requests", 429, "rate_limit"))
    assert kind is RateLimited and msg.startswith("rate limited: Too many requests") and "wait" in msg
    kind, msg, _ = run(CopilotError("Model gpt-9 is not available", 404))
    assert kind is NotEntitled and msg.startswith("no such model") and "Connect's list" in msg
    kind, msg, _ = run(CopilotError("the upstream failed", 502))
    assert kind is SourceError and msg == "the upstream failed"
    kind, msg, _ = run(CopilotError("no answer from the Copilot runtime in 210 s", kind="timeout"))
    assert kind is SourceError and msg == "no answer from the Copilot runtime in 210 s"
    kind, msg, rt = run(None, open_error=CopilotError("the Copilot SDK is not installed here: install it", kind="setup"))
    assert kind is SourceError and "not installed" in msg and rt.calls == []
    assert classify("HTTP 401: Bad credentials") == (401, "authentication") and classify("all is well") == (0, "")
    assert classify("Rate limit of 10 per 60s exceeded") == (429, "rate_limit")


def test_connect_checks_the_token_the_models_their_prices_and_the_allowance(installed, settings_for):
    installed(ASSISTANT)
    settings = settings_for(COPILOT_API_KEY=KEY, COPILOT_ACCOUNT=LOGIN, COPILOT_PLAN="pro", COPILOT_MODEL="gpt-6-luna")
    models = [listed("gpt-6-luna", 0.10, 0.50), listed("claude-haiku-5.5", 0.10, 0.50, batch=1_000),
              listed("claude-sonnet-5", 2.50, 12.00), listed("gpt-7-preview", 1.00, 2.00), listed("grok-4.7")]
    quota = {"premium_interactions": {"entitlement": 1500, "used": 12, "remaining": 99.2, "reset": "2026-12-01T00:00:00Z",
                                      "unlimited": False},
             "chat": {"entitlement": -1, "used": 0, "remaining": 100.0, "reset": "", "unlimited": True}}
    rt = FakeRuntime(models=models, quota=quota, answers=[answer("OK", in_=12, out=1, read=0, thought=0, nano=170_000.0)])
    scanned = ASSISTANT.run_scan(ASSISTANT.build(settings, session=rt, now=lambda: NOW))
    rows = {w: (ok, d) for w, ok, d in scanned.results}
    assert rows["the Copilot SDK"] == (True, "github-copilot-sdk 1.0.29")
    assert rows["the key"] == (True, "accepted (token): 5 models listed by the server")
    assert rows["the account"] == (True, "the token is the GitHub account COPILOT_ACCOUNT names")
    assert rows["the model gpt-6-luna"] == (True, "listed")
    ok, gone = rows["the table's models"]
    assert not ok and "gpt-5.3-codex" in gone and "claude-opus-5.5" not in gone  # only the ones Pro reaches
    assert rows["models not in the table"] == (True, "gpt-7-preview")
    assert rows["the table's prices"] == (False, "claude-sonnet-5: the server's $2.50 in and $12.00 out a million tokens, "
                                                 "the table's $2.00 and $10.00 (the table is stale: update the plugin)")
    assert rows["its allowance"] == (True, "chat: unlimited; premium_interactions: 12 of 1,500 used (99.2% left), "
                                           "resets 2026-12-01")
    ok, said = rows["an answer"]
    assert ok and said.startswith("gpt-6-luna answered in ") and said.endswith(
        ": 13 tokens, 0.000170 AI credits by Copilot's count (0.000170 by the table's prices)")
    assert scanned.plan == {}  # Copilot sends no limits the plans differ by: the plan stays the one chosen
    assert scanned.limits["perMinute"] is None and scanned.limits["seen"]["chat"] == "chat: unlimited"
    assert [c[0] for c in rt.calls] == ["auth", "models", "quota", "ask"] and rt.opened == rt.closed == 1  # one runtime
    (probe,) = rt.asks
    assert (probe.model, probe.system, probe.prompt) == ("gpt-6-luna", "Reply with the single word OK.", "Are you there?")
    light = FakeRuntime(models=models)
    found = {w for w, _, _ in ASSISTANT.build(settings, session=light, now=lambda: NOW).connect(light=True).results}
    assert "an answer" not in found and light.asks == []
    listing = ASSISTANT.build(settings, session=FakeRuntime(models=models[:1]), now=lambda: NOW).models()
    assert [(m["id"], m["title"], m["policy"]) for m in listing] == [("gpt-6-luna", "gpt-6-luna", "enabled")]


def test_connect_says_what_it_cannot_reach(installed, settings_for):
    installed(ASSISTANT)

    def scan(rt, **env):
        settings = settings_for(COPILOT_API_KEY=KEY, **env)
        return ASSISTANT.run_scan(ASSISTANT.build(settings, session=rt, now=lambda: NOW)).results

    missing = CopilotError("the Copilot SDK is not installed here: install it", kind="setup")
    assert scan(FakeRuntime(open_error=missing)) == (("the Copilot SDK", False, "the Copilot SDK is not installed here: install it"),)
    rt = FakeRuntime(auth={"authenticated": False, "message": f"Authentication failed for {KEY}"})
    sdk, (what, ok, detail) = scan(rt)
    assert sdk[0] == "the Copilot SDK" and (what, ok) == ("the key", False) and KEY not in detail
    assert detail.startswith("refused: Authentication failed for …") and "Copilot Requests" in detail
    assert [c[0] for c in rt.calls] == ["auth"]  # nothing more is asked of a runtime not signed in
    what, ok, detail = scan(FakeRuntime(models=CopilotError("Access denied by policy settings", 403, "authorization")))[-1]
    assert (what, ok) == ("the key", False) and detail.startswith("refused: not allowed: Access denied by policy settings")
    rows = {w: (ok, d) for w, ok, d in scan(FakeRuntime(models=[listed("gpt-6-luna", 0.10, 0.50)], answers=[answer("OK")]),
                                            COPILOT_ACCOUNT="someone-else")}
    assert rows["the account"] == (False, "the token belongs to another GitHub account than COPILOT_ACCOUNT names: check "
                                          "the token or the account")
    assert rows["the model auto"] == (True, "Copilot chooses among the models your plan and its policies allow")
    assert "the table's models" not in rows  # the free plan reaches auto alone: nothing of the table to miss
    assert rows["the table's prices"] == (True, "the server's agree with the table's (1 model)")
    rows = {w: (ok, d) for w, ok, d in scan(FakeRuntime(models=[listed("claude-opus-5.5", 4.0, 20.0, policy="disabled")],
                                                        answers=[answer("OK", model="claude-opus-5.5")]),
                                            COPILOT_PLAN="pro-plus", COPILOT_MODEL="claude-opus-5.5", COPILOT_ACCOUNT=EMAIL)}
    assert rows["the model claude-opus-5.5"] == (False, "listed, but not enabled for this account (its policy: disabled): "
                                                        "enable it in your Copilot settings on GitHub")
    assert "the account" not in rows  # an email cannot be told from the token's login
    rows = scan(FakeRuntime(models=[], answers=[answer("OK")]), COPILOT_ACCOUNT=LOGIN)
    assert rows[2][0] == "the account" and rows[3] == ("the model auto", False, "no model is listed for this account: has "
                                                                                 "it a Copilot plan?")


def test_the_machines_daily_request_cap_holds(installed, settings_for):
    installed(ASSISTANT)
    settings = settings_for(COPILOT_API_KEY=KEY, COPILOT_REQUESTS_PER_DAY="1")
    rt = FakeRuntime(answers=[answer("Verdict: yes"), answer("Verdict: yes")])
    a = ASSISTANT.build(settings, session=rt, now=lambda: NOW)
    assert a.evaluate(Question("x")).ok
    with pytest.raises(BudgetExhausted, match="daily request cap"):
        a.evaluate(Question("x"))
    assert len(rt.asks) == 1 and rt.opened == 1  # the second was not sent: the runtime was not even started
    assert a.tokens.today(NOW) == 150  # the answer's tokens counted on the machine's ledger


def test_the_runtime_is_the_sdks_by_default_beside_the_data(installed, settings_for, tmp_path):
    installed(ASSISTANT)
    a = ASSISTANT.build(settings_for(COPILOT_API_KEY=KEY), now=lambda: NOW)
    assert isinstance(a.runtime, SdkRuntime) and a.runtime.home == tmp_path / "assistants" / "copilot"
    assert not a.runtime.home.exists() and KEY not in repr(a.runtime)  # nothing written until a call needs the runtime
    assert a.headers(KEY) == {} and a.client._headers == {}  # the token is the SDK's to send, never a header here


def test_the_sdk_runtime_is_driven_locked_down(fake_sdk, tmp_path):
    usage = event("assistant.usage", model="gpt-6-luna", input_tokens=120, output_tokens=30, cache_read_tokens=20,
                  cache_write_tokens=0, reasoning_tokens=8, finish_reason="stop", content_filter_triggered=False,
                  service_request_id="svc-1", copilot_usage=SimpleNamespace(total_nano_aiu=4_500_000.0))
    final = event("assistant.message", content="Closed.\nVerdict: no", message_id="m-1", model="gpt-6-luna")
    model = SimpleNamespace(id="gpt-6-luna", name="GPT-6 Luna", policy=SimpleNamespace(state="enabled", terms=""),
                            billing=SimpleNamespace(multiplier=0.33, token_prices=SimpleNamespace(
                                input_price=10.0, output_price=50.0, cache_price=1.0, batch_size=1_000_000)),
                            capabilities=SimpleNamespace(limits=SimpleNamespace(max_context_window_tokens=1_000_000)),
                            supported_reasoning_efforts=["low", "medium"])
    auth = SimpleNamespace(isAuthenticated=True, authType="token", host="https://github.com", login=LOGIN, statusMessage="")
    quota = SimpleNamespace(quota_snapshots={"premium_interactions": SimpleNamespace(
        entitlement_requests=1500, used_requests=12, remaining_percentage=99.2, reset_date="2026-12-01",
        is_unlimited_entitlement=False)})
    sdk, rpc, made = fake_sdk(auth=auth, models=[model], quota=quota, events=[usage], final=final)
    environ = {"PATH": r"C:\Windows", "LIMINAL_DB": "x.db", "CLAUDE_API_KEY": "sk-ant-x", "CODEX_ACCOUNT": EMAIL,
               "GH_TOKEN": "gho_x", "GITHUB_TOKEN": "ghs_x", "COPILOT_GITHUB_TOKEN": "github_pat_other",
               "COPILOT_PROVIDER_BASE_URL": "http://elsewhere", "COPILOT_MODEL": "gpt-6-astra", "LIMINAL_SMTP_PASSWORD": "pw",
               "AWS_SECRET_ACCESS_KEY": "s"}
    home = tmp_path / "home"
    rt = SdkRuntime(KEY, home, sdk=sdk, rpc=rpc, environ=environ)
    assert KEY not in repr(rt) and made == [] and not home.exists()  # nothing made, started or written before open
    with rt.open() as conn:
        assert conn.version == "1.0.29"
        signed, models, allowances = conn.auth(), conn.models(), conn.quota()
        got = conn.ask(Ask("auto", "You are terse.", "Is it open?", "low", 30.0))
    (client,) = made
    assert client.options == {"github_token": KEY, "use_logged_in_user": False, "mode": "empty", "base_directory": str(home),
                              "working_directory": str(home), "env": {"PATH": r"C:\Windows", "LIMINAL_DB": "x.db"}}
    assert client.started and client.stopped and home.is_dir()
    (session,) = client.sessions
    options = dict(session.options)
    deny, on_event = options.pop("on_permission_request"), options.pop("on_event")
    assert options == {"model": "auto", "system_message": {"mode": "replace", "content": "You are terse."},
                       "available_tools": [], "streaming": False, "infinite_sessions": {"enabled": False},
                       "reasoning_effort": "low"}
    refused = deny(SimpleNamespace(kind="shell", full_command_text="rm -rf /"), None)
    assert isinstance(refused, FakeReject) and "no tool may run" in refused.feedback  # every permission request refused
    assert callable(on_event) and session.sent == [("Is it open?", 30.0)] and session.disconnected
    assert signed == {"authenticated": True, "type": "token", "host": "https://github.com", "login": LOGIN, "message": ""}
    assert models == [{"id": "gpt-6-luna", "name": "GPT-6 Luna", "policy": "enabled", "multiplier": 0.33,
                       "prices": {"input": 10.0, "output": 50.0, "cache": 1.0, "batch": 1_000_000}, "context": 1_000_000,
                       "efforts": ["low", "medium"]}]
    assert allowances == {"premium_interactions": {"entitlement": 1500, "used": 12, "remaining": 99.2, "reset": "2026-12-01",
                                                   "unlimited": False}}
    assert isinstance(client.quota_request, FakeQuotaRequest)
    assert got == {"text": "Closed.\nVerdict: no", "message_id": "m-1", "request_id": "", "model": "gpt-6-luna",
                   "asked": "auto", "usage": [{"model": "gpt-6-luna", "input": 120, "output": 30, "cache_read": 20,
                                               "cache_write": 0, "reasoning": 8, "finish": "stop", "filtered": False,
                                               "nano_aiu": 4_500_000.0, "request_id": "svc-1", "sub": False}]}


def test_the_sdk_runtimes_refusals_and_what_it_leaves_out(fake_sdk, tmp_path):
    failing = event("session.error", error_type="authentication", message="Authentication failed", status_code=401)
    sdk, rpc, made = fake_sdk(error=failing)
    with pytest.raises(CopilotError) as caught:
        with SdkRuntime(KEY, tmp_path, sdk=sdk, rpc=rpc, environ={}).open() as conn:
            conn.ask(Ask("auto", "s", "p"))
    assert (caught.value.status, caught.value.kind, caught.value.message) == (401, "authentication", "Authentication failed")
    (client,) = made
    assert client.stopped and client.sessions[0].disconnected  # the session ended and the runtime stopped all the same
    sdk, rpc, made = fake_sdk(**{"raise": TimeoutError("Timeout after 30s waiting for session.idle")})
    with pytest.raises(CopilotError) as caught:
        with SdkRuntime(KEY, tmp_path, sdk=sdk, rpc=rpc, environ={}).open() as conn:
            conn.ask(Ask("auto", "s", "p", timeout=30.0))
    assert caught.value.kind == "timeout" and "Timeout after 30s" in caught.value.message
    sdk, rpc, made = fake_sdk(start_error=FileNotFoundError("the runtime's binary"))
    with pytest.raises(CopilotError) as caught:
        with SdkRuntime(KEY, tmp_path, sdk=sdk, rpc=rpc, environ={}).open():
            pass
    assert caught.value.kind == "setup" and "download-runtime" in caught.value.message and made[0].stopped
    sdk, rpc, made = fake_sdk(quota=None)
    with SdkRuntime(KEY, tmp_path, sdk=sdk, rpc=SimpleNamespace(), environ={}).open() as conn:
        assert conn.quota() is None  # no quota request type: nothing read, nothing refused
    with pytest.raises(CopilotError) as caught:
        with SdkRuntime(KEY, tmp_path, module="no_such_copilot_sdk_here", environ={}).open():
            pass
    assert caught.value.kind == "setup" and 'pip install "plugin-platform-copilot[sdk]"' in caught.value.message
    assert child_env({"Path": "x", "github_token": "t", "MY_SERVICE_TOKEN": "t", "HOTKEY": "k", "copilot_home": "h"}) == \
        {"Path": "x", "HOTKEY": "k"}
