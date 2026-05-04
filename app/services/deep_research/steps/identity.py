"""Identity research — WHOIS, MX, maps, social profiles, tech stack."""

from __future__ import annotations

import asyncio
import logging
import re
import socket

import requests
from bs4 import BeautifulSoup

from app.services.deep_research.schemas import IdentityResult, LeadInput, SourceConfig, StepResult, StepStatus

logger = logging.getLogger(__name__)

HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
                   "(KHTML, like Gecko) Chrome/125.0.0.0 Safari/537.36"
}


async def research_identity(lead: LeadInput, sources: SourceConfig | None = None) -> StepResult:
    """Gather company identity: domain, tech, location, social presence."""
    sources = sources or SourceConfig()
    result = StepResult(step_id="identify", step_type="identity_research")
    identity = IdentityResult(company_name=lead.name, industry=lead.sector, size=lead.size)

    import time
    start = time.time()

    domain = _find_domain_from_name(lead.name)

    tasks = []
    if sources.whois_lookup and domain:
        tasks.append(_whois_lookup(domain))
    else:
        tasks.append(asyncio.sleep(0))

    if sources.google_maps:
        tasks.append(_maps_lookup(lead.name))
    else:
        tasks.append(asyncio.sleep(0))

    if sources.social_scan:
        tasks.append(_social_scan(lead.name))
    else:
        tasks.append(asyncio.sleep(0))

    if sources.builtwith and domain:
        tasks.append(_tech_lookup(domain))
    else:
        tasks.append(asyncio.sleep(0))

    if sources.crunchbase:
        tasks.append(_crunchbase_lookup(lead.name))
    else:
        tasks.append(asyncio.sleep(0))

    whois, maps, social, tech, crunchbase = await asyncio.gather(*tasks)

    # Assemble
    if domain:
        identity.domain = domain
        result.sources_used.append("domain")

    if whois and isinstance(whois, dict):
        identity.domain_age = whois.get("created", "")
        identity.email_provider = whois.get("mx_provider", "")
        if identity.domain_age:
            result.sources_used.append("whois")
        if identity.email_provider:
            result.sources_used.append("mx")

    if maps and isinstance(maps, dict):
        identity.location = maps.get("location", "")
        identity.rating = maps.get("rating", "")
        identity.review_count = maps.get("reviews", 0)
        identity.description = maps.get("description", "")
        if identity.location:
            result.sources_used.append("google_maps")

    if social and isinstance(social, dict):
        identity.social_profiles = social
        if social:
            result.sources_used.append("social")

    if tech and isinstance(tech, list):
        identity.tech_stack = tech
        if tech:
            result.sources_used.append("builtwith")

    if crunchbase and isinstance(crunchbase, dict):
        identity.crunchbase_url = crunchbase.get("url", "")
        identity.funding_summary = crunchbase.get("funding", "")
        if identity.crunchbase_url:
            result.sources_used.append("crunchbase")

    result.raw_output = identity.model_dump()
    result.status = StepStatus.COMPLETED
    result.duration_ms = (time.time() - start) * 1000
    return result


def _find_domain_from_name(company_name: str) -> str:
    slug = re.sub(r"[^a-z0-9]", "", company_name.lower().replace(" ", ""))
    return f"{slug}.com" if len(slug) > 3 else ""


async def _whois_lookup(domain: str) -> dict:
    """Basic WHOIS + MX lookup."""
    info = {}
    try:
        import subprocess
        output = subprocess.check_output(["whois", domain], timeout=10, text=True, stderr=subprocess.DEVNULL)
        for line in output.split("\n"):
            line_lower = line.lower()
            if "creation date" in line_lower or "created" in line_lower:
                info["created"] = line.split(":", 1)[-1].strip()[:10]
                break
    except Exception:
        pass

    try:
        import dns.resolver
        answers = dns.resolver.resolve(domain, "MX")
        mx = str(answers[0].exchange).lower()
        if "google" in mx:
            info["mx_provider"] = "Google Workspace"
        elif "outlook" in mx or "microsoft" in mx:
            info["mx_provider"] = "Microsoft 365"
        elif "zoho" in mx:
            info["mx_provider"] = "Zoho"
        else:
            info["mx_provider"] = mx
    except Exception:
        info["mx_provider"] = "unknown"

    return info


