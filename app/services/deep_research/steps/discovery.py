"""Signal discovery — news, reviews, social activity, sector trends, competitors."""

from __future__ import annotations

import asyncio
import logging
import re

import requests
from bs4 import BeautifulSoup

from app.services.deep_research.schemas import (
    IdentityResult,
    LeadInput,
    SignalItem,
    SourceConfig,
    StepResult,
    StepStatus,
)

logger = logging.getLogger(__name__)

HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
                   "(KHTML, like Gecko) Chrome/125.0.0.0 Safari/537.36"
}


async def discover_signals(
    lead: LeadInput,
    identity: IdentityResult,
    sources: SourceConfig | None = None,
) -> StepResult:
    """Find signals: news, awards, reviews, jobs, social activity, industry trends."""
    sources = sources or SourceConfig()
    result = StepResult(step_id="discover", step_type="signal_discovery")
    signals: list[SignalItem] = []

    import time
    start = time.time()

    company = lead.name
    sector = lead.sector
    location = identity.location or ""
    domain = identity.domain or ""

    tasks = []

    # Google Web search (always useful)
    tasks.append(_search_signals(company, sector, location))

    # Google News
    if sources.google_news:
        tasks.append(_search_news(company, sector))

    # Industry trends
    if sector:
        tasks.append(_search_industry_trends(sector, location))

    results = await asyncio.gather(*tasks)

    for signal_list in results:
        if isinstance(signal_list, list):
            signals.extend(signal_list)

    # Deduplicate by detail text similarity
    seen = set()
    unique = []
    for s in signals:
        key = s.detail[:80].lower().strip()
        if key not in seen:
            seen.add(key)
            unique.append(s)
    signals = unique

    result.sources_used = list(set(s.source for s in signals))
    result.raw_output = {"signals": [s.model_dump() for s in signals], "count": len(signals)}
    result.status = StepStatus.COMPLETED
    result.duration_ms = (time.time() - start) * 1000
    return result


async def _search_signals(company: str, sector: str, location: str) -> list[SignalItem]:
    """Scrape Google SERP for broad signals."""
    signals = []
    queries = [
        f'"{company}" award OR won OR best',
        f'"{company}" launches OR announces OR releases',
        f'"{company}" review OR reviews complaint',
        f'"{company}" hiring OR jobs OR careers',
    ]

    for query in queries:
        try:
            url = f"https://www.google.com/search?q={requests.utils.quote(query)}"
            resp = requests.get(url, headers=HEADERS, timeout=10)
            if resp.status_code != 200:
                continue

            soup = BeautifulSoup(resp.text, "html.parser")
            text = soup.get_text()[:2000]

            # Extract snippets
            for snippet_div in soup.select(".VwiC3b, .st"):
                snippet = snippet_div.get_text()[:500]
                if company.lower() in snippet.lower():
                    signal_type = _classify_signal(snippet, query)
                    signals.append(SignalItem(
                        signal_type=signal_type,
                        source="google_web",
                        detail=snippet[:300],
                    ))
        except Exception:
            continue

    # Competitor check
    if sector:
        try:
            q = f"{sector} similar to {company} OR competitor OR alternative"
            url = f"https://www.google.com/search?q={requests.utils.quote(q)}"
            resp = requests.get(url, headers=HEADERS, timeout=10)
            if resp.status_code == 200:
                text = resp.text
                # Try to extract competitor names
                for match in re.finditer(rf"(?<!{re.escape(company)})([A-Z][a-z]+(?:\s[A-Z][a-z]+)*)\s", text):
                    name = match.group(1).strip()
                    if len(name) > 5 and name.lower() not in company.lower():
                        signals.append(SignalItem(
                            signal_type="competitor",
                            source="google_web",
                            detail=f"Competitor detected: {name}",
                        ))
                        break
        except Exception:
            pass

    return signals


async def _search_news(company: str, sector: str) -> list[SignalItem]:
    """Scrape Google News for recent mentions."""
    signals = []
    try:
        query = requests.utils.quote(f'"{company}"')
        url = f"https://news.google.com/search?q={query}&hl=en-US"
        resp = requests.get(url, headers=HEADERS, timeout=10)
        if resp.status_code != 200:
            return signals

        soup = BeautifulSoup(resp.text, "html.parser")
        for article in soup.select("article")[:5]:
            headline = article.get_text()[:200]
            if company.lower() in headline.lower():
                signal_type = _classify_signal(headline, "news")
                signals.append(SignalItem(
                    signal_type=signal_type,
                    source="google_news",
                    detail=headline[:300],
                ))

        if not signals:
            # Fallback to web search for news
            web_url = f"https://www.google.com/search?q={requests.utils.quote(company)}+news&tbm=nws"
            web_resp = requests.get(web_url, headers=HEADERS, timeout=10)
            if web_resp.status_code == 200:
                web_soup = BeautifulSoup(web_resp.text, "html.parser")
                for snippet in web_soup.select(".VwiC3b")[:5]:
                    text = snippet.get_text()[:300]
                    if company.lower() in text.lower():
                        signal_type = _classify_signal(text, "news")
                        signals.append(SignalItem(
                            signal_type=signal_type,
                            source="google_news",
                            detail=text,
                        ))
    except Exception:
        pass
    return signals


async def _search_industry_trends(sector: str, location: str) -> list[SignalItem]:
    """Search industry trends, market data relevant to the lead's sector."""
    signals = []

    queries = [
        f"{sector} market size 2025",
        f"{sector} trends challenges 2025",
        f"{sector} digital transformation",
    ]

    if location:
        queries.append(f"{sector} {location} regulations 2025")
        queries.append(f"{sector} {location} growth")

    for query in queries:
        try:
            url = f"https://www.google.com/search?q={requests.utils.quote(query)}"
            resp = requests.get(url, headers=HEADERS, timeout=10)
            if resp.status_code != 200:
                continue

            soup = BeautifulSoup(resp.text, "html.parser")
            # Featured snippet
            snippet_div = soup.select_one(".VwiC3b, .IZ6rdc, .LGOjhe")
            if snippet_div:
                text = snippet_div.get_text()[:400]
                signals.append(SignalItem(
                    signal_type="industry",
                    source="google_web",
                    detail=text,
                    relevance="Provides market context for outreach positioning",
                ))
        except Exception:
            continue

    return signals


def _classify_signal(text: str, source_hint: str) -> str:
    """Classify a signal based on keyword matching."""
    lower = text.lower()

    if any(w in lower for w in ["award", "won", "best", "top", "recognized", "ranked", "rated"]):
        return "award"
    if any(w in lower for w in ["funding", "raised", "series", "investor", "valuation", "round"]):
        return "growth"
    if any(w in lower for w in ["launch", "announces", "releases", "unveiled", "introduces", "new"]):
        return "launch"
    if any(w in lower for w in ["hiring", "job", "career", "opening", "position"]):
        return "growth"
    if any(w in lower for w in ["complaint", "review", "bad", "terrible", "disappointed", "issue", "problem"]):
        return "pain"
    if any(w in lower for w in ["competitor", "vs", "alternative", "rival"]):
        return "competitor"
    if any(w in lower for w in ["regulation", "law", "compliance", "legal", "government", "rule"]):
        return "regulation"
    if any(w in lower for w in ["market", "industry", "trend", "growth", "billion", "million"]):
        return "industry"

    return "general"
