"""
Centralized API Client and Embedding Initialization (Session 56)

Provides shared singletons and wrappers for:
  - Anthropic API client (with retry, timeout, error handling)
  - SentenceTransformer embedding model (lazy-loaded singleton)
  - Batch embedding helper
  - Structured logging to stderr

All scripts should import from here instead of creating their own clients.

Usage:
    from api_client import get_anthropic_client, call_api, get_embedding_model, embed_texts

    # Singleton Anthropic client
    client = get_anthropic_client()

    # Wrapped API call with retry and logging
    response = call_api(model="claude-haiku-4-5-20251001", messages=[...], max_tokens=2000)

    # Singleton embedding model
    model = get_embedding_model()

    # Batch embedding
    vectors = embed_texts(["text1", "text2"], batch_size=64)
"""

import logging
import os
import sys
import time
import threading



# ==========================================================================
# LOGGING — stderr only, never stdout (CLI output goes to stdout)
# ==========================================================================

_LOG_FORMAT = "[baselayer] %(asctime)s %(levelname)s %(message)s"
_LOG_DATEFMT = "%Y-%m-%d %H:%M:%S"

_log_level_name = os.environ.get("BASELAYER_LOG_LEVEL", "WARNING").upper()
_log_level = getattr(logging, _log_level_name, logging.WARNING)

_handler = logging.StreamHandler(sys.stderr)
_handler.setFormatter(logging.Formatter(_LOG_FORMAT, datefmt=_LOG_DATEFMT))

logger = logging.getLogger("baselayer")
logger.setLevel(_log_level)
# Avoid duplicate handlers if module is re-imported
if not logger.handlers:
    logger.addHandler(_handler)
logger.propagate = False


# ==========================================================================
# RESPONSE TEXT: read by block type, never by position
# ==========================================================================

class ResponseTextError(RuntimeError):
    """A Messages API response with no usable text: a refusal, or no text block."""

    def __init__(self, reason: str, caller: str = ""):
        super().__init__(f"{caller or 'api'}: response has no usable text ({reason})")
        self.reason = reason
        self.caller = caller


def response_text(response, *, caller: str = "") -> str:
    """Concatenated text of a Messages API response's TEXT blocks.

    Never read the first content block by position: with extended thinking on (the default
    on the 5-generation models) the first block is a thinking block, which has no
    `.text`, so a positional read raises or reads the wrong block. Thinking and
    any other non-text blocks are skipped.

    Raises ResponseTextError on a refusal (the content may be empty) or when no
    text block is present. A max_tokens stop still returns the text, as a
    positional read did, but is logged as a warning because the text is truncated.
    (Extraction has its own stricter reader, extract_facts.response_text, which
    also refuses a max_tokens stop because truncated JSON is unusable there.)
    """
    stop = getattr(response, "stop_reason", None)
    if stop == "refusal":
        raise ResponseTextError("refusal", caller)
    parts = [getattr(b, "text", "") or "" for b in (getattr(response, "content", None) or [])
             if getattr(b, "type", None) == "text"]
    if not parts:
        raise ResponseTextError("no_text", caller)
    if stop == "max_tokens":
        logger.warning("%s: response stopped at max_tokens; text is truncated", caller or "api")
    return "".join(parts)


# ==========================================================================
# ANTHROPIC CLIENT — singleton with retry and timeout
# ==========================================================================

_anthropic_client = None
_client_lock = threading.Lock()


def get_anthropic_client(max_retries=2, timeout=120.0):
    """Get a shared Anthropic client with retry and timeout.

    Returns a configured anthropic.Anthropic instance. Uses a module-level
    singleton so all callers share the same connection pool. Thread-safe.

    Args:
        max_retries: Number of automatic retries on transient errors (default 2).
            Only used on first initialization; subsequent calls return the
            existing client regardless of arguments.
        timeout: Request timeout in seconds (default 120).
            Only used on first initialization.
    """
    global _anthropic_client
    if _anthropic_client is not None:
        return _anthropic_client

    with _client_lock:
        if _anthropic_client is not None:
            return _anthropic_client

        try:
            import anthropic
        except ImportError:
            raise ImportError(
                "anthropic package not installed. Run: pip install anthropic"
            )

        _anthropic_client = anthropic.Anthropic(
            max_retries=max_retries,
            timeout=timeout,
        )
        logger.info("Anthropic client initialized (max_retries=%d, timeout=%.0fs)", max_retries, timeout)
        return _anthropic_client


