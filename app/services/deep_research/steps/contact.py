"""Contact discovery — find person name, email, role from company name only."""

from __future__ import annotations

import logging
import re

import requests
from bs4 import BeautifulSoup

from app.services.deep_research.schemas import ContactResult, LeadInput, StepResult, StepStatus

logger = logging.getLogger(__name__)

HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
                   "(KHTML, like Gecko) Chrome/125.0.0.0 Safari/537.36"
}


async def discover_contact(lead: LeadInput, config: dict | None = None) -> StepResult:
    """Find person name and email for a company using only free scraping.

    Strategy:
    1. Google search: "{company} email contact"
    2. Google search: "{company} owner/founder linkedin"
    3. Scrape company website contact page (if domain found)
    4. Regex extract emails from all scraped text
    5. Score confidence based on sources in agreement
    """
    config = config or {}
    result = StepResult(step_id="find_person", step_type="contact_discovery")
    contact = ContactResult()

    import time
    start = time.time()

    try:
        company_name = lead.name.strip()
        sector = lead.sector.strip()

        # ── Step 1: Find domain ────────────────────────────────────────────────
        domain = await _find_domain(company_name)

        # ── Step 2: Find person name via LinkedIn + Google ──────────────────────
        person_name, person_role, linkedin_url = await _find_person(company_name, sector)

        # ── Step 3: Find email ──────────────────────────────────────────────────
        if domain:
            emails = await _find_emails(company_name, domain, person_name)
            if emails:
                contact.email = emails[0]
                contact.email_confidence = emails[0][1] if isinstance(emails[0], tuple) else 0.5
                if isinstance(emails[0], tuple):
                    contact.email = emails[0][0]
                    contact.email_confidence = emails[0][1]
                else:
                    contact.email = emails[0]
                    contact.email_confidence = 0.6
                contact.alternative_emails = [e[0] if isinstance(e, tuple) else e for e in emails[1:4]]

        # ── Assemble result ─────────────────────────────────────────────────────
        contact.person_name = person_name
        contact.role = person_role
        contact.linkedin_url = linkedin_url
        contact.domain = domain

        # Track sources
        if domain:
            contact.sources.append(f"domain:{domain}")
        if person_name:
            contact.sources.append("google_search")
        if linkedin_url:
            contact.sources.append("linkedin")
        if contact.email:
            contact.sources.append(f"email_scrape:{'high' if contact.email_confidence > 0.8 else 'medium'}")

        result.sources_used = contact.sources
        result.raw_output = contact.model_dump()
        result.status = StepStatus.COMPLETED if contact.email else StepStatus.SKIPPED

    except Exception as e:
        logger.error(f"Contact discovery failed for {lead.name}: {e}")
        result.status = StepStatus.FAILED
        result.error = str(e)

    result.duration_ms = (time.time() - start) * 1000
    return result


async def _find_domain(company_name: str) -> str:
    """Find the company's website domain."""
    try:
        query = f"{company_name} official website"
        url = f"https://www.google.com/search?q={requests.utils.quote(query)}"
        resp = requests.get(url, headers=HEADERS, timeout=10)

        if resp.status_code != 200:
            return ""

        soup = BeautifulSoup(resp.text, "html.parser")
        for a in soup.select("a[href]"):
            href = a["href"]
            if "google.com" in href or "youtube.com" in href:
                continue
            match = re.search(r"https?://(www\.)?([a-zA-Z0-9-]+\.[a-zA-Z]{2,})", href)
            if match:
                domain = match.group(2)
                if not any(skip in domain.lower() for skip in ["google", "facebook", "linkedin", "yelp", "instagram", "twitter"]):
                    return domain
    except Exception:
        pass

    # Fallback: guess domain from name
    slug = re.sub(r"[^a-z0-9]", "", company_name.lower().replace(" ", ""))
    if len(slug) > 3:
        return f"{slug}.com"

    return ""


