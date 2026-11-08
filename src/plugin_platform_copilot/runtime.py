"""GitHub's Copilot SDK (github-copilot-sdk) driven for one assistant's calls: the documented, terms-
compliant way an application reaches Copilot (the SDK's general availability, 2026-06-02: open to
"all existing GitHub Copilot subscribers, including Copilot Free for personal use"). GitHub Models,
the OpenAI-compatible endpoint at models.github.ai, was retired on 2026-07-30 (its inference API gone
for every customer), and the chat endpoints and token exchange GitHub's own editors use are not
documented for anyone else: neither is used here.

The SDK runs Copilot's runtime as a child process it starts and speaks JSON-RPC to over stdio; the
runtime makes the model calls. Here it runs only while a call needs it (`SdkRuntime.open`: started,
asked, stopped, whatever happened) and as locked down as the SDK allows: its "empty" mode (no
environment context, no telemetry, no custom instructions, no host files or git, no session store, no
memory, no skills), no tool at all (`available_tools=[]`, and every permission request refused), the
system prompt replaced by the argument's own, the token passed explicitly with the user's stored
logins and the environment's GitHub tokens ignored (`use_logged_in_user=False`), and a child
environment without this machine's other credentials. The SDK is the plugin's `sdk` extra (Python
3.11 or later); nothing of it is imported until a call needs it.

What the assistant gets back is plain data (`Connection.auth`, `models`, `quota`, `ask`), so it knows
nothing of the SDK's types; a refusal is a CopilotError carrying the upstream HTTP status, the error
type and code the runtime gave (its session.error event), or this module's own kinds: setup (no SDK,
no runtime) and timeout.
"""
from __future__ import annotations

import asyncio
import concurrent.futures
import importlib
import os
import re
import threading
from contextlib import contextmanager
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Awaitable, Callable, Iterable, Iterator, Mapping

SDK_PACKAGE = "github-copilot-sdk"
SDK_MODULE = "copilot"
SDK_WRITTEN_FOR = "1.0.29"  # the SDK release this plugin was written against (its 1.x API; the sdk extra allows <2)
INSTALL = ('install the SDK with pip install "plugin-platform-copilot[sdk]", then fetch its runtime once with '
           "python -m copilot download-runtime")
START_SECONDS = 90.0  # the runtime's start (a first one may fetch the runtime: download-runtime spares that)
CALL_SECONDS = 60.0  # an account read: the sign-in, the models, the allowance
ANSWER_SECONDS = 180.0  # an answer (a reasoning model may think a while)
STOP_SECONDS = 15.0
NO_TOOLS = "this assistant answers in words only: no tool may run"

# What the runtime's environment leaves out: the variables it would take a token, a provider (BYOK) or a
# model from on its own, and any other program's credential here (the other plugins' keys and accounts).
GITHUB_VARIABLES = frozenset({"GH_TOKEN", "GITHUB_TOKEN", "GH_ENTERPRISE_TOKEN", "GITHUB_ENTERPRISE_TOKEN"})
OWN_PREFIXES = ("COPILOT_", "GITHUB_COPILOT_")
CREDENTIAL = re.compile(r"(^|_)(API_KEY|KEY|KEY_ID|KEYS|TOKEN|TOKENS|SECRET|SECRET_KEY|PASSWORD|PASSWD|ACCOUNT|"
                        r"CREDENTIAL|CREDENTIALS|PAT)$")

# Words a refusal without a session.error event is read by: (status, error type, the words)
WORDS: tuple[tuple[int, str, tuple[str, ...]], ...] = (
    (401, "authentication", ("401", "unauthorized", "authentication failed", "not authenticated", "bad credentials",
                             "no authentication information", "classic personal access token")),
    (403, "authorization", ("403", "forbidden", "access denied", "denied by policy", "not enabled for")),
    (402, "quota", ("402", "quota", "ai credit", "out of credits", "budget", "payment required", "spending limit")),
    (429, "rate_limit", ("429", "rate limit", "rate-limit", "too many requests")),
    (404, "model", ("404", "unknown model", "no such model", "model not found", "model is not available",
                    "model not available", "not a valid model")),
)


