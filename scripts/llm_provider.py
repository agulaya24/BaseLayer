"""
LLM Provider Abstraction Layer (D-052)

Supports Anthropic, OpenAI, and Google (Gemini) APIs, plus local Ollama.
Provider and model are configured in config.py per pipeline role.

Usage:
    from llm_provider import call_llm

    # By role (looks up model from config)
    result = call_llm("Extract facts from...", role="extraction")

    # By explicit model (auto-detects provider from prefix)
    result = call_llm("Classify these...", model="gpt-4o-mini", max_tokens=2000)

    # Returns standardized dict:
    # {"text": str, "input_tokens": int, "output_tokens": int, "model": str}

Non-Anthropic providers require additional packages:
    pip install openai             # For OpenAI (gpt-*, o1-*, o3-*)
    pip install google-generativeai  # For Google (gemini-*)

These are only imported when actually needed — Anthropic-only users won't hit
ImportErrors from missing packages.
"""

import json
import os
import sys

# Ensure config is importable from scripts directory
sys.path.insert(0, os.path.dirname(__file__))


# ---------------------------------------------------------------------------
# Provider detection
# ---------------------------------------------------------------------------

def detect_provider(model: str) -> str:
    """Auto-detect the API provider from a model name prefix.

    Returns one of: 'anthropic', 'openai', 'google', 'ollama'.
    Raises ValueError if the model name doesn't match any known pattern.
    """
    if model.startswith("claude-"):
        return "anthropic"
    elif model.startswith(("gpt-", "o1-", "o3-")):
        return "openai"
    elif model.startswith("gemini-"):
        return "google"
    elif model.startswith("ollama:"):
        return "ollama"
    else:
        raise ValueError(
            f"Cannot detect provider for model '{model}'. "
            f"Expected prefix: claude-*, gpt-*/o1-*/o3-*, gemini-*, or ollama:*"
        )


def _resolve_model(model: str = None, role: str = None) -> str:
    """Resolve a model name from explicit model or role lookup.

    Priority: model > role. At least one must be provided.
    """
    if model:
        return model
    if role:
        from config import LLM_PROVIDER_CONFIG
        if role not in LLM_PROVIDER_CONFIG:
            valid = ", ".join(sorted(LLM_PROVIDER_CONFIG.keys()))
            raise ValueError(
                f"Unknown pipeline role '{role}'. Valid roles: {valid}"
            )
        return LLM_PROVIDER_CONFIG[role]
    raise ValueError("Must specify either 'model' or 'role' in call_llm()")


# ---------------------------------------------------------------------------
# Anthropic backend
# ---------------------------------------------------------------------------

def _call_anthropic(prompt: str, model: str, max_tokens: int, temperature: float) -> dict:
    """Call Anthropic Messages API. Returns standardized response dict.

    Uses the centralized singleton client from api_client.py with
    retry and timeout support.
    """
    from api_client import call_api

    resp = call_api(
        model=model,
        messages=[{"role": "user", "content": prompt}],
        max_tokens=max_tokens,
        temperature=temperature,
        caller="llm_provider.call_llm",
    )

    return {
        "text": resp.content[0].text.strip(),
        "input_tokens": resp.usage.input_tokens,
        "output_tokens": resp.usage.output_tokens,
        "model": model,
    }


# ---------------------------------------------------------------------------
# OpenAI backend
# ---------------------------------------------------------------------------

def _call_openai(prompt: str, model: str, max_tokens: int, temperature: float) -> dict:
    """Call OpenAI Chat Completions API. Returns standardized response dict."""
    try:
        import openai
    except ImportError:
        raise ImportError(
            "openai package not installed. Run: pip install openai"
        )

    api_key = os.environ.get("OPENAI_API_KEY")
    if not api_key:
        raise EnvironmentError(
            "OPENAI_API_KEY environment variable not set. "
            "Get your key at https://platform.openai.com/api-keys"
        )

    client = openai.OpenAI(api_key=api_key)

    # o1/o3 models don't support temperature or max_tokens the same way
    kwargs = {
        "model": model,
        "messages": [{"role": "user", "content": prompt}],
    }

    if model.startswith(("o1-", "o3-")):
        # o-series models: use max_completion_tokens, no temperature
        kwargs["max_completion_tokens"] = max_tokens
    else:
        kwargs["max_tokens"] = max_tokens
        kwargs["temperature"] = temperature

    resp = client.chat.completions.create(**kwargs)

    choice = resp.choices[0]
    usage = resp.usage

    return {
        "text": choice.message.content.strip(),
        "input_tokens": usage.prompt_tokens,
        "output_tokens": usage.completion_tokens,
        "model": model,
    }