def call_api(
    model,
    messages,
    system=None,
    max_tokens=4096,
    temperature=0,
    timeout=None,
    caller=None,
):
    """Call Anthropic Messages API with retry logic and error logging.

    Wraps the Anthropic client with:
      - Exponential backoff on rate limit errors (429)
      - Retry on transient server errors (500, 502, 503, 529)
      - Structured error logging with caller context
      - Returns the full response object for caller inspection

    Args:
        model: Anthropic model name (e.g. "claude-haiku-4-5-20251001").
        messages: List of message dicts [{"role": "user", "content": "..."}].
        system: Optional system prompt string.
        max_tokens: Maximum tokens in response (default 4096).
        temperature: Sampling temperature (default 0).
        timeout: Per-request timeout override in seconds. If None, uses client default.
        caller: Optional string identifying the calling script/function for logs.

    Returns:
        The full Anthropic response object (so callers can access .content,
        .usage, etc.). This preserves existing interfaces where scripts
        inspect usage tokens.

    Raises:
        Exception: After all retries are exhausted, re-raises the last error.
    """
    import anthropic

    client = get_anthropic_client()
    caller_tag = f"[{caller}] " if caller else ""
    max_retries = 3
    base_delay = 1.0  # seconds

    kwargs = {
        "model": model,
        "max_tokens": max_tokens,
        "temperature": temperature,
        "messages": messages,
    }
    if system:
        kwargs["system"] = system
    if timeout:
        kwargs["timeout"] = timeout

    last_error = None
    for attempt in range(max_retries + 1):
        try:
            response = client.messages.create(**kwargs)
            logger.debug(
                "%sAPI call succeeded (model=%s, in=%d, out=%d)",
                caller_tag, model,
                response.usage.input_tokens, response.usage.output_tokens,
            )
            return response

        except anthropic.RateLimitError as e:
            last_error = e
            if attempt < max_retries:
                delay = base_delay * (2 ** attempt)
                logger.warning(
                    "%sRate limited (attempt %d/%d), retrying in %.1fs: %s",
                    caller_tag, attempt + 1, max_retries + 1, delay, e,
                )
                time.sleep(delay)
            else:
                logger.error(
                    "%sRate limit exceeded after %d attempts: %s",
                    caller_tag, max_retries + 1, e,
                )

        except anthropic.APIStatusError as e:
            last_error = e
            # Retry on transient server errors
            if e.status_code in (500, 502, 503, 529) and attempt < max_retries:
                delay = base_delay * (2 ** attempt)
                logger.warning(
                    "%sServer error %d (attempt %d/%d), retrying in %.1fs: %s",
                    caller_tag, e.status_code, attempt + 1, max_retries + 1, delay, e,
                )
                time.sleep(delay)
            else:
                logger.error(
                    "%sAPI error (status=%d) after %d attempts: %s",
                    caller_tag, e.status_code, attempt + 1, e,
                )
                raise

        except anthropic.APIConnectionError as e:
            last_error = e
            if attempt < max_retries:
                delay = base_delay * (2 ** attempt)
                logger.warning(
                    "%sConnection error (attempt %d/%d), retrying in %.1fs: %s",
                    caller_tag, attempt + 1, max_retries + 1, delay, e,
                )
                time.sleep(delay)
            else:
                logger.error(
                    "%sConnection failed after %d attempts: %s",
                    caller_tag, max_retries + 1, e,
                )
                raise

        except Exception as e:
            # Non-retryable errors: raise immediately
            logger.error("%sUnexpected error: %s", caller_tag, e)
            raise

    # All retries exhausted (only reached for rate limit errors)
    raise last_error


# ==========================================================================
# EMBEDDING MODEL — singleton, lazy-loaded
# ==========================================================================

_embedding_model = None
_embedding_lock = threading.Lock()


def get_embedding_model():
    """Get a shared SentenceTransformer embedding model (singleton, thread-safe).

    Returns the model configured by EMBEDDING_MODEL in config.py.
    First call loads the model (~80MB download on first use, ~3s load time).
    Subsequent calls return the same instance.

    Handles ImportError gracefully: logs a warning and returns None if
    sentence_transformers is not installed.
    """
    global _embedding_model
    if _embedding_model is not None:
        return _embedding_model

    with _embedding_lock:
        if _embedding_model is not None:
            return _embedding_model

        try:
            from sentence_transformers import SentenceTransformer
        except ImportError:
            logger.warning(
                "sentence_transformers not installed. Embedding features unavailable. "
                "Run: pip install sentence-transformers"
            )
            return None

        try:
            from baselayer.config import EMBEDDING_MODEL
        except ImportError:
            from config import EMBEDDING_MODEL

        logger.info("Loading embedding model: %s", EMBEDDING_MODEL)
        _embedding_model = SentenceTransformer(EMBEDDING_MODEL)
        logger.info("Embedding model loaded (dim=%d)", _embedding_model.get_sentence_embedding_dimension())
        return _embedding_model


def embed_texts(texts, batch_size=64):
    """Encode a list of texts into embeddings using the singleton model.

    Args:
        texts: List of strings to embed.
        batch_size: Number of texts to encode per batch (default 64).

    Returns:
        List of embedding vectors (each a list of floats), or None if
        the embedding model is not available.
    """
    model = get_embedding_model()
    if model is None:
        logger.warning("embed_texts called but embedding model is not available")
        return None

    all_embeddings = []
    for i in range(0, len(texts), batch_size):
        batch = texts[i:i + batch_size]
        embeddings = model.encode(batch, show_progress_bar=False).tolist()
        all_embeddings.extend(embeddings)

    return all_embeddings
