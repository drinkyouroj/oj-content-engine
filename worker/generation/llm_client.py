"""Unified LLM client for content generation.

Wraps both Groq and Anthropic providers behind a single async interface.
Implements per-platform model configuration, exponential-backoff retries,
and code fence stripping so callers always receive clean text.

Implements PRD Section 4 (Content Generation Engine) — provider abstraction layer.

Inputs:
    - system_prompt: str
    - user_prompt: str
    - provider: "groq" | "anthropic"
    - model: model name string
    - (optional) max_tokens, temperature, max_retries

Outputs:
    - LLMResponse dataclass with content, total_tokens, model, provider

Environment variables:
    GENERATION_MODEL_<PLATFORM>  — override default provider/model for a platform.
        Format: "provider/model", e.g. "anthropic/claude-3-5-haiku-20241022".
        PLATFORM is the uppercase platform key (e.g. SUBSTACK, TWITTER, LINKEDIN,
        INSTAGRAM, SUBSTACK_CRITIQUE).
    GROQ_API_KEY                 — optional fallback; callers usually pass the key directly.
    ANTHROPIC_API_KEY            — optional fallback; callers usually pass the key directly.
"""

from __future__ import annotations

import asyncio
import logging
import os
from dataclasses import dataclass

from groq import AsyncGroq

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Model routing table
# ---------------------------------------------------------------------------

GENERATION_MODELS: dict[str, dict[str, str]] = {
    "substack": {"provider": "anthropic", "model": "claude-sonnet-4-6"},
    "twitter": {"provider": "anthropic", "model": "claude-haiku-4-5"},
    "linkedin": {"provider": "anthropic", "model": "claude-haiku-4-5"},
    "instagram": {"provider": "anthropic", "model": "claude-haiku-4-5"},
    "substack_critique": {"provider": "anthropic", "model": "claude-sonnet-4-6"},
    "thesis_suggest": {"provider": "anthropic", "model": "claude-haiku-4-5"},
}


# ---------------------------------------------------------------------------
# Public types
# ---------------------------------------------------------------------------


class LLMGenerationError(Exception):
    """Raised when LLM generation fails after all retries or configuration is invalid."""


@dataclass
class LLMResponse:
    """Result of a single LLM generation call.

    Attributes:
        content: The generated text, with code fences already stripped.
        total_tokens: Combined input + output token count.
        model: Model name used for the call.
        provider: Provider name ("groq" or "anthropic").
    """

    content: str
    total_tokens: int
    model: str
    provider: str


# ---------------------------------------------------------------------------
# Config helpers
# ---------------------------------------------------------------------------


def get_model_config(platform: str) -> dict[str, str]:
    """Return the provider/model config for a given platform key.

    Checks the environment variable ``GENERATION_MODEL_<PLATFORM>`` first
    (format: ``provider/model``). Falls back to ``GENERATION_MODELS``.

    Args:
        platform: Platform key, e.g. "substack", "twitter", "substack_critique".

    Returns:
        Dict with "provider" and "model" string keys.

    Raises:
        KeyError: If the platform is not found in GENERATION_MODELS and no env
            var override is set.
        ValueError: If the env var override is malformed (not "provider/model").
    """
    env_var = f"GENERATION_MODEL_{platform.upper()}"
    override = os.environ.get(env_var)
    if override:
        parts = override.split("/", 1)
        if len(parts) != 2 or not parts[0] or not parts[1]:
            raise ValueError(
                f"Env var {env_var}={override!r} is malformed. "
                "Expected format: 'provider/model'."
            )
        return {"provider": parts[0], "model": parts[1]}

    # Will raise KeyError for unknown platforms — intentional.
    return dict(GENERATION_MODELS[platform])


# ---------------------------------------------------------------------------
# Client
# ---------------------------------------------------------------------------


