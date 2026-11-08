"""Copilot through GitHub's Copilot SDK (runtime.py) behind the library's Assistant (liminal_libs.
assistants): the same hooks as the other assistants' (`body`, `parse`, `parse_models`, `error`,
`final`, `limits_from`), filled with the SDK's shapes, and `models`, `answer` and `connect` going
through the runtime instead of the contract's HTTP client, each counted on the plugin's caps (the
machine's requests and tokens a day) as the client counts its own requests.

What a session is asked (`body`): the model ("auto": Copilot chooses), the argument's system prompt in
place of the runtime's, the user's text, the reasoning effort where set; nothing about the account
(the SDK takes no user field) and no output cap (it takes none: the answer's tokens are counted
after). An answer's usage is every model call's (an assistant.usage event each: input with the cache
reads and writes, output with the reasoning), its model the one that answered (auto's choice), its
cost by that model's prices in the table (Copilot bills tokens at the model's published rate). A
refusal is said in words (`error`), scrubbed of the token and the account.

Connect (`connect`): the runtime started once, the token tried (the sign-in the runtime reports), the
models the server lists for this account compared with the table (the ones the plan reaches, and
their prices: the server's AI credits per batch of tokens against the table's dollars), the account
named checked against the token's, the allowance left (the server's quota), and unless `light`, one
answer of a few tokens. Copilot sends no limits the plans differ by, so the plan stays yours.
"""
from __future__ import annotations

import time
from typing import Any, Mapping

from liminal_libs.assistants import Assistant, Parsed, Prompt, Usage
from liminal_libs.errors import BudgetExhausted, NotEntitled, RateLimited, SourceError, Unauthorized
from liminal_libs.sources.plugin import Scanned

from .runtime import ANSWER_SECONDS, SDK_PACKAGE, SDK_WRITTEN_FOR, Ask, CopilotError, SdkRuntime

AUTO = "auto"  # auto model selection: Copilot picks the model for each prompt (the only one on Free and Student)
HOST = "https://api.github.com"
PROBE_SECONDS = 60.0
CREDIT_USD = 0.01  # 1 AI credit = $0.01 USD (the pricing page)
TOKEN_HELP = ("a fine-grained personal access token (github_pat_) owned by your personal account with the Copilot "
              "Requests account permission, or an OAuth (gho_) or GitHub App user (ghu_) token")
AUTH_KINDS = ("authentication", "auth", "unauthorized", "unauthenticated")
DENIED_KINDS = ("authorization", "forbidden", "policy", "permission", "access_denied", "not_entitled")
QUOTA_KINDS = ("quota", "billing", "budget", "credits", "insufficient_quota")
QUOTA_WORDS = ("quota", "ai credit", "out of credits", "budget", "spending limit", "payment required")
MODEL_KINDS = ("model", "model_not_found", "not_found", "unknown_model", "model_not_supported")
RATE_KINDS = ("rate_limit", "rate_limited", "ratelimit", "too_many_requests")


