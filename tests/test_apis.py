"""What the plugin attaches to (plugin API 2.2, apis.py): the Copilot SDK's card and the runtime's are sound, say how
the token is given, the limits, the prices, the status page and the token page, name exactly the SDK calls the real
runtime makes (run on a recording fake SDK: nothing imported, no process started) among the SDK's others, and every
address on them is GitHub's own. The page check is the weekly one (tests/test_vendor_pages.py, LIMINAL_VENDOR_PAGES=1);
nothing is sent here. The user, 2026-11-11: "each plugin should reflect the the API its attached to, and present links
that provide documentation"."""
from __future__ import annotations

from datetime import date
from types import SimpleNamespace
from urllib.parse import urlsplit

from liminal_libs.sources.apis import problems, urls

import plugin_platform_copilot as copilot
from plugin_platform_copilot import ASSISTANT
from plugin_platform_copilot.apis import APIS, COPILOT_RUNTIME, COPILOT_SDK
from plugin_platform_copilot.runtime import SDK_WRITTEN_FOR, Ask, SdkRuntime

from conftest import FakeQuotaRequest, FakeReject, event

KEY = "github_pat_11TESTONLY0000000000_scratchtokenfortests"


def recording_sdk(calls: list, *, stop_fails: bool = False):
    """The copilot and copilot.rpc modules' places, each SDK call the runtime makes recorded by its name on the card."""

    class Session:
        def __init__(self, options):
            self.options = options

        async def send_and_wait(self, prompt, *, timeout=60.0):
            calls.append("CopilotSession.send_and_wait")
            return event("assistant.message", content="OK", message_id="m-1", model="gpt-6-luna")

        async def disconnect(self):
            calls.append("CopilotSession.disconnect")

    class Client:
        def __init__(self, **options):
            calls.append("CopilotClient")
            self.rpc = SimpleNamespace(account=SimpleNamespace(get_quota=self._quota))

        async def start(self):
            calls.append("CopilotClient.start")

        async def stop(self):
            calls.append("CopilotClient.stop")
            if stop_fails:
                raise RuntimeError("it will not stop")

        async def force_stop(self):
            calls.append("CopilotClient.force_stop")

        async def get_auth_status(self):
            calls.append("CopilotClient.get_auth_status")
            return SimpleNamespace(isAuthenticated=True, authType="token", host="https://github.com", login="octocat")

        async def list_models(self):
            calls.append("CopilotClient.list_models")
            return []

        async def _quota(self, request):
            calls.append("client.rpc.account.get_quota")
            return SimpleNamespace(quota_snapshots={})

        async def create_session(self, **options):
            calls.append("CopilotClient.create_session")
            return Session(options)

    sdk = SimpleNamespace(CopilotClient=Client, __version__=SDK_WRITTEN_FOR)
    return sdk, SimpleNamespace(PermissionDecisionReject=FakeReject, AccountGetQuotaRequest=FakeQuotaRequest)


def named(call: str) -> str:
    """A call on the card as the recorder names it: what comes before its arguments."""
    return call.split("(")[0]


def test_the_cards_are_sound_and_are_the_plugins():
    assert problems(APIS, today=date(2026, 11, 11)) == []
    assert ASSISTANT.apis == APIS and copilot.CopilotPlugin.apis is APIS and copilot.APIS is APIS
    assert [a.kind for a in APIS] == ["sdk", "command"] and all(a.verified == "2026-11-11" for a in APIS)
    assert SDK_WRITTEN_FOR in COPILOT_SDK.version and COPILOT_SDK.link("source") == "https://github.com/github/copilot-sdk"
    assert COPILOT_SDK.link("console") == ASSISTANT.signup  # the token is made where the plugin's setup says
    assert all(COPILOT_SDK.link(k) for k in ("docs", "reference", "auth", "limits", "pricing", "status", "changelog"))
    assert "Copilot Requests" in COPILOT_SDK.auth and "1,500" in COPILOT_SDK.limits and "$0.01" in COPILOT_SDK.costs
    assert {copilot.PRICING, copilot.PLANS_PAGE, copilot.MODELS_PAGE} <= set(urls(APIS))  # the tables' pages among them
    assert ASSISTANT.interface()["apis"] == ["GitHub Copilot SDK", "Copilot runtime (the SDK's CLI server)"]
    assert ASSISTANT.api_facts() == {}  # the instance keeps nothing of a run: each Connect builds its own Assistant


def test_the_card_names_exactly_the_sdk_calls_the_runtime_makes(tmp_path):
    """The real SdkRuntime on a recording fake SDK: a runtime opened, the sign-in, the models, the allowance and one
    answer asked, then closed; and once more with a runtime that will not stop. The calls made are the SDK card's
    used calls, all of them."""
    calls: list = []
    for fails in (False, True):
        sdk, rpc = recording_sdk(calls, stop_fails=fails)
        with SdkRuntime(KEY, tmp_path / str(fails), sdk=sdk, rpc=rpc, environ={}).open() as conn:
            conn.auth(), conn.models(), conn.quota()
            assert conn.ask(Ask("auto", "You are terse.", "Is it open?", timeout=5.0))["text"] == "OK"
    assert set(calls) == {named(c.name) for c in COPILOT_SDK.used}
    used = {named(c.name): c for c in COPILOT_SDK.used}
    assert used["CopilotSession.send_and_wait"].costs and not used["CopilotClient.list_models"].costs
    assert all(c.area in {a.name for a in COPILOT_SDK.areas} for c in COPILOT_SDK.calls)
    assert len(COPILOT_SDK.areas) > len(COPILOT_SDK.covered) and len(COPILOT_SDK.calls) > len(COPILOT_SDK.used)
    assert [c.name for c in COPILOT_RUNTIME.used] == ["copilot-runtime (a child process, JSON-RPC over stdio)"]
    assert all(c.area in {a.name for a in COPILOT_RUNTIME.areas} for c in COPILOT_RUNTIME.calls)


def test_every_address_is_githubs_own():
    hosts = {urlsplit(u).hostname for u in urls(APIS)}
    assert hosts == {"docs.github.com", "github.com", "github.blog", "pypi.org", "www.githubstatus.com"}
    assert all(u.startswith(("https://github.com/github/copilot-sdk", "https://github.com/settings/"))
               for u in urls(APIS) if urlsplit(u).hostname == "github.com")