async def _maps_lookup(company_name: str) -> dict:
    """Scrape Google Maps for location, rating."""
    try:
        query = requests.utils.quote(f"{company_name}")
        url = f"https://www.google.com/search?q={query}"
        resp = requests.get(url, headers=HEADERS, timeout=10)

        if resp.status_code == 200:
            text = resp.text
            info = {}

            rating_match = re.search(r"(\d+\.?\d*)\s*★", text)
            if rating_match:
                info["rating"] = f"{rating_match.group(1)}★"

            reviews_match = re.search(r"(\d[\d,]*)\s*reviews?", text)
            if reviews_match:
                info["reviews"] = int(reviews_match.group(1).replace(",", ""))

            addr_match = re.search(r'"address"[^"]*"([^"]+)"', text, re.IGNORECASE)
            if not addr_match:
                addr_match = re.search(r"(\d+\s+[A-Z][a-z]+.*?,\s*[A-Z]{2}\s+\d{5})", text)
            if addr_match:
                info["location"] = addr_match.group(1)

            desc_match = re.search(r'<meta[^>]*description[^>]*content="([^"]+)"', text.strip()[:2000], re.IGNORECASE)
            if desc_match:
                info["description"] = desc_match.group(1)[:300]

            return info
    except Exception:
        pass
    return {}


async def _social_scan(company_name: str) -> dict:
    """Find social profile URLs."""
    profiles = {}
    platforms = ["instagram.com", "twitter.com", "facebook.com", "linkedin.com/company"]

    query = requests.utils.quote(company_name)
    url = f"https://www.google.com/search?q={query}"
    try:
        resp = requests.get(url, headers=HEADERS, timeout=10)
        if resp.status_code == 200:
            for platform in platforms:
                match = re.search(rf"(https?://[^\s&]*{platform}/[^\s&\"'<>]*)", resp.text)
                if match:
                    profiles[platform.split(".")[0]] = match.group(1).rstrip("/")
    except Exception:
        pass
    return profiles


async def _tech_lookup(domain: str) -> list:
    """Scrape homepage for tech stack signals."""
    tech = []
    try:
        resp = requests.get(f"https://{domain}", headers=HEADERS, timeout=8)
        if resp.status_code == 200:
            soup = BeautifulSoup(resp.text, "html.parser")
            for script in soup.find_all("script", src=True):
                src = script["src"].lower()
                for signal, name in {
                    "shopify": "Shopify", "woocommerce": "WooCommerce", "stripe": "Stripe",
                    "squarespace": "Squarespace", "wix": "Wix", "webflow": "Webflow",
                    "react": "React", "vue": "Vue.js", "angular": "Angular",
                    "google-analytics": "Google Analytics", "gtag": "Google Tag Manager",
                    "hubspot": "HubSpot", "salesforce": "Salesforce", "zendesk": "Zendesk",
                    "intercom": "Intercom", "drift": "Drift", "hotjar": "Hotjar",
                    "segment": "Segment", "mixpanel": "Mixpanel", "amplitude": "Amplitude",
                }.items():
                    if signal in src and name not in tech:
                        tech.append(name)
    except Exception:
        pass
    return tech


async def _crunchbase_lookup(company_name: str) -> dict:
    """Try to find Crunchbase profile."""
    try:
        slug = re.sub(r"[^a-z0-9-]", "", company_name.lower().replace(" ", "-").strip("-"))
        query = requests.utils.quote(f"crunchbase.com {company_name}")
        url = f"https://www.google.com/search?q={query}"
        resp = requests.get(url, headers=HEADERS, timeout=10)
        if resp.status_code == 200:
            match = re.search(r"(https?://www\.crunchbase\.com/organization/[^\s&\"'<>]+)", resp.text)
            if match:
                return {"url": match.group(1)}
    except Exception:
        pass
    return {}