class CopilotAssistant(Assistant):
    """Copilot: the library's Assistant over the Copilot SDK's runtime (see the module's docstring).
    `session` is the runtime when it has `open` (the tests' fake); else the SDK's own (SdkRuntime)."""

    base_url = HOST  # the account's host: nothing of this plugin's own is sent there (the runtime talks to Copilot)
    models_path = ""  # the models come from the runtime (models.list), not from a path of this plugin's
    answers_path = ""
    request_id_header = "x-github-request-id"
    limit_prefixes = ()
    probe_tokens = 16

    def __init__(self, plugin, settings, session=None, now=None, sleep=time.sleep):
        runtime = session if callable(getattr(session, "open", None)) else None
        super().__init__(plugin, settings, session=None, now=now, sleep=sleep)
        self.runtime = runtime if runtime is not None else SdkRuntime(settings.key or "")

    # -- the hooks, in the SDK's shapes ----------------------------------------------------------------

    def headers(self, key: str) -> dict:
        """None of this plugin's: the token goes to the SDK's client (its github_token), never into a
        header of this plugin's."""
        return {}

    def body(self, prompt: Prompt, model: str, user_id: str) -> dict:
        """What a session is asked (an Ask's fields): nothing about the account, no output cap."""
        out = {"model": model, "system": prompt.system, "prompt": prompt.user}
        if self.settings.effort:
            out["effort"] = self.settings.effort
        return out

    def parse(self, raw: Mapping[str, Any]) -> Parsed:
        """An answer (runtime.answer_of): its text, every model call's usage summed (input with the cache
        reads and writes among it, output with the reasoning), how it ended, the model that answered."""
        calls = [u for u in (raw.get("usage") or ()) if isinstance(u, Mapping)]
        inp = sum(int(u.get("input") or 0) for u in calls)
        read = sum(int(u.get("cache_read") or 0) for u in calls)
        wrote = sum(int(u.get("cache_write") or 0) for u in calls)
        out = sum(int(u.get("output") or 0) for u in calls)
        thought = sum(int(u.get("reasoning") or 0) for u in calls)
        # the cache reads and writes are among the input tokens; a count without them is added to
        usage = Usage(inp if inp >= read + wrote else inp + read + wrote, out, read, thought, max(len(calls), 1))
        root = [u for u in calls if not u.get("sub")] or calls
        last = root[-1] if root else {}
        filtered = any(u.get("filtered") or u.get("finish") == "content_filter" for u in root)
        finish = str(last.get("finish") or "")
        stop = "refusal" if filtered else "length" if finish in ("length", "max_tokens") else "end_turn"
        model = str(last.get("model") or raw.get("model") or "")
        request_id = str(raw.get("request_id") or last.get("request_id") or raw.get("message_id") or "")
        return Parsed(str(raw.get("text") or ""), usage, stop, request_id, model, None, raw)

    def parse_models(self, raw) -> list[dict]:
        """The server's models (runtime.model_row each): [{id, title, policy, prices ...}]."""
        rows = raw if isinstance(raw, (list, tuple)) else (raw or {}).get("data", []) if isinstance(raw, Mapping) else []
        return [{**m, "id": str(m["id"]), "title": str(m.get("name") or m["id"])}
                for m in rows if isinstance(m, Mapping) and m.get("id")]

    def error(self, status: int, body, message: str) -> SourceError | None:
        """A refusal in words, by the upstream status and the runtime's error type ({kind, code} in
        `body`); `message` comes scrubbed. None: the plain SourceError."""
        info = body if isinstance(body, Mapping) else {}
        kind = str(info.get("kind") or "").lower().replace("-", "_")
        code = str(info.get("code") or "").lower()
        low = message.lower()
        quota = kind in QUOTA_KINDS or any(w in low or w in code for w in QUOTA_WORDS)
        if kind == "setup":
            return SourceError(0, message)
        if kind == "timeout":
            return SourceError(0, message if message.startswith("no answer") else f"no answer: {message}")
        if status == 401 or kind in AUTH_KINDS:
            return Unauthorized(401, f"the token was refused: {message} (Copilot takes {TOKEN_HELP}; a classic ghp_ "
                                     "token is not taken)")
        if status == 402 or (quota and status in (0, 403, 429)):
            return NotEntitled(status or 402, f"no AI credits left for it: {message} (the allowance renews on the 1st "
                                              "at 00:00 UTC; a budget for additional usage on GitHub's billing page "
                                              "lets it go on, at $0.01 a credit)")
        if status == 403 or kind in DENIED_KINDS:
            return NotEntitled(403, f"not allowed: {message} (the account needs a Copilot plan, the token the Copilot "
                                    "Requests permission, and an organization's policy must allow the Copilot CLI "
                                    "and the model)")
        if status == 404 or kind in MODEL_KINDS:
            return NotEntitled(404, f"no such model: {message} (choose one from Connect's list)")
        if status == 429 or kind in RATE_KINDS:
            return RateLimited(429, f"rate limited: {message} (Copilot publishes no limits: wait a little and try again)")
        return None

    def final(self, status: int, body) -> bool:
        """A quota's 429 is final: no AI credits left, trying again changes nothing."""
        info = body if isinstance(body, Mapping) else {}
        return status == 429 and str(info.get("kind") or "").lower() in QUOTA_KINDS

    def limits_from(self, headers: Mapping[str, Any]) -> tuple[int | None, int | None]:
        return None, None  # Copilot publishes no rate limits, and the runtime passes on no rate-limit headers

    # -- what is refused before anything is sent -------------------------------------------------------

    def classic(self) -> str | None:
        """Why the key is not even tried: a classic personal access token, which Copilot does not take."""
        if (self.settings.key or "").strip().startswith("ghp_"):
            return f"{self.name}: a classic personal access token (ghp_) is not taken by Copilot: make {TOKEN_HELP}"
        return None

    def refusal(self) -> str | None:
        return (self.classic() if self.settings.has_key else None) or super().refusal()

    def _refuse(self) -> None:
        why = self.classic() if self.settings.has_key else None
        if why:
            raise Unauthorized(0, why)
        super()._refuse()

    def _key(self) -> None:
        if not self.settings.has_key:
            raise Unauthorized(0, f"{self.name}: no key ({self.plugin.key_names[0]} is not set)")
        why = self.classic()
        if why:
            raise Unauthorized(0, why)

    def _count(self) -> None:
        """One request counted as it goes, as the contract's client counts its own: the plan's window
        (none published: no wait), the machine's daily cap (BudgetExhausted once reached)."""
        limiter = getattr(self.client, "_limiter", None)
        if limiter is not None:
            limiter.acquire()
        if self.client.take_day is not None and not self.client.take_day():
            raise BudgetExhausted("the daily request cap is reached on this machine (all its databases together)")
        self.client.requests_made += 1

    def refused(self, e: CopilotError) -> SourceError:
        """The runtime's refusal as the contract's error, in words, scrubbed of the token and the account."""
        message = self.client.scrub(e.message)
        return self.error(e.status, {"kind": e.kind, "code": e.code}, message) or SourceError(e.status, message)

    # -- what every assistant does, through the runtime ------------------------------------------------

    def models(self) -> list[dict]:
        """The models the server lists for this account (one request)."""
        self._key()
        self._count()
        try:
            with self.runtime.open() as rt:
                return self.parse_models(rt.models())
        except CopilotError as e:
            raise self.refused(e) from None

    def answer(self, prompt: Prompt, model: str, timeout: float = ANSWER_SECONDS) -> tuple[Parsed, dict, float]:
        """One answer to a prompt from a model, the runtime started for it and stopped after it:
        (what it holds, no headers, the answer's seconds)."""
        ask = Ask(timeout=timeout, **self.body(prompt, model, self.settings.user_id))
        self._count()
        try:
            with self.runtime.open() as rt:
                started = time.monotonic()
                raw = rt.ask(ask)
                seconds = round(time.monotonic() - started, 3)
        except CopilotError as e:
            raise self.refused(e) from None
        parsed = self.parse(raw)
        self.tokens.charge_day(parsed.usage.total, self.now())
        return parsed, {}, seconds

    def connect(self, light: bool = False) -> Scanned:
        """The capability scan (see the module's docstring): one runtime for every step, each step's
        refusal a row of its own."""
        s = self.settings
        if not s.has_key:
            raise Unauthorized(0, f"{self.name}: no key ({self.plugin.key_names[0]} is not set)")
        rows: list[tuple[str, bool, str]] = []
        limits: dict = {"seen": {}, "perMinute": None, "kept": list(self.window())}
        why = self.classic()
        if why:
            rows.append(("the key", False, f"not sent: {why}"))
            return Scanned(tuple(rows), {}, {}, limits)
        plan = self.plugin.plan_of(s.plan)
        try:
            with self.runtime.open() as rt:
                rows.append(sdk_row(str(getattr(rt, "version", "") or "")))
                auth = rt.auth()
                if not auth.get("authenticated"):
                    said = self.client.scrub(str(auth.get("message") or "the runtime is not signed in with it"))
                    rows.append(("the key", False, f"refused: {said} (Copilot takes {TOKEN_HELP})"))
                    return Scanned(tuple(rows), {}, {}, limits)
                try:
                    self._count()
                    listed = self.parse_models(rt.models())
                except CopilotError as e:
                    rows.append(("the key", False, f"refused: {self.refused(e).message}"))
                    return Scanned(tuple(rows), {}, {}, limits)
                rows += self.model_rows(auth, listed, plan)
                quota = rt.quota()
                if quota:
                    said = [allowance(k, q) for k, q in sorted(quota.items())]
                    rows.append(("its allowance", True, "; ".join(said)))
                    limits["seen"] = dict(zip(sorted(quota), said))
                if not light and plan is not None and plan.api_access:
                    rows.append(self.probe(rt))
        except CopilotError as e:
            err = self.refused(e)
            rows.append(("the Copilot SDK", False, err.message) if e.kind == "setup"
                        else ("the key", False, f"refused: {err.message}"))
        return Scanned(tuple(rows), {}, {}, limits)

    def model_rows(self, auth: Mapping[str, Any], listed: list[dict], plan) -> list[tuple[str, bool, str]]:
        """Connect's rows on the models: the key, the account, the model chosen, the table's models
        against the ones listed (those the plan reaches), and their prices."""
        s = self.settings
        by_id = {m["id"]: m for m in listed}
        ids = set(by_id)
        out = [("the key", True, f"accepted ({auth.get('type') or 'a token'}): {len(ids)} models listed by the server")]
        account, login, var = (s.account or "").strip(), str(auth.get("login") or ""), self.plugin.account_var
        if account and "@" not in account and login:  # an email cannot be told from the token's login
            same = account.lower() == login.lower()
            out.append(("the account", same, f"the token is the GitHub account {var} names" if same else
                        f"the token belongs to another GitHub account than {var} names: check the token or the account"))
        if s.model == AUTO:
            out.append((f"the model {AUTO}", bool(ids), "Copilot chooses among the models your plan and its policies allow"
                        if ids else "no model is listed for this account: has it a Copilot plan?"))
        else:
            m = by_id.get(s.model)
            state = str((m or {}).get("policy") or "")
            ok = m is not None and state in ("", "enabled")
            out.append((f"the model {s.model}", ok, "listed" if ok else
                        f"listed, but not enabled for this account (its policy: {state}): enable it in your Copilot "
                        "settings on GitHub" if m is not None else
                        "not listed by the server: choose another model (the ones listed are in the scan's rows below)"))
        reach = set(self.plugin.reach(plan)) - {AUTO} if plan is not None else set()
        gone = sorted(reach - ids)
        if gone:
            out.append(("the table's models", False, f"not listed by the server: {', '.join(gone)} (the table is stale, "
                                                     "or your plan or its policies leave them out: update the plugin, "
                                                     "or choose the plan you are on)"))
        new = sorted(ids - {m.id for m in self.plugin.models})
        if new:
            out.append(("models not in the table", True, ", ".join(new[:12]) + (" ..." if len(new) > 12 else "")))
        return out + self.price_rows(listed)

    def price_rows(self, listed: list[dict]) -> list[tuple[str, bool, str]]:
        """The table's prices against the server's (AI credits per batch of tokens, 1 credit $0.01)."""
        checked, differ = 0, []
        for m in listed:
            mine = self.plugin.model_of(m["id"])
            prices = m.get("prices") or {}
            batch = prices.get("batch") or 0
            if mine is None or mine.id == AUTO or batch <= 0 or prices.get("input") is None or prices.get("output") is None:
                continue
            checked += 1
            given_in, given_out = per_million(prices["input"], batch), per_million(prices["output"], batch)
            if not (close(given_in, mine.input_usd) and close(given_out, mine.output_usd)):
                differ.append(f"{mine.id}: the server's ${given_in:.2f} in and ${given_out:.2f} out a million tokens, "
                              f"the table's ${mine.input_usd:.2f} and ${mine.output_usd:.2f}")
        if differ:
            return [("the table's prices", False, "; ".join(differ[:6]) + (" ..." if len(differ) > 6 else "")
                     + " (the table is stale: update the plugin)")]
        return ([("the table's prices", True, f"the server's agree with the table's ({checked} "
                                              f"{'model' if checked == 1 else 'models'})")] if checked else [])

    def probe(self, rt) -> tuple[str, bool, str]:
        """Connect's one answer of a few tokens, with Copilot's own count of what it cost."""
        s = self.settings
        probe = Prompt("Reply with the single word OK.", "Are you there?", self.probe_tokens)
        try:
            self._count()
            ask = Ask(timeout=PROBE_SECONDS, **self.body(probe, s.model, s.user_id))
            started = time.monotonic()
            raw = rt.ask(ask)
            seconds = round(time.monotonic() - started, 3)
        except CopilotError as e:
            return ("an answer", False, f"refused: {self.refused(e).message}")
        parsed = self.parse(raw)
        self.tokens.charge_day(parsed.usage.total, self.now())
        nano = [float(u["nano_aiu"]) for u in raw.get("usage") or () if isinstance(u, Mapping) and u.get("nano_aiu") is not None]
        mine = self.plugin.model_of(parsed.model or s.model)
        detail = f"{parsed.model or s.model} answered in {seconds:g} s: {parsed.usage.total} tokens"
        if nano:
            detail += f", {sum(nano) / 1e9:.6f} AI credits by Copilot's count"
        if mine is not None and mine.id != AUTO:
            detail += f" ({credits(mine, parsed.usage):.6f} by the table's prices)"
        return ("an answer", True, detail)


