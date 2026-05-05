"""Personalised email generation using LLM."""

from __future__ import annotations

import json
import logging
from datetime import datetime, timezone

from openai import OpenAI

from app.config.settings import get_settings

logger = logging.getLogger(__name__)


class EmailGeneratorService:
    """Generates personalised email content from company context using LLM (OpenAI or Gemini)."""

    def __init__(self) -> None:
        self.settings = get_settings()
        self._setup_client()

    def _setup_client(self):
        """Initialize the appropriate LLM client."""
        if self.settings.llm_provider == "openai":
            from openai import OpenAI
            self.client = OpenAI(api_key=self.settings.openai_api_key)
        else:
            import google.generativeai as genai
            import urllib3
            import os
            
            if not self.settings.verify_ssl:
                urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)
                # Note: For Gemini, we still set env vars as it might not use httpx
                os.environ["CURL_CA_BUNDLE"] = ""
                os.environ["REQUESTS_CA_BUNDLE"] = ""
                os.environ["SSL_CERT_FILE"] = ""
            
            genai.configure(api_key=self.settings.google_api_key)
            self.client = genai.GenerativeModel(self.settings.llm_model)

    def generate(
        self,
        company_name: str,
        context: str,
        recipient_email: str,
    ) -> dict:
        """
        Generate a personalised email based on company context.

        Returns {"subject": str, "body_text": str, "body_html": str}
        """
        prompt = self._build_prompt(company_name, context)

        if self.settings.llm_provider == "openai":
            return self._generate_openai(prompt)
        else:
            return self._generate_gemini(prompt)

    def _generate_openai(self, prompt: str) -> dict:
        """Generate using OpenAI."""
        response = self.client.chat.completions.create(
            model=self.settings.llm_model,
            messages=[
                {
                    "role": "system",
                    "content": (
                        "You are a professional B2B outreach email writer. "
                        "Write concise, personalised emails. Output JSON with keys: "
                        "subject, body_text, body_html."
                    ),
                },
                {"role": "user", "content": prompt},
            ],
            response_format={"type": "json_object"},
            temperature=0.7,
        )
        raw = response.choices[0].message.content or "{}"
        parsed = json.loads(raw)
        return self._format_response(parsed)

    def _generate_gemini(self, prompt: str) -> dict:
        """Generate using Google Gemini."""
        # Add system instruction for Gemini
        system_instruction = (
            "You are a professional B2B outreach email writer. "
            "Write concise, personalised emails. Output ONLY a valid JSON object "
            "with these exact keys: subject, body_text, body_html."
        )
        
        full_prompt = f"{system_instruction}\n\nUser Request: {prompt}"
        
        response = self.client.generate_content(
            full_prompt,
            generation_config={"response_mime_type": "application/json"}
        )
        
        try:
            raw = response.text or "{}"
            parsed = json.loads(raw)
        except Exception as e:
            logger.error(f"Failed to parse Gemini response: {e}")
            parsed = {"subject": "Reaching out", "body_text": response.text}
            
        return self._format_response(parsed)

    def prioritize(self, company_name: str, context: str) -> float:
        """
        Score a lead's potential from 0 to 1 based on context quality and business intent.
        Uses high-granularity analysis to ensure unique rankings.
        """
        prompt = f"""
        Evaluate the business potential and outreach relevance for this company.
        
        COMPANY: {company_name}
        CONTEXT: {context}
        
        TASK:
        Provide a 'High Precision Score' from 0.00 to 1.00.
        0.00 - 0.30: Irrelevant, generic, or low-value.
        0.31 - 0.60: Relevant but standard opportunity.
        0.61 - 0.85: High-value opportunity with specific pain points.
        0.86 - 1.00: Perfect match, urgent need, clear high-intent hook.
        
        Consider:
        1. Industry niche (is it a high-growth or specialized sector?)
        2. Pain point specificity (does the context mention a concrete problem?)
        3. Scalability (could our services provide a massive ROI here?)
        
        Output ONLY a JSON object: {{"score": float, "reasoning": "brief 1-sentence explanation"}}
        """

        try:
            if self.settings.llm_provider == "openai":
                response = self.client.chat.completions.create(
                    model=self.settings.llm_model,
                    messages=[
                        {"role": "system", "content": "You are a senior sales architect. You provide highly granular lead scores based on semantic intent analysis."},
                        {"role": "user", "content": prompt},
                    ],
                    response_format={"type": "json_object"},
                    temperature=0.2, # Lower temp for consistency but prompt forces variation
                )
                raw = response.choices[0].message.content or "{}"
            else:
                response = self.client.generate_content(
                    f"You are a senior sales architect. Output ONLY valid JSON.\n\n{prompt}",
                    generation_config={"response_mime_type": "application/json"}
                )
                raw = response.text or "{}"
            
            parsed = json.loads(raw)
            score = float(parsed.get("score", 0.5))
            
            # Add a tiny bit of deterministic 'jitter' based on context length to break ties
            jitter = (len(context) % 100) / 1000.0  # +0.000 to +0.099
            return min(1.0, score + jitter)
            
        except Exception as e:
            logger.error(f"AI Prioritization failed: {e}")
            return 0.5

    def _format_response(self, parsed: dict) -> dict:
        """Standardize the response format."""
        return {
            "subject": parsed.get("subject", "Reaching out"),
            "body_text": parsed.get("body_text", ""),
            "body_html": parsed.get(
                "body_html",
                f"<p>{parsed.get('body_text', '')}</p>",
            ),
            "generated_at": datetime.now(timezone.utc).isoformat(),
            "model_used": self.settings.llm_model,
        }

    def regenerate(
        self,
        company_name: str,
        context: str,
        recipient_email: str,
        feedback: str,
        prev_subject: str = "",
        prev_body: str = "",
    ) -> dict:
        """
        Regenerate an email based on user feedback and the previous draft.
        """
        prompt = f"""
Previous Subject: {prev_subject}
Previous Body: {prev_body}

User Feedback: {feedback}

Company Name: {company_name}
Company Context: {context}

Please regenerate the outreach email for {company_name} incorporating the user's feedback.
Follow the same rules: concise, professional, and reference the company's context.
"""

        if self.settings.llm_provider == "openai":
            return self._generate_openai(prompt)
        else:
            return self._generate_gemini(prompt)

    def follow_up(
        self,
        company_name: str,
        context: str,
        recipient_email: str,
        previous_subject: str = "",
        follow_up_number: int = 1,
    ) -> dict:
        """
        Generate a follow-up email for a lead that hasn't replied yet.

        The prompt references the previous outreach to maintain thread continuity
        and escalates urgency naturally with each follow-up number.
        """
        urgency_hooks = {
            1: "a gentle, friendly nudge — assume they were busy",
            2: "a slightly more direct follow-up — reference the previous email and add a new angle",
            3: "a final re-engagement attempt — acknowledge it may not be the right time, leave the door open",
        }
        tone = urgency_hooks.get(follow_up_number, urgency_hooks[3])

        prompt = f"""
This is follow-up #{follow_up_number} for {company_name}.

Previous Email Subject: {previous_subject}

Company: {company_name}
Context: {context}

TONE: {tone}

Write a concise follow-up email from Klyro to {company_name}.
- Reference the previous outreach naturally (don't just repeat it)
- Add a new value proposition or angle
- Keep it under 120 words
- End with a soft call to action
"""

        if self.settings.llm_provider == "openai":
            return self._generate_openai(prompt)
        else:
            return self._generate_gemini(prompt)

    @staticmethod
    def _build_prompt(company_name: str, context: str) -> str:
        return f"""
Company Name: {company_name}
Company Context: {context}

Write a professional outreach email from Klyro to {company_name}.
The email should:
- Reference the company's specific context to show research
- Explain how Klyro's services can help
- Be concise (max 150 words)
- End with a soft call to action
"""