class CopilotError(Exception):
    """What the runtime refused or could not do, in its own terms: the upstream HTTP status (0: none
    given), the error type (its session.error's errorType: authentication, quota, rate_limit ...; or
    setup and timeout, this module's own), its code, and its message (not yet scrubbed)."""

    def __init__(self, message: str, status: int = 0, kind: str = "", code: str = ""):
        super().__init__(str(message))
        self.message = str(message)
        self.status = _int(status) or 0
        self.kind = str(kind or "")
        self.code = str(code or "")


@dataclass(frozen=True)
class Ask:
    """One prompt as a session takes it: the model ("auto": Copilot chooses), the system prompt (in
    place of the runtime's own), the user's text, the reasoning effort ("": the model's default), and
    how long the answer may take."""
    model: str
    system: str
    prompt: str
    effort: str = ""
    timeout: float = ANSWER_SECONDS


# -- what the SDK is given ----------------------------------------------------------------------------

def child_env(environ: Mapping[str, str]) -> dict[str, str]:
    """The runtime's environment: this process's, without the variables the runtime would read a token,
    a provider or a model from on its own (COPILOT_*, GH_TOKEN, GITHUB_TOKEN ...) and without any other
    program's credential (a name ending in _KEY, _TOKEN, _SECRET, _PASSWORD, _ACCOUNT ...)."""
    out: dict[str, str] = {}
    for k, v in environ.items():
        up = str(k).upper()
        if up in GITHUB_VARIABLES or up.startswith(OWN_PREFIXES) or CREDENTIAL.search(up):
            continue
        out[str(k)] = str(v)
    return out


def client_options(token: str, home: Path, environ: Mapping[str, str]) -> dict:
    """CopilotClient's options: the token given explicitly and no other credential of the machine's
    (use_logged_in_user False: no stored login, no gh login, no environment token), the "empty" mode,
    the runtime's home and working folder the plugin's own, its environment cleaned (child_env)."""
    return {"github_token": token, "use_logged_in_user": False, "mode": "empty", "base_directory": str(home),
            "working_directory": str(home), "env": child_env(environ)}


def session_options(ask: Ask, deny: Callable, on_event: Callable) -> dict:
    """create_session's options for one answer: the model, the system prompt replaced, no tool, every
    permission request refused, no streaming, no compaction, every event kept; the effort where set."""
    out = {"model": ask.model, "system_message": {"mode": "replace", "content": ask.system}, "available_tools": [],
           "on_permission_request": deny, "streaming": False, "infinite_sessions": {"enabled": False},
           "on_event": on_event}
    if ask.effort:
        out["reasoning_effort"] = ask.effort
    return out


def denial(rpc) -> Callable:
    """The permission handler: every request refused (no tool is offered, so none should come)."""
    reject = getattr(rpc, "PermissionDecisionReject", None) if rpc is not None else None

    def deny(request=None, invocation=None):
        if reject is None:
            raise PermissionError(NO_TOOLS)
        return reject(feedback=NO_TOOLS)

    return deny


# -- what the SDK gives back, as plain data -------------------------------------------------------------

def _get(obj: Any, *names: str) -> Any:
    """The first of these attributes (or keys) the object has set; None when none is."""
    if obj is None:
        return None
    for n in names:
        v = obj.get(n) if isinstance(obj, Mapping) else getattr(obj, n, None)
        if v is not None:
            return v
    return None


def _int(value: Any) -> int | None:
    try:
        return int(float(str(value).strip())) if value not in (None, "") else None
    except (TypeError, ValueError):
        return None


def _num(value: Any) -> float | None:
    try:
        return float(value) if value not in (None, "") else None
    except (TypeError, ValueError):
        return None


def event_type(event: Any) -> str:
    """An event's type as its string (assistant.usage, session.error ...), however the SDK holds it."""
    kind = getattr(event, "type", None)
    value = getattr(kind, "value", kind)
    return str(value or getattr(event, "raw_type", "") or "")


