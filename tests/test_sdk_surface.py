"""The Copilot SDK's surface the runtime (runtime.py) relies on, read from the installed SDK where there
is one (CI's sdk job installs the plugin's `sdk` extra; a machine without it skips these): the client's
and the session's options, send_and_wait's timeout, the permission and quota types, the event types.
Read by signature only: nothing is started, nothing sent."""
from __future__ import annotations

import inspect
from pathlib import Path

import pytest

from plugin_platform_copilot.runtime import Ask, client_options, denial, session_options

copilot = pytest.importorskip("copilot", reason="the Copilot SDK is not installed here (the plugin's sdk extra)")


def test_the_client_takes_the_options_given():
    params = inspect.signature(copilot.CopilotClient.__init__).parameters
    given = client_options("github_pat_x", Path("."), {})
    assert set(given) <= set(params), sorted(set(given) - set(params))


def test_a_session_takes_the_options_given_and_waits_with_a_timeout():
    params = inspect.signature(copilot.CopilotClient.create_session).parameters
    given = session_options(Ask("auto", "s", "p", "low"), lambda *a: None, lambda e: None)
    assert set(given) <= set(params), sorted(set(given) - set(params))
    from copilot.session import CopilotSession

    assert "timeout" in inspect.signature(CopilotSession.send_and_wait).parameters


def test_the_permission_and_quota_types_and_the_events_are_there():
    from copilot import SessionEventType
    from copilot import rpc

    assert denial(rpc)(None, None).__class__.__name__ == "PermissionDecisionReject"
    rpc.AccountGetQuotaRequest()
    assert {"assistant.usage", "assistant.message", "session.error"} <= {t.value for t in SessionEventType}
    for name in ("get_auth_status", "list_models", "start", "stop", "force_stop"):
        assert callable(getattr(copilot.CopilotClient, name, None)), name
