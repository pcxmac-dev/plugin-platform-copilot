"""Fakes and guards: tests never read the user's saved keys, never touch the machine's real ledgers,
never import the Copilot SDK, never start a process and never send a request (a FakeRuntime answers
the assistant; a fake SDK module stands in for the copilot package under the real SdkRuntime)."""
from __future__ import annotations

from contextlib import contextmanager
from types import SimpleNamespace

import pytest


@pytest.fixture(autouse=True)
def no_saved_keys(monkeypatch, tmp_path):
    """Tests never read the user's saved keys (their user environment variables), never load the
    workspace's plugin directory, and count on scratch ledgers."""
    from liminal_libs import config, layout

    monkeypatch.setattr(config, "saved_user_keys", lambda: {})
    monkeypatch.setattr(layout, "plugins_dir", lambda: None)
    monkeypatch.setenv("LIMINAL_LIVE_LOCK", str(tmp_path / "machine" / "live.lock"))


@pytest.fixture
def installed(monkeypatch):
    """The plugin loaded as an installed package's entry point, as the app loads it."""
    from liminal_libs.sources import registry

    def install(*plugins):
        eps = [SimpleNamespace(name=p.name, value=f"plugin_platform_{p.name}", load=(lambda p=p: p)) for p in plugins]
        monkeypatch.setattr(registry, "_entry_points", lambda: eps)
        registry.reload()
        return registry.assistants()

    yield install
    registry._providers = None


@pytest.fixture
def settings_for(tmp_path):
    from liminal_libs.config import load_settings

    def make(**env):
        return load_settings(env={"LIMINAL_DB": str(tmp_path / "m.db"), **env}, env_file=None)
    return make


# -- the runtime's place: what the assistant is given instead of the SDK's -------------------------------

SIGNED_IN = {"authenticated": True, "type": "token", "host": "https://github.com", "login": "octocat", "message": ""}


class FakeRuntime:
    """The runtime (runtime.SdkRuntime's place): what each call answers (a value, or an exception
    raised), every call recorded, every open and close counted; nothing imported or started."""

    def __init__(self, *, auth=None, models=(), quota=None, answers=(), version="1.0.29", open_error=None):
        self.auth_ = dict(SIGNED_IN) if auth is None else auth
        self.models_ = list(models) if not isinstance(models, Exception) else models
        self.quota_ = quota
        self.answers = list(answers)
        self.version = version
        self.open_error = open_error
        self.calls: list[tuple] = []
        self.opened = self.closed = 0

    @property
    def asks(self) -> list:
        return [c[1] for c in self.calls if c[0] == "ask"]

    @contextmanager
    def open(self):
        if self.open_error is not None:
            raise self.open_error
        self.opened += 1
        try:
            yield self
        finally:
            self.closed += 1

    @staticmethod
    def _give(value):
        if isinstance(value, Exception):
            raise value
        return value

    def auth(self):
        self.calls.append(("auth",))
        return self._give(self.auth_)

    def models(self):
        self.calls.append(("models",))
        return self._give(self.models_)

    def quota(self):
        self.calls.append(("quota",))
        return self._give(self.quota_)

    def ask(self, ask):
        self.calls.append(("ask", ask))
        return self._give(self.answers.pop(0))


def answer(text, model="gpt-6-luna", in_=120, out=30, read=20, wrote=0, thought=8, finish="stop", filtered=False,
           nano=4_500_000.0, sub=None):
    """An answer as the runtime gives it (runtime.answer_of): the text and each model call's usage."""
    calls = [{"model": model, "input": in_, "output": out, "cache_read": read, "cache_write": wrote, "reasoning": thought,
              "finish": finish, "filtered": filtered, "nano_aiu": nano, "request_id": "svc-req-1", "sub": False}]
    if sub:
        calls.append({**calls[0], **sub, "sub": True})
    return {"text": text, "message_id": "msg-1", "request_id": "", "model": "", "asked": "auto", "usage": calls}


def listed(model_id, input_usd=None, output_usd=None, policy="enabled", batch=1_000_000):
    """A model as the runtime lists it (runtime.model_row), its prices in AI credits per batch of tokens."""
    prices = None if input_usd is None else {"input": input_usd / 0.01 * batch / 1_000_000,
                                              "output": output_usd / 0.01 * batch / 1_000_000, "cache": None, "batch": batch}
    return {"id": model_id, "name": model_id, "policy": policy, "multiplier": 1.0, "prices": prices, "context": None,
            "efforts": []}


# -- the SDK's place: the copilot and copilot.rpc modules, for the real SdkRuntime ----------------------

class FakeReject:
    """copilot.rpc.PermissionDecisionReject's place."""

    def __init__(self, feedback=""):
        self.feedback = feedback


class FakeQuotaRequest:
    """copilot.rpc.AccountGetQuotaRequest's place."""


def event(kind, agent_id=None, **data):
    """A session event as the SDK gives it: a type (an enum: its value the string), its data."""
    return SimpleNamespace(type=SimpleNamespace(value=kind), data=SimpleNamespace(**data), agent_id=agent_id, ephemeral=None)


class FakeSdkSession:
    def __init__(self, options, script):
        self.options, self.script = options, script
        self.sent: list = []
        self.disconnected = False

    async def send_and_wait(self, prompt, *, timeout=60.0):
        self.sent.append((prompt, timeout))
        for e in self.script.get("events", ()):
            self.options["on_event"](e)
        failing = self.script.get("error")
        if failing is not None:
            self.options["on_event"](failing)
            raise Exception(f"Session error: {failing.data.message}")
        if self.script.get("raise") is not None:
            raise self.script["raise"]
        return self.script.get("final")

    async def disconnect(self):
        self.disconnected = True


@pytest.fixture
def fake_sdk():
    """make(**script) -> (the copilot module's place, copilot.rpc's place, the clients made): each
    client keeps its options and its sessions, answering by the script (auth, models, quota, events,
    final, error, raise, start_error)."""

    def make(**script):
        made: list = []

        class FakeClient:
            def __init__(self, **options):
                self.options = options
                self.started = self.stopped = False
                self.sessions: list = []
                self.quota_request = None
                self.rpc = SimpleNamespace(account=SimpleNamespace(get_quota=self._quota))
                made.append(self)

            async def start(self):
                if script.get("start_error") is not None:
                    raise script["start_error"]
                self.started = True

            async def stop(self):
                self.stopped = True

            async def get_auth_status(self):
                return script.get("auth")

            async def list_models(self):
                return list(script.get("models", ()))

            async def _quota(self, request):
                self.quota_request = request
                return script.get("quota")

            async def create_session(self, **options):
                session = FakeSdkSession(options, script)
                self.sessions.append(session)
                return session

        sdk = SimpleNamespace(CopilotClient=FakeClient, __version__="1.0.29")
        rpc = SimpleNamespace(PermissionDecisionReject=FakeReject, AccountGetQuotaRequest=FakeQuotaRequest)
        return sdk, rpc, made

    return make