def usage_row(event: Any) -> dict:
    """One model call's usage (an assistant.usage event): its tokens, how it ended, Copilot's own cost
    figure (nano AI credits), its request id, whether a sub-agent made it."""
    d = getattr(event, "data", None)
    billed = _get(d, "copilot_usage", "copilotUsage")
    return {"model": str(_get(d, "model") or ""),
            "input": _int(_get(d, "input_tokens", "inputTokens")) or 0,
            "output": _int(_get(d, "output_tokens", "outputTokens")) or 0,
            "cache_read": _int(_get(d, "cache_read_tokens", "cacheReadTokens")) or 0,
            "cache_write": _int(_get(d, "cache_write_tokens", "cacheWriteTokens")) or 0,
            "reasoning": _int(_get(d, "reasoning_tokens", "reasoningTokens")) or 0,
            "finish": str(_get(d, "finish_reason", "finishReason") or ""),
            "filtered": bool(_get(d, "content_filter_triggered", "contentFilterTriggered")),
            "nano_aiu": _num(_get(billed, "total_nano_aiu", "totalNanoAiu")),
            "request_id": str(_get(d, "service_request_id", "serviceRequestId", "api_call_id", "apiCallId",
                                   "provider_call_id", "providerCallId") or ""),
            "sub": bool(getattr(event, "agent_id", None) or _get(d, "initiator") == "sub-agent")}


def answer_of(final: Any, events: Iterable[Any], ask: Ask) -> dict:
    """An answer as the assistant reads it: the final message's text and ids, and each model call's
    usage (every call is billed, a sub-agent's too)."""
    d = getattr(final, "data", None)
    return {"text": str(_get(d, "content") or ""), "message_id": str(_get(d, "message_id", "messageId") or ""),
            "request_id": str(_get(d, "request_id", "requestId", "service_request_id", "serviceRequestId") or ""),
            "model": str(_get(d, "model") or ""), "asked": ask.model,
            "usage": [usage_row(e) for e in events if event_type(e) == "assistant.usage"]}


def model_row(m: Any) -> dict:
    """A model the server lists (ModelInfo): its id and name, its policy for this account, its prices
    (AI credits per batch of tokens) and multiplier, its context window, its reasoning levels."""
    billing = _get(m, "billing")
    prices = _get(billing, "token_prices", "tokenPrices")
    limits = _get(_get(m, "capabilities"), "limits")
    return {"id": str(_get(m, "id") or ""), "name": str(_get(m, "name") or _get(m, "id") or ""),
            "policy": str(_get(_get(m, "policy"), "state") or ""),
            "multiplier": _num(_get(billing, "multiplier")),
            "prices": None if prices is None else {
                "input": _num(_get(prices, "input_price", "inputPrice")),
                "output": _num(_get(prices, "output_price", "outputPrice")),
                "cache": _num(_get(prices, "cache_price", "cachePrice")),
                "batch": _int(_get(prices, "batch_size", "batchSize"))},
            "context": _int(_get(limits, "max_context_window_tokens", "maxContextWindowTokens")),
            "efforts": [str(x) for x in (_get(m, "supported_reasoning_efforts", "supportedReasoningEfforts") or ())]}


def quota_rows(result: Any) -> dict:
    """The account's allowances (account.getQuota's quotaSnapshots), by their names."""
    snaps = _get(result, "quota_snapshots", "quotaSnapshots") or {}
    items = snaps.items() if isinstance(snaps, Mapping) else ()
    return {str(k): {"entitlement": _int(_get(s, "entitlement_requests", "entitlementRequests")),
                     "used": _int(_get(s, "used_requests", "usedRequests")),
                     "remaining": _num(_get(s, "remaining_percentage", "remainingPercentage")),
                     "reset": str(_get(s, "reset_date", "resetDate") or ""),
                     "unlimited": bool(_get(s, "is_unlimited_entitlement", "isUnlimitedEntitlement"))}
            for k, s in items}


def classify(message: str) -> tuple[int, str]:
    """A refusal's status and type read from its words, where the runtime sent no session.error."""
    low = message.lower()
    for status, kind, words in WORDS:
        if any(w in low for w in words):
            return status, kind
    return 0, ""