# ---------------------------------------------------------------------------
# Google (Gemini) backend
# ---------------------------------------------------------------------------

def _call_google(prompt: str, model: str, max_tokens: int, temperature: float) -> dict:
    """Call Google Gemini API. Returns standardized response dict."""
    try:
        import google.generativeai as genai
    except ImportError:
        raise ImportError(
            "google-generativeai package not installed. Run: pip install google-generativeai"
        )

    api_key = os.environ.get("GOOGLE_API_KEY") or os.environ.get("GEMINI_API_KEY")
    if not api_key:
        raise EnvironmentError(
            "GOOGLE_API_KEY or GEMINI_API_KEY environment variable not set. "
            "Get your key at https://aistudio.google.com/apikey"
        )

    genai.configure(api_key=api_key)

    gen_config = genai.types.GenerationConfig(
        max_output_tokens=max_tokens,
        temperature=temperature,
    )

    gen_model = genai.GenerativeModel(model)
    resp = gen_model.generate_content(prompt, generation_config=gen_config)

    # Extract token counts from usage_metadata
    usage = resp.usage_metadata
    input_tokens = getattr(usage, "prompt_token_count", 0) or 0
    output_tokens = getattr(usage, "candidates_token_count", 0) or 0

    return {
        "text": resp.text.strip(),
        "input_tokens": input_tokens,
        "output_tokens": output_tokens,
        "model": model,
    }


# ---------------------------------------------------------------------------
# Ollama backend (local)
# ---------------------------------------------------------------------------

def _call_ollama(prompt: str, model: str, max_tokens: int, temperature: float) -> dict:
    """Call local Ollama API. Model format: 'ollama:model_name'.
    Returns standardized response dict."""
    import requests

    from config import OLLAMA_URL

    # Strip 'ollama:' prefix to get the actual model name
    ollama_model = model.replace("ollama:", "", 1)

    payload = {
        "model": ollama_model,
        "prompt": prompt,
        "stream": False,
        "options": {
            "temperature": temperature,
            "num_predict": max_tokens,
        },
    }

    try:
        resp = requests.post(OLLAMA_URL, json=payload, timeout=120)
        resp.raise_for_status()
        data = resp.json()
    except requests.exceptions.ConnectionError:
        raise ConnectionError(
            f"Cannot connect to Ollama at {OLLAMA_URL}. "
            f"Is Ollama running? Start with: ollama serve"
        )
    except requests.exceptions.RequestException as e:
        raise RuntimeError(f"Ollama request failed: {e}")

    text = data.get("response", "").strip()

    # Ollama provides eval_count and prompt_eval_count for token tracking
    input_tokens = data.get("prompt_eval_count", 0)
    output_tokens = data.get("eval_count", 0)

    return {
        "text": text,
        "input_tokens": input_tokens,
        "output_tokens": output_tokens,
        "model": model,
    }


# ---------------------------------------------------------------------------
# Singleton clients — delegated to api_client.py (Session 56 centralization)
# ---------------------------------------------------------------------------
# These functions are thin wrappers that delegate to api_client.py.
# Kept here for backward compatibility — existing scripts import from
# llm_provider, and these re-exports ensure they keep working.

def get_anthropic_client(max_retries=2, timeout=120.0):
    """Get a shared Anthropic client with retry and timeout.

    Delegates to api_client.get_anthropic_client() for centralized
    singleton management, retry logic, and logging.
    """
    from api_client import get_anthropic_client as _get_client
    return _get_client(max_retries=max_retries, timeout=timeout)


def get_embedding_model():
    """Get a shared SentenceTransformer embedding model (singleton).

    Delegates to api_client.get_embedding_model() for centralized
    singleton management and graceful ImportError handling.
    """
    from api_client import get_embedding_model as _get_model
    return _get_model()


# ---------------------------------------------------------------------------
# Provider dispatch table
# ---------------------------------------------------------------------------