def sdk_row(version: str) -> tuple[str, bool, str]:
    """Connect's row on the SDK: its release, and whether it is the major one this plugin was written for."""
    ok = not version or version.split(".")[0] == SDK_WRITTEN_FOR.split(".")[0]
    said = f"{SDK_PACKAGE} {version or '(its release not said)'}"
    return ("the Copilot SDK", ok, said if ok else f"{said}: this plugin was written for {SDK_WRITTEN_FOR}: update the plugin")


def allowance(name: str, q: Mapping[str, Any]) -> str:
    """An allowance in words: premium_interactions: 12 of 1,500 used (99.2% left), resets 2026-12-01."""
    if q.get("unlimited") or q.get("entitlement") == -1:
        said = f"{name}: unlimited"
    elif q.get("entitlement") is not None:
        said = f"{name}: {q.get('used') or 0:,} of {q['entitlement']:,} used"
        if q.get("remaining") is not None:
            said += f" ({float(q['remaining']):.1f}% left)"
    else:
        said = f"{name}: " + (f"{float(q['remaining']):.1f}% left" if q.get("remaining") is not None else "not said")
    return said + (f", resets {str(q['reset'])[:10]}" if q.get("reset") else "")


def credits(m, usage: Usage) -> float:
    """What an answer cost in AI credits by a model's prices in the table, unrounded (a probe's is tiny)."""
    cached = usage.cached_tokens if m.cached_usd is not None else 0
    uncached = max(usage.input_tokens - cached, 0)
    usd = (uncached * m.input_usd + cached * (m.cached_usd or 0.0) + usage.output_tokens * m.output_usd) / 1_000_000
    return usd / CREDIT_USD


def per_million(price: float, batch: int) -> float:
    """AI credits per batch of tokens as dollars a million tokens."""
    return float(price) / float(batch) * 1_000_000 * CREDIT_USD


def close(a: float, b: float) -> bool:
    """Two prices the same, the server's rounding allowed for."""
    return abs(a - b) <= max(0.005, 0.01 * abs(b))
