"""The weekly check (CI's schedule, LIMINAL_VENDOR_PAGES=1): GitHub's public pages read again, each
written-in figure looked for (verify.check_sources); and, from the pages served as markdown, every
model's prices, every model's plans, its place in the Copilot CLI (the SDK's runtime) and every plan's
allowance compared with the tables row by row. A figure gone or changed means the table is stale and
the plugin needs a release; the failure names the model or the plan. And every address on the plugin's
cards (apis.py) asked once. Nothing is read on a push or a pull request."""
from __future__ import annotations

import os
import re

import pytest

from liminal_libs.assistants.verify import USER_AGENT, check_sources
from plugin_platform_copilot import ASSISTANT, AUTO, INDIVIDUAL, MODELS, MODELS_PAGE, ORGANIZATION, PLANS_PAGE, PRICING

pytestmark = pytest.mark.skipif(not os.environ.get("LIMINAL_VENDOR_PAGES"),
                                reason="LIMINAL_VENDOR_PAGES=1 reads the vendor's pages (the weekly CI run)")

COLUMNS = {"Copilot Pro": "pro", "Copilot Pro+": "pro-plus", "Copilot Max": "max", "Copilot Business": "business",
           "Copilot Enterprise": "enterprise"}  # the models-by-plan table's columns, as the plans are named here


def markdown(url: str) -> list[str]:
    """A docs page's lines as GitHub serves them to a reader asking for markdown."""
    import requests

    resp = requests.get(url, headers={"User-Agent": USER_AGENT, "Accept": "text/markdown"}, timeout=30)
    assert resp.status_code < 400, f"{url}: HTTP {resp.status_code}"
    assert "markdown" in resp.headers.get("Content-Type", ""), f"{url}: no longer served as markdown: read its tables by hand"
    return resp.text.splitlines()


def cell(text: str) -> str:
    """A table cell's words: an icon as its label (Included), footnote marks and tags dropped."""
    label = re.search(r'aria-label="([^"]+)"', text)
    if label:
        return label.group(1)
    return re.sub(r"\s+", " ", re.sub(r"\[\^[^\]]+\]", "", re.sub(r"<[^>]+>", " ", text))).strip()


def rows(lines: list[str], heading: str | None = None) -> list[list[str]]:
    """A page's table rows (the header among them), under `heading` only when it is given."""
    out, inside = [], heading is None
    for line in lines:
        if line.startswith("#"):
            inside = heading is None or line.lstrip("#").strip() == heading
            continue
        if not inside or not line.startswith("|") or set(line.strip()) <= set("|-: "):
            continue
        cells = [cell(c) for c in line.strip().strip("|").split("|")]
        if any(cells):
            out.append(cells)
    return out


def test_the_tables_still_match_githubs_pages():
    problems = check_sources(ASSISTANT)
    assert problems == [], "\n".join(problems)


def test_every_models_prices_are_still_the_pricing_pages():
    found: dict[str, list[str]] = {}
    for r in rows(markdown(PRICING)):
        if r[0] and r[0] not in found and "Long context" not in r:  # the default tier's row
            found[r[0]] = r
    wrong = []
    for m in MODELS:
        if m.id == AUTO:
            continue
        r = found.get(m.title)
        if r is None:
            wrong.append(f"{m.title} ({m.id}): no longer on the pricing page")
            continue
        amounts = [float(a.replace(",", "")) for a in re.findall(r"\$([\d,]+(?:\.\d+)?)", " ".join(r))]
        page = (amounts[0], amounts[1], amounts[-1]) if len(amounts) >= 3 else tuple(amounts)
        if page != (m.input_usd, m.cached_usd, m.output_usd):
            wrong.append(f"{m.title} ({m.id}): the page's {page} (input, cached input, output a million tokens), the "
                         f"table's {(m.input_usd, m.cached_usd, m.output_usd)}")
    assert wrong == [], "the table is stale:\n" + "\n".join(wrong)


def test_every_models_plans_are_still_the_models_pages():
    table = rows(markdown(MODELS_PAGE), heading="Supported AI models per Copilot plan")
    assert table, "the models-by-plan table is gone from the models page"
    header, body = table[0], {r[0]: r for r in table[1:]}
    columns = {i: COLUMNS[h] for i, h in enumerate(header) if h in COLUMNS}
    assert sorted(columns.values()) == sorted(COLUMNS.values()), f"the table's plans changed: {header}"
    wrong = []
    for m in MODELS:
        if m.id == AUTO:
            continue
        r = body.get(m.title)
        if r is None:
            wrong.append(f"{m.title} ({m.id}): no longer in the models-by-plan table")
            continue
        for i, plan in columns.items():
            page, mine = r[i] == "Included", ASSISTANT.allows(ASSISTANT.plan_of(plan), m.id)
            if page != mine:
                wrong.append(f"{m.title} ({m.id}) on {plan}: the page says {r[i]!r}, the table "
                             f"{'reaches it' if mine else 'does not'}")
    assert wrong == [], "the table is stale:\n" + "\n".join(wrong)


def test_every_model_is_still_in_the_copilot_cli():
    table = rows(markdown(MODELS_PAGE), heading="Supported AI models per client")
    assert table and "Copilot CLI" in table[0], "the models-by-client table changed"
    at = table[0].index("Copilot CLI")
    body = {r[0]: r for r in table[1:]}
    wrong = [f"{m.title} ({m.id}): {body[m.title][at]!r} in the Copilot CLI, the SDK's runtime" for m in MODELS
             if m.title in body and body[m.title][at] != "Included"]
    assert wrong == [], "the table is stale:\n" + "\n".join(wrong)


def test_every_plans_allowance_is_still_the_plans_pages():
    table = [r[:5] for r in rows(markdown(PLANS_PAGE))]
    wrong = []
    for name, (usd, base, flex, total) in INDIVIDUAL.items():
        title = ASSISTANT.plan_of(name).title
        want = [title, f"${usd} USD", f"{base:,}", f"{flex:,}", f"{total:,}"]
        if want not in table:
            wrong.append(f"{title}: the page's rows {[r for r in table if r[0] == title]}, the table's {want[1:]}")
    for name, (usd, credits) in ORGANIZATION.items():
        title = ASSISTANT.plan_of(name).title
        want = [title, f"${usd} USD", f"{credits:,}"]
        if want not in [r[:3] for r in table]:
            wrong.append(f"{title}: the page's rows {[r for r in table if r[0] == title]}, the table's {want[1:]}")
    assert wrong == [], "the table is stale:\n" + "\n".join(wrong)


def test_every_address_on_the_cards_answers():
    """Each address on the cards asked once (sources.apis.dead_links)."""
    from liminal_libs.sources.apis import dead_links
    from plugin_platform_copilot.apis import APIS

    assert dead_links(APIS) == []