def last_error(events: Iterable[Any]) -> CopilotError | None:
    """The runtime's last session.error event as a CopilotError (its status, type, code, message)."""
    for e in reversed(list(events)):
        if event_type(e) == "session.error":
            d = getattr(e, "data", None)
            return CopilotError(str(_get(d, "message") or "the session failed"),
                                _int(_get(d, "status_code", "statusCode")) or 0,
                                str(_get(d, "error_type", "errorType") or ""), str(_get(d, "error_code", "errorCode") or ""))
    return None


def failure(exc: BaseException, events: Iterable[Any] = ()) -> CopilotError:
    """The CopilotError an SDK exception is: the session.error event the runtime sent before it (its
    status, type and code), else the exception's own words read for a status."""
    if isinstance(exc, CopilotError):
        return exc
    sent = last_error(events)
    if sent is not None:
        return sent
    if isinstance(exc, ImportError):
        return CopilotError(f"the Copilot SDK could not be loaded ({exc}): {INSTALL}", kind="setup")
    if isinstance(exc, TimeoutError):
        return CopilotError(f"no answer in time ({exc})" if str(exc) else "no answer in time", kind="timeout")
    if isinstance(exc, OSError) and not isinstance(exc, ConnectionError):
        return CopilotError(f"the Copilot runtime could not start: {type(exc).__name__}: {exc} ({INSTALL})", kind="setup")
    text = str(exc) or type(exc).__name__
    status, kind = classify(text)
    return CopilotError(text, status, kind, str(getattr(exc, "code", "") or ""))


# -- the runtime ----------------------------------------------------------------------------------------

class SdkRuntime:
    """The Copilot SDK for one token: nothing imported, started or written until `open` is entered;
    inside it the runtime runs (on an event loop of its own, on a thread of its own, so every call is
    a plain one whatever the caller's loop), and it is stopped on the way out, whatever happened. `sdk`
    and `rpc` stand in for the copilot and copilot.rpc modules (the tests' fakes)."""

    def __init__(self, token: str, home: Path | str | None = None, *, sdk: Any = None, rpc: Any = None,
                 environ: Mapping[str, str] | None = None, module: str = SDK_MODULE):
        self._token = token or ""
        self._home = Path(home) if home is not None else None
        self._sdk, self._rpc, self._environ, self._module = sdk, rpc, environ, module

    def __repr__(self) -> str:
        return f"<SdkRuntime {self._module}>"  # never the token

    @property
    def home(self) -> Path:
        """The runtime's home (COPILOT_HOME) and working folder: the plugin's own in the data folder."""
        if self._home is None:
            from liminal_libs import layout

            self._home = layout.data_dir() / "assistants" / "copilot"
        return self._home

    @home.setter
    def home(self, value: Path | str) -> None:
        self._home = Path(value)

    def modules(self) -> tuple[Any, Any]:
        """The SDK's modules (copilot, copilot.rpc), imported when first asked; CopilotError (setup) when
        the SDK is not installed."""
        if self._sdk is None:
            try:
                self._sdk = importlib.import_module(self._module)
            except ImportError:
                raise CopilotError(f"the Copilot SDK is not installed here: {INSTALL}", kind="setup") from None
        if self._rpc is None:
            for name in (f"{self._module}.rpc", f"{self._module}.generated.rpc"):
                try:
                    self._rpc = importlib.import_module(name)
                    break
                except ImportError:
                    continue
        return self._sdk, self._rpc

    @contextmanager
    def open(self) -> Iterator["Connection"]:
        """The runtime started for the calls inside (one child process, the SDK's), stopped after them."""
        sdk, rpc = self.modules()
        home = self.home
        home.mkdir(parents=True, exist_ok=True)
        loop = asyncio.new_event_loop()
        thread = threading.Thread(target=loop.run_forever, name="copilot-sdk", daemon=True)
        thread.start()
        conn = Connection(sdk, rpc, loop, str(getattr(sdk, "__version__", "") or ""))
        try:
            conn.start(client_options(self._token, home, os.environ if self._environ is None else self._environ))
            yield conn
        finally:
            try:
                conn.stop()
            finally:
                conn.settle()
                loop.call_soon_threadsafe(loop.stop)
                thread.join(STOP_SECONDS)
                if not thread.is_alive():
                    loop.close()


