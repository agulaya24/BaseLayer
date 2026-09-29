"""Prices for the distillation path: one dated table, confirmed by the operator per run.

The project rule is never to price from an in-repo constant nobody re-checks. Two copies of a
rate table used to live here (distill.py and author_from_package.py); the distill copy listed
claude-sonnet-5 at $3/$15 while the published rate is $2/$10, so every printed distill cost was
1.5x the bill. There is now ONE table, it carries the date it was read and where from, and a
billed run refuses to start until the operator either confirms that date or supplies the rates.

Confirm with `--rates-confirmed <RATES_AS_OF>` (or BASELAYER_RATES_CONFIRMED), or override with
`--rate-in X --rate-out Y`. A model absent from the table is refused unless both rates are given.
"""
import os

# Source: the claude-api skill's Current Models table (first-party API rates), cached
# 2026-06-24, read on 2026-09-25. USD per million tokens, (input, output).
RATES_AS_OF = "2026-06-24"
RATES_READ_ON = "2026-09-25"
RATES_SOURCE = "claude-api skill, Current Models table (first-party API rates)"
RATES_PER_MTOK = {
    "claude-haiku-4-5": (1.0, 5.0),
    "claude-sonnet-5": (2.0, 10.0),
    "claude-opus-5": (5.0, 25.0),
    "claude-opus-5-5": (4.0, 20.0),
}
# Message Batches API: 50% of the standard rate, input and output.
BATCH_DISCOUNT = 0.5


class RatesNotConfirmed(SystemExit):
    """The run would price itself from a table the operator has not confirmed."""


def add_rate_args(ap):
    ap.add_argument("--rates-confirmed", default=None,
                    help="confirm the in-repo rate table by its date (%s, %s). Also read from "
                         "BASELAYER_RATES_CONFIRMED." % (RATES_AS_OF, RATES_SOURCE))
    ap.add_argument("--rate-in", type=float, default=None,
                    help="USD per million input tokens; overrides the table (needs --rate-out)")
    ap.add_argument("--rate-out", type=float, default=None,
                    help="USD per million output tokens; overrides the table (needs --rate-in)")


def resolve_rates(model, rate_in=None, rate_out=None, confirmed=None):
    """The rates a run prices itself at, with where they came from. Raises RatesNotConfirmed
    unless the operator supplied both rates or confirmed the table's date."""
    if rate_in is not None or rate_out is not None:
        if rate_in is None or rate_out is None:
            raise RatesNotConfirmed("give both --rate-in and --rate-out, or neither")
        return {"model": model, "in": float(rate_in), "out": float(rate_out),
                "source": "operator", "as_of": None, "batch_discount": BATCH_DISCOUNT}
    if model not in RATES_PER_MTOK:
        raise RatesNotConfirmed(
            "no rate for %r in the table dated %s; pass --rate-in and --rate-out"
            % (model, RATES_AS_OF))
    if confirmed is None:
        confirmed = os.environ.get("BASELAYER_RATES_CONFIRMED")
    i, o = RATES_PER_MTOK[model]
    if confirmed != RATES_AS_OF:
        raise RatesNotConfirmed(
            "RATES NOT CONFIRMED. This run would price %s at $%g in / $%g out per MTok from the "
            "in-repo table dated %s (%s). Check the current price list, then pass "
            "--rates-confirmed %s, or pass --rate-in and --rate-out."
            % (model, i, o, RATES_AS_OF, RATES_SOURCE, RATES_AS_OF))
    return {"model": model, "in": i, "out": o, "source": RATES_SOURCE, "as_of": RATES_AS_OF,
            "batch_discount": BATCH_DISCOUNT}


def rates_from_args(model, a):
    return resolve_rates(model, getattr(a, "rate_in", None), getattr(a, "rate_out", None),
                         getattr(a, "rates_confirmed", None))


def cost_usd(rates, tin, tout, batch=False):
    usd = tin / 1e6 * rates["in"] + tout / 1e6 * rates["out"]
    return usd * (rates.get("batch_discount", BATCH_DISCOUNT) if batch else 1.0)


# --------------------------------------------------------------------------- spend ceiling
# Same variable as extraction (BASELAYER_SPEND_CEILING_USD), one difference: on this path an
# unset ceiling does not mean "no ceiling". A billed distillation or authoring run refuses to
# start unless there is a ceiling at or above its estimate, or the operator passes
# --confirm-spend with an amount at or above the estimate, which then becomes the ceiling.
#
# Estimate constants, MEASURED, and they do not transfer beyond what they were measured on:
#   LEAF: 18 leaves of 50 facts, claude-sonnet-5, no thinking parameter sent (so adaptive),
#     one mini corpus (2026-09-25 preflight ledger): 40,899 input and 153,169 output tokens over
#     19 calls including one schema repair. Output per leaf, repair share included: 8,509.
#   AUTHOR: claude-opus-5-5, effort high, three layers from small packages: 8,716 / 6,843 /
#     8,352 output tokens; compose 16,833 on its first attempt. A large package will emit more.
# The ceiling, not the estimate, is what bounds a run: it is checked before every call against
# measured spend plus that call's worst case (prompt chars / CHARS_PER_TOKEN input, max_tokens
# output).
MEASURED_LEAF_OUT_TOKENS = 8509
MEASURED_LEAF_BASIS = ("claude-sonnet-5, 50-fact chunks, 18 leaves + 1 repair, one mini corpus, "
                       "2026-09-25")
