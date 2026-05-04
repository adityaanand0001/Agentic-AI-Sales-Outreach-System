"""Browser-based deep exploration — navigate, click, type, paginate, extract."""

from __future__ import annotations

import asyncio
import logging

from playwright.async_api import async_playwright

from app.services.deep_research.schemas import (
    BrowserAction,
    BrowserSequence,
    IdentityResult,
    LeadInput,
    SourceConfig,
    StepResult,
    StepStatus,
)

logger = logging.getLogger(__name__)


async def deep_explore(
    lead: LeadInput,
    identity: IdentityResult,
    sources: SourceConfig | None = None,
    browser_sequences: list[BrowserSequence] | None = None,
) -> StepResult:
    """Run browser sequences to deeply explore company websites."""
    result = StepResult(step_id="deep_dive", step_type="browser_explore")

    if not browser_sequences and identity.domain:
        browser_sequences = _default_sequences(identity.domain)

    if not browser_sequences:
        result.status = StepStatus.SKIPPED
        return result

    import time
    start = time.time()

    extracted = {}
    pages_visited = 0

    try:
        async with async_playwright() as p:
            browser = await p.chromium.launch(headless=True)
            context = await browser.new_context(
                user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
                            "(KHTML, like Gecko) Chrome/125.0.0.0 Safari/537.36"
            )
            page = await context.new_page()

            for seq in browser_sequences:
                try:
                    seq_data = await _run_sequence(page, seq, lead)
                    if seq_data:
                        pages_visited += len(seq.actions)
                        extracted[seq.site_url] = seq_data
                except Exception as e:
                    logger.warning(f"Browser sequence failed for {seq.site_url}: {e}")
                    continue

            await browser.close()

    except Exception as e:
        logger.error(f"Browser exploration failed: {e}")
        result.status = StepStatus.FAILED
        result.error = str(e)
        return result

    result.sources_used = list(extracted.keys())
    result.raw_output = {"pages": list(extracted.keys()), "pages_visited": pages_visited}
    result.status = StepStatus.COMPLETED
    result.duration_ms = (time.time() - start) * 1000
    return result


async def _run_sequence(page, seq: BrowserSequence, lead: LeadInput) -> str:
    """Execute one browser sequence — a list of actions on a site."""
    collected_texts = []

    for action in seq.actions[:10]:  # max 10 actions per sequence for safety
        try:
            if action.action == "navigate":
                await page.goto(action.url or seq.site_url, timeout=15000)

            elif action.action == "scroll_down":
                for _ in range(action.count or 1):
                    await page.evaluate("window.scrollBy(0, window.innerHeight)")
                    await asyncio.sleep(0.5)

            elif action.action == "click":
                if action.selector:
                    try:
                        await page.click(action.selector, timeout=5000)
                        await asyncio.sleep(1)
                    except Exception:
                        pass

            elif action.action == "type":
                if action.selector and action.text:
                    try:
                        await page.fill(action.selector, action.text)
                        await asyncio.sleep(0.5)
                    except Exception:
                        pass

            elif action.action == "paginate":
                max_pages = action.max_pages or 3
                next_sel = action.next_selector or ".pagination a.next, .pagination-next, a[rel=next]"
                for _ in range(max_pages):
                    text = await page.evaluate("document.body.innerText")
                    collected_texts.append(text[:2000])
                    try:
                        btn = page.locator(next_sel).first
                        if await btn.is_visible():
                            await btn.click()
                            await asyncio.sleep(1.5)
                        else:
                            break
                    except Exception:
                        break

            elif action.action == "extract":
                limit = action.limit or 3
                if action.selector:
                    elements = page.locator(action.selector)
                    count = await elements.count()
                    for i in range(min(count, limit)):
                        try:
                            text = await elements.nth(i).inner_text()
                            collected_texts.append(text[:1000])
                        except Exception:
                            continue
                else:
                    text = await page.evaluate("document.body.innerText")
                    collected_texts.append(text[:3000])

            elif action.action == "wait":
                await asyncio.sleep(action.count or 2)

        except Exception:
            continue

    return "\n---\n".join(collected_texts)


def _default_sequences(domain: str) -> list[BrowserSequence]:
    """Generate default browser sequences for company exploration."""
    url = f"https://{domain}"
    return [
        BrowserSequence(
            site_url=url,
            actions=[
                BrowserAction(action="navigate", url=url),
                BrowserAction(action="scroll_down", count=2),
                BrowserAction(action="extract", selector="h1, h2, p"),
            ]
        ),
        BrowserSequence(
            site_url=f"{url}/about",
            actions=[
                BrowserAction(action="navigate", url=f"{url}/about"),
                BrowserAction(action="extract", selector="section, .about-content, p"),
            ]
        ),
        BrowserSequence(
            site_url=f"{url}/blog",
            actions=[
                BrowserAction(action="navigate", url=f"{url}/blog"),
                BrowserAction(action="scroll_down", count=2),
                BrowserAction(action="extract", selector="article h2, article time, article p", limit=5),
            ]
        ),
    ]