class Connection:
    """The runtime while `SdkRuntime.open` holds it: its calls, each a plain one returning plain data."""

    def __init__(self, sdk: Any, rpc: Any, loop: asyncio.AbstractEventLoop, version: str = ""):
        self._sdk, self._rpc, self._loop = sdk, rpc, loop
        self.version = version
        self.client: Any = None

    def _run(self, make: Callable[[], Awaitable], seconds: float):
        future = asyncio.run_coroutine_threadsafe(make(), self._loop)
        try:
            return future.result(seconds)
        except concurrent.futures.TimeoutError:
            if future.done():
                raise  # the call's own timeout (send_and_wait's): failure() reads it
            future.cancel()
            raise CopilotError(f"no answer from the Copilot runtime in {seconds:g} s", kind="timeout") from None

    def _call(self, make: Callable[[], Awaitable], seconds: float, events: Iterable[Any] = ()):
        try:
            return self._run(make, seconds)
        except CopilotError:
            raise
        except Exception as e:  # noqa: BLE001 - the SDK's exception is the refusal: read into a CopilotError
            raise failure(e, events) from None

    def start(self, options: dict) -> None:
        async def make():
            self.client = self._sdk.CopilotClient(**options)
            await self.client.start()

        self._call(make, START_SECONDS)

    def stop(self) -> None:
        client, self.client = self.client, None
        if client is None:
            return
        try:
            self._run(client.stop, STOP_SECONDS)
        except Exception:  # noqa: BLE001 - a runtime that will not stop gracefully is stopped by force
            try:
                self._run(client.force_stop, STOP_SECONDS)
            except Exception:  # noqa: BLE001 - nothing more can be done from here
                pass

    def settle(self) -> None:
        """Whatever the SDK left running on the loop (its readers) cancelled, so the loop closes clean."""

        async def cancel_all():
            tasks = [t for t in asyncio.all_tasks() if t is not asyncio.current_task()]
            for t in tasks:
                t.cancel()
            await asyncio.gather(*tasks, return_exceptions=True)
            await asyncio.get_running_loop().shutdown_asyncgens()

        try:
            self._run(cancel_all, STOP_SECONDS)
        except Exception:  # noqa: BLE001 - a loop that will not settle is stopped all the same
            pass

    def auth(self) -> dict:
        """Whether the runtime is signed in with the token: {authenticated, type, host, login, message}."""
        status = self._call(lambda: self.client.get_auth_status(), CALL_SECONDS)
        return {"authenticated": bool(_get(status, "isAuthenticated", "is_authenticated")),
                "type": str(_get(status, "authType", "auth_type") or ""), "host": str(_get(status, "host") or ""),
                "login": str(_get(status, "login") or ""), "message": str(_get(status, "statusMessage", "status_message") or "")}

    def models(self) -> list[dict]:
        """The models the server lists for this account (model_row each)."""
        listed = self._call(lambda: self.client.list_models(), CALL_SECONDS)
        return [model_row(m) for m in (listed or ())]

    def quota(self) -> dict | None:
        """The account's allowances (quota_rows); None where the runtime gives none (a quota that cannot
        be read is no refusal: "a failed or unavailable acquisition is not quota exhaustion")."""
        account = getattr(getattr(self.client, "rpc", None), "account", None)
        request = getattr(self._rpc, "AccountGetQuotaRequest", None)
        if account is None or request is None or not hasattr(account, "get_quota"):
            return None
        try:
            result = self._run(lambda: account.get_quota(request()), CALL_SECONDS)
        except Exception:  # noqa: BLE001 - see the docstring
            return None
        return quota_rows(result)

    def ask(self, ask: Ask) -> dict:
        """One answer in a session of its own (answer_of), the session ended after it."""
        events: list = []
        deny = denial(self._rpc)

        async def make():
            session = await self.client.create_session(**session_options(ask, deny, events.append))
            try:
                return await session.send_and_wait(ask.prompt, timeout=ask.timeout)
            finally:
                try:
                    await session.disconnect()
                except Exception:  # noqa: BLE001 - the answer, or its refusal, is what counts
                    pass

        final = self._call(make, ask.timeout + 30.0, events)
        return answer_of(final, events, ask)