MEASURED_AUTHOR_LAYER_OUT_TOKENS = 8000
MEASURED_COMPOSE_OUT_TOKENS = 17000
CHARS_PER_TOKEN = 3.5
# Leaf payload (themes + singularities collected from the leaves, as JSON, counted with
# count_tokens): 7,107 tokens for 295 facts on the same mini run, one layer.
MEASURED_PAYLOAD_TOKENS_PER_FACT = 24.1
MEASURED_PAYLOAD_BASIS = "claude-sonnet-5, 50-fact chunks, 295 facts, one mini corpus, 2026-09-25"


class SpendCeilingExceeded(SystemExit):
    """A call would take measured spend past the run's ceiling. A SystemExit so that no broad
    `except Exception` retry loop can absorb it."""


class SpendNotConfirmed(SystemExit):
    """The run has no ceiling, or its estimate exceeds the ceiling, and no --confirm-spend
    covers it."""


def add_spend_args(ap):
    ap.add_argument("--confirm-spend", type=float, default=None,
                    help="USD the operator accepts for this run. Must be at or above the "
                         "printed estimate, and becomes the run's ceiling. Without it the "
                         "ceiling is BASELAYER_SPEND_CEILING_USD, and a run with neither is "
                         "refused.")


def env_ceiling():
    raw = os.environ.get("BASELAYER_SPEND_CEILING_USD")
    return float(raw) if raw not in (None, "") else None


def plan_ceiling(estimate_usd, confirm_spend=None, env=None):
    """The ceiling this run executes under, or a refusal before any client exists."""
    if env is None:
        env = env_ceiling()
    if confirm_spend is not None:
        if confirm_spend < estimate_usd:
            raise SpendNotConfirmed(
                "--confirm-spend $%.4f is below the estimate $%.4f; not starting"
                % (confirm_spend, estimate_usd))
        return float(confirm_spend)
    if env is None:
        raise SpendNotConfirmed(
            "NO SPEND CEILING. Estimate $%.4f. Set BASELAYER_SPEND_CEILING_USD at or above it, "
            "or pass --confirm-spend with an amount at or above it." % estimate_usd)
    if estimate_usd > env:
        raise SpendNotConfirmed(
            "ESTIMATE $%.4f exceeds the ceiling $%.4f (BASELAYER_SPEND_CEILING_USD); not "
            "starting. Pass --confirm-spend >= the estimate to run anyway." % (estimate_usd, env))
    return env


class SpendGuard:
    """Per-call ceiling. check() before a call, record() after it with the billed usage."""

    def __init__(self, rates, ceiling_usd, chars_per_token=CHARS_PER_TOKEN, label=""):
        self.rates = rates
        self.ceiling_usd = float(ceiling_usd)
        self.chars_per_token = chars_per_token
        self.label = label
        self.spent_usd = 0.0
        self.calls = 0
        self.tokens = {"in": 0, "out": 0, "batch_in": 0, "batch_out": 0}

    def worst_usd(self, prompt_chars, max_tokens, batch=False):
        return cost_usd(self.rates, prompt_chars / self.chars_per_token, max_tokens, batch)

    def check(self, prompt_chars, max_tokens, batch=False):
        worst = self.worst_usd(prompt_chars, max_tokens, batch)
        if self.spent_usd + worst > self.ceiling_usd:
            raise SpendCeilingExceeded(
                "SPEND CEILING%s $%.4f: measured $%.4f plus this call's worst case $%.4f would "
                "pass it; stopping before the call"
                % (" [%s]" % self.label if self.label else "", self.ceiling_usd,
                   self.spent_usd, worst))

    def record(self, tin, tout, batch=False):
        self.calls += 1
        self.tokens["batch_in" if batch else "in"] += int(tin)
        self.tokens["batch_out" if batch else "out"] += int(tout)
        self.spent_usd += cost_usd(self.rates, tin, tout, batch)

    def summary(self):
        return {"ceiling_usd": self.ceiling_usd, "measured_usd": round(self.spent_usd, 6),
                "calls": self.calls, "tokens": dict(self.tokens)}


def estimate_calls(prompt_chars, out_tokens_each, rates, max_tokens, batch=False):
    """(point, worst) USD for one call per prompt. Point uses the measured output per call;
    worst assumes every call stops at max_tokens and none is repaired."""
    tin = sum(prompt_chars) / CHARS_PER_TOKEN
    n = len(prompt_chars)
    return (cost_usd(rates, tin, n * out_tokens_each, batch),
            cost_usd(rates, tin, n * max_tokens, batch))