_PROVIDER_BACKENDS = {
    "anthropic": _call_anthropic,
    "openai": _call_openai,
    "google": _call_google,
    "ollama": _call_ollama,
}


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def call_llm(
    prompt: str,
    model: str = None,
    role: str = None,
    max_tokens: int = 4096,
    temperature: float = 0,
) -> dict:
    """
    Call an LLM through the unified provider abstraction.

    Args:
        prompt: The full prompt text to send.
        model: Explicit model name (e.g. 'claude-haiku-4-5-20251001', 'gpt-4o-mini').
               Auto-detects provider from prefix. Takes priority over role.
        role: Pipeline role name (e.g. 'extraction', 'authoring').
              Looks up model from LLM_PROVIDER_CONFIG in config.py.
        max_tokens: Maximum tokens in the response (default 4096).
        temperature: Sampling temperature (default 0 = deterministic).

    Returns:
        dict with keys:
            text (str): The model's response text.
            input_tokens (int): Number of input tokens consumed.
            output_tokens (int): Number of output tokens generated.
            model (str): The model that was actually used.

    Raises:
        ValueError: If neither model nor role is specified, or role is unknown.
        ImportError: If required provider package is not installed.
        EnvironmentError: If required API key is missing.
    """
    resolved_model = _resolve_model(model, role)
    provider = detect_provider(resolved_model)
    backend_fn = _PROVIDER_BACKENDS[provider]
    return backend_fn(prompt, resolved_model, max_tokens, temperature)


def get_provider_info(model: str = None, role: str = None) -> dict:
    """
    Get provider metadata without making an API call.
    Useful for cost estimation, logging, and eval metadata.

    Returns:
        dict with keys: model, provider, requires_api_key, api_key_env_var, installed
    """
    resolved_model = _resolve_model(model, role)
    provider = detect_provider(resolved_model)

    # Check if the required package is importable
    installed = True
    api_key_vars = []
    if provider == "anthropic":
        api_key_vars = ["ANTHROPIC_API_KEY"]
        try:
            import anthropic  # noqa: F401
        except ImportError:
            installed = False
    elif provider == "openai":
        api_key_vars = ["OPENAI_API_KEY"]
        try:
            import openai  # noqa: F401
        except ImportError:
            installed = False
    elif provider == "google":
        api_key_vars = ["GOOGLE_API_KEY", "GEMINI_API_KEY"]
        try:
            import google.generativeai  # noqa: F401
        except ImportError:
            installed = False
    elif provider == "ollama":
        api_key_vars = []  # No API key needed

    has_key = any(os.environ.get(v) for v in api_key_vars) if api_key_vars else True

    return {
        "model": resolved_model,
        "provider": provider,
        "requires_api_key": provider != "ollama",
        "api_key_env_vars": api_key_vars,
        "api_key_set": has_key,
        "package_installed": installed,
    }


# ---------------------------------------------------------------------------
# Pricing reference (for cost estimation in eval scripts)
# ---------------------------------------------------------------------------

# Approximate pricing per 1M tokens as of 2025-05.
# Used for cost tracking in eval runs — not billing-critical.
PRICING = {
    # Anthropic
    "claude-haiku-4-5-20251001": {"input": 0.80, "output": 4.00},
    "claude-sonnet-4-20250514": {"input": 3.00, "output": 15.00},
    "claude-sonnet-4-6": {"input": 3.00, "output": 15.00},
    "claude-opus-4-20250514": {"input": 15.00, "output": 75.00},
    "claude-opus-4-6": {"input": 15.00, "output": 75.00},
    # OpenAI
    "gpt-4o": {"input": 2.50, "output": 10.00},
    "gpt-4o-mini": {"input": 0.15, "output": 0.60},
    "gpt-4.1": {"input": 2.00, "output": 8.00},
    "gpt-4.1-mini": {"input": 0.40, "output": 1.60},
    "gpt-4.1-nano": {"input": 0.10, "output": 0.40},
    "o3-mini": {"input": 1.10, "output": 4.40},
    # Google
    "gemini-2.0-flash": {"input": 0.10, "output": 0.40},
    "gemini-2.0-pro": {"input": 1.25, "output": 10.00},
    "gemini-2.5-flash-preview-04-17": {"input": 0.15, "output": 0.60},
    "gemini-2.5-pro-preview-05-06": {"input": 1.25, "output": 10.00},
}


def estimate_cost(model: str, input_tokens: int, output_tokens: int) -> float:
    """Estimate cost in USD for a given model and token counts.
    Returns 0.0 if model not in pricing table (e.g. ollama)."""
    rates = PRICING.get(model, {})
    if not rates:
        return 0.0
    input_cost = (input_tokens / 1e6) * rates["input"]
    output_cost = (output_tokens / 1e6) * rates["output"]
    return input_cost + output_cost