class LLMClient:
    """Async LLM client supporting Groq and Anthropic providers.

    Handles retry with exponential backoff and code fence stripping.
    Anthropic is imported lazily so it remains an optional dependency
    (the package is optional — only needed if using the anthropic provider).

    Args:
        groq_api_key: Groq API key. Empty string disables Groq.
        anthropic_api_key: Anthropic API key. Empty string disables Anthropic.
    """

    def __init__(
        self,
        groq_api_key: str = "",
        anthropic_api_key: str = "",
    ) -> None:
        self._groq_api_key = groq_api_key
        self._anthropic_api_key = anthropic_api_key

    async def generate(
        self,
        system_prompt: str,
        user_prompt: str,
        provider: str,
        model: str,
        max_tokens: int = 4096,
        temperature: float = 0.7,
        max_retries: int = 3,
    ) -> LLMResponse:
        """Generate content using the specified provider and model.

        Retries up to ``max_retries`` times with exponential backoff
        (2^attempt seconds between attempts). Code fences are stripped
        from the final response.

        Args:
            system_prompt: System-role instruction for the LLM.
            user_prompt: User-role message / content brief.
            provider: "groq" or "anthropic".
            model: Model name accepted by the provider.
            max_tokens: Maximum output tokens. Defaults to 4096.
            temperature: Sampling temperature. Defaults to 0.7.
            max_retries: Number of attempts before raising. Defaults to 3.

        Returns:
            LLMResponse with stripped content, token count, model, and provider.

        Raises:
            LLMGenerationError: If the API key for the chosen provider is missing,
                the provider is unknown, or all retries are exhausted.
        """
        if provider == "groq":
            if not self._groq_api_key:
                raise LLMGenerationError(
                    "Groq API key is missing. Set groq_api_key on LLMClient."
                )
            call = lambda: self._generate_groq(  # noqa: E731
                system_prompt, user_prompt, model, max_tokens, temperature
            )
        elif provider == "anthropic":
            if not self._anthropic_api_key:
                raise LLMGenerationError(
                    "Anthropic API key is missing. Set anthropic_api_key on LLMClient."
                )
            call = lambda: self._generate_anthropic(  # noqa: E731
                system_prompt, user_prompt, model, max_tokens, temperature
            )
        else:
            raise LLMGenerationError(
                f"Unknown provider {provider!r}. Supported: 'groq', 'anthropic'."
            )

        last_error: Exception | None = None
        for attempt in range(max_retries):
            try:
                return await call()
            except LLMGenerationError:
                # Config errors (missing key, unknown provider) — don't retry.
                raise
            except Exception as exc:  # noqa: BLE001
                last_error = exc
                wait = 2**attempt  # 1s, 2s, 4s, …
                logger.warning(
                    "LLM generation attempt %d/%d failed (%s/%s): %s. Retrying in %ds.",
                    attempt + 1,
                    max_retries,
                    provider,
                    model,
                    exc,
                    wait,
                )
                await asyncio.sleep(wait)

        raise LLMGenerationError(
            f"LLM generation failed after {max_retries} retries "
            f"({provider}/{model}): {last_error}"
        ) from last_error

    # ------------------------------------------------------------------
    # Provider-specific internals
    # ------------------------------------------------------------------

    async def _generate_groq(
        self,
        system_prompt: str,
        user_prompt: str,
        model: str,
        max_tokens: int,
        temperature: float,
    ) -> LLMResponse:
        """Call the Groq chat completions API.

        Args:
            system_prompt: System instruction.
            user_prompt: User message.
            model: Groq model name.
            max_tokens: Max output tokens.
            temperature: Sampling temperature.

        Returns:
            LLMResponse with stripped content.

        Raises:
            Any exception from the Groq SDK on network/API failure.
        """
        client = AsyncGroq(api_key=self._groq_api_key)
        response = await client.chat.completions.create(
            model=model,
            max_tokens=max_tokens,
            temperature=temperature,
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt},
            ],
        )
        raw_text = response.choices[0].message.content.strip()
        total_tokens = getattr(response.usage, "total_tokens", 0) or 0
        return LLMResponse(
            content=self._strip_code_fences(raw_text),
            total_tokens=int(total_tokens),
            model=model,
            provider="groq",
        )

    async def _generate_anthropic(
        self,
        system_prompt: str,
        user_prompt: str,
        model: str,
        max_tokens: int,
        temperature: float,
    ) -> LLMResponse:
        """Call the Anthropic messages API.

        Imports ``anthropic`` lazily so it stays an optional dependency.

        Args:
            system_prompt: System instruction.
            user_prompt: User message.
            model: Anthropic model name.
            max_tokens: Max output tokens.
            temperature: Sampling temperature.

        Returns:
            LLMResponse with stripped content.

        Raises:
            ImportError: If the ``anthropic`` package is not installed.
            Any exception from the Anthropic SDK on network/API failure.
        """
        # Lazy import — anthropic is optional
        from anthropic import AsyncAnthropic  # noqa: PLC0415

        client = AsyncAnthropic(api_key=self._anthropic_api_key)
        response = await client.messages.create(
            model=model,
            max_tokens=max_tokens,
            temperature=temperature,
            system=system_prompt,
            messages=[{"role": "user", "content": user_prompt}],
        )
        raw_text = response.content[0].text.strip()
        total_tokens = response.usage.input_tokens + response.usage.output_tokens
        return LLMResponse(
            content=self._strip_code_fences(raw_text),
            total_tokens=total_tokens,
            model=model,
            provider="anthropic",
        )

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    @staticmethod
    def _strip_code_fences(text: str) -> str:
        """Remove markdown code fences from LLM output.

        Handles both plain ``` and annotated ```json / ```python fences.
        Returns the text unchanged if no fences are detected.

        Args:
            text: Raw LLM output string.

        Returns:
            Text with opening and closing code fences removed.
        """
        if not text.startswith("```"):
            return text
        # Drop the opening fence line (e.g. "```json")
        text = text.split("\n", 1)[1] if "\n" in text else text[3:]
        # Drop the closing fence
        if "```" in text:
            text = text.rsplit("```", 1)[0]
        return text.strip()
