"""Thin wrapper around the official Google Gen AI SDK (``google-genai``).

All Gemini traffic goes through this class so that:
  * the model name lives in one place (GEMINI_MODEL),
  * every call requests structured JSON validated against a schema,
  * failures surface as ``AIUnavailable`` with an honest reason — the caller never
    substitutes canned text and presents it as a Gemini response.
"""
import json
import logging
import time

from flask import current_app

log = logging.getLogger(__name__)


class AIUnavailable(Exception):
    """reason: not_configured | quota | provider_error | timeout | invalid_output | blocked"""

    def __init__(self, reason, message):
        super().__init__(message)
        self.reason = reason
        self.message = message


USER_MESSAGES = {
    "not_configured": "The AI assistant isn't configured on this server yet (missing GEMINI_API_KEY).",
    "quota": "The AI service has reached its usage limit for now. Please try again later.",
    "provider_error": "The AI service is temporarily unavailable. Please try again in a moment.",
    "timeout": "The AI service took too long to respond. Please try again.",
    "invalid_output": "The AI returned a response we couldn't safely use, so it was discarded.",
    "blocked": "The AI service declined to answer this message.",
}


class GeminiService:
    # Gemini "thinking" tokens count against max_output_tokens; this headroom keeps the JSON answer from
    # being truncated (finish_reason MAX_TOKENS) when the model reasons before replying.
    THINKING_HEADROOM_TOKENS = 2048

    def __init__(self, api_key, model, timeout_seconds=30, fallback_model="", max_retries=2, thinking_level="low"):
        self.thinking_level = thinking_level
        self.api_key = api_key
        self.model = model
        self.fallback_model = fallback_model
        self.timeout_seconds = timeout_seconds
        self.max_retries = max_retries
        self._client = None

    @property
    def configured(self):
        return bool(self.api_key)

    def _get_client(self):
        if self._client is None:
            from google import genai
            from google.genai import types
            self._client = genai.Client(
                api_key=self.api_key,
                http_options=types.HttpOptions(timeout=self.timeout_seconds * 1000),
            )
        return self._client

    def generate_json(self, *, system_instruction, contents, schema, temperature=0.7, max_output_tokens=1024):
        """Return the parsed JSON object produced by the model, or raise AIUnavailable."""
        if not self.configured:
            raise AIUnavailable("not_configured", USER_MESSAGES["not_configured"])

        from google.genai import errors, types

        config = types.GenerateContentConfig(
            system_instruction=system_instruction,
            temperature=temperature,
            max_output_tokens=max_output_tokens + self.THINKING_HEADROOM_TOKENS,
            thinking_config=types.ThinkingConfig(thinking_level=self.thinking_level) if self.thinking_level else None,
            response_mime_type="application/json",
            response_json_schema=schema,
        )
        response = None
        models = [self.model] + ([self.fallback_model] if self.fallback_model and self.fallback_model != self.model else [])
        last_reason = "provider_error"
        for model in models:
            for attempt in range(self.max_retries + 1):
                try:
                    response = self._get_client().models.generate_content(model=model, contents=contents, config=config)
                    break
                except errors.ClientError as exc:
                    code = getattr(exc, "code", None)
                    log.warning("Gemini client error model=%s code=%s", model, code)
                    if code != 429:
                        raise AIUnavailable("provider_error", USER_MESSAGES["provider_error"])
                    # Quotas are per model: don't retry this one, but the fallback model may still have quota.
                    last_reason = "quota"
                    break
                except errors.ServerError as exc:
                    code = getattr(exc, "code", None)
                    log.warning("Gemini server error model=%s code=%s attempt=%s", model, code, attempt + 1)
                    if code == 504:
                        # Gateway timeout: each attempt already waited ~30 s, so move on to the fallback model.
                        last_reason = "timeout"
                        break
                    # 500/503 ("model overloaded") fail fast and are usually transient: back off and retry.
                    last_reason = "provider_error"
                except Exception as exc:  # network errors, timeouts
                    name = type(exc).__name__
                    log.warning("Gemini call failed model=%s: %s", model, name)
                    last_reason = "timeout" if "timeout" in name.lower() else "provider_error"
                if attempt < self.max_retries:
                    time.sleep(1.5 * (attempt + 1))
            if response is not None:
                break
        if response is None:
            raise AIUnavailable(last_reason, USER_MESSAGES[last_reason])

        candidates = getattr(response, "candidates", None) or []
        finish = str(getattr(candidates[0], "finish_reason", "")) if candidates else ""
        if "MAX_TOKENS" in finish:
            log.warning("Gemini output truncated (MAX_TOKENS); discarding")
            raise AIUnavailable("invalid_output", USER_MESSAGES["invalid_output"])
        text = getattr(response, "text", None)
        if not text:
            raise AIUnavailable("blocked", USER_MESSAGES["blocked"])
        try:
            data = json.loads(text)
        except (TypeError, ValueError):
            raise AIUnavailable("invalid_output", USER_MESSAGES["invalid_output"])
        if not isinstance(data, dict):
            raise AIUnavailable("invalid_output", USER_MESSAGES["invalid_output"])
        return data


def get_ai() -> GeminiService:
    return current_app.extensions["gemini"]


def to_contents(history):
    """[(role, text)] with role 'user'/'assistant' -> Gemini contents list."""
    return [{"role": "model" if role == "assistant" else "user", "parts": [{"text": text}]}
            for role, text in history]