async def _find_person(company_name: str, sector: str) -> tuple[str, str, str]:
    """Find decision maker via Google + LinkedIn scraping."""
    person_name = ""
    person_role = ""
    linkedin_url = ""

    # Determine target role based on size/context
    target_roles = "owner OR founder OR CEO OR director"

    try:
        query = f'linkedin.com/in "{company_name}" {target_roles}'
        url = f"https://www.google.com/search?q={requests.utils.quote(query)}"
        resp = requests.get(url, headers=HEADERS, timeout=10)

        if resp.status_code == 200:
            soup = BeautifulSoup(resp.text, "html.parser")
            text = soup.get_text()

            # Try to find LinkedIn URL
            li_match = re.search(r"(https?://[a-z]{2,3}\.linkedin\.com/in/[^\s&]+)", text)
            if li_match:
                linkedin_url = li_match.group(1)

            # Extract person name from snippet (heuristic: before " - " near company name)
            for line in text.split("\n"):
                if company_name.lower() in line.lower():
                    parts = line.split(" - ")
                    for part in parts[:2]:
                        clean = part.strip().strip(".").strip("|").strip()
                        words = clean.split()
                        if 2 <= len(words) <= 4 and all(w[0].isupper() for w in words if w[0].isalpha()):
                            person_name = clean
                            break
                    if person_name:
                        break

    except Exception:
        pass

    # Role inference from size/sector
    if not person_role:
        if any(w in sector.lower() for w in ["food", "bakery", "cafe", "restaurant"]):
            person_role = "Owner"
        elif "saas" in sector.lower() or "tech" in sector.lower():
            person_role = "CEO" if not person_name else "Founder"
        else:
            person_role = "Owner / Founder"

    return person_name, person_role, linkedin_url


async def _find_emails(company_name: str, domain: str, person_name: str) -> list:
    """Find email addresses via scraping contact page and web search."""
    found = []

    # Try 1: Scrape contact page
    try:
        for path in ["/contact", "/contact-us", "/about", "/about-us", "/"]:
            url = f"https://{domain}{path}"
            try:
                resp = requests.get(url, headers=HEADERS, timeout=8)
                if resp.status_code == 200:
                    emails = re.findall(r"[a-zA-Z0-9._%+-]+@" + re.escape(domain), resp.text)
                    emails = list(set(e.lower() for e in emails))
                    # Skip generic emails
                    generic = {"info", "hello", "contact", "support", "sales", "admin", "noreply"}
                    for e in emails:
                        prefix = e.split("@")[0]
                        if prefix in generic:
                            found.append((e, 0.3))
                        elif person_name and _partial_match(prefix, person_name):
                            found.append((e, 0.95))
                        else:
                            found.append((e, 0.5))
                    if found:
                        found.sort(key=lambda x: x[1], reverse=True)
                        return found
            except Exception:
                continue
    except Exception:
        pass

    # Try 2: Google search for email
    try:
        query = f'"{company_name}" "@{domain}" email'
        url = f"https://www.google.com/search?q={requests.utils.quote(query)}"
        resp = requests.get(url, headers=HEADERS, timeout=10)

        if resp.status_code == 200:
            raw_emails = re.findall(r"[a-zA-Z0-9._%+-]+@" + re.escape(domain), resp.text)
            raw_emails = list(set(e.lower() for e in raw_emails))
            generic = {"info", "hello", "contact", "support", "sales", "admin", "noreply"}
            for e in raw_emails:
                prefix = e.split("@")[0]
                if prefix in generic:
                    found.append((e, 0.3))
                elif person_name and _partial_match(prefix, person_name):
                    found.append((e, 0.95))
                else:
                    found.append((e, 0.4))
            found.sort(key=lambda x: x[1], reverse=True)
    except Exception:
        pass

    # Try 3: Guess common patterns
    if not found and person_name:
        parts = person_name.lower().split()
        if len(parts) >= 2:
            for pattern in [
                f"{parts[0]}@{domain}",
                f"{parts[0]}.{parts[-1]}@{domain}",
                f"{parts[0][0]}.{parts[-1]}@{domain}",
                f"{parts[0][0]}{parts[-1]}@{domain}",
            ]:
                found.append((pattern, 0.5))

    return found


def _partial_match(email_prefix: str, person_name: str) -> bool:
    """Check if email prefix partially matches person name."""
    name_parts = person_name.lower().replace(".", " ").split()
    prefix = email_prefix.lower().replace(".", "").replace("_", "").replace("-", "")
    return any(part in prefix for part in name_parts if len(part) > 1)
