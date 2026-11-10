# ADR-0002: Shape of the agent-facing tool API

- **Status:** accepted
- **Date:** 2026-11-09

## Context
The consumer of this API is an LLM in a live voice conversation, not a frontend. That
changes what "a good API" means. Every field costs tokens and latency, values get read aloud,
and error messages need to tell the model what to do next. The customer also requires
minimal PII and strict per-store data isolation.

## Decision
1. **Customer-scoped routes.** Everything about a store lives under
   `/v1/customers/{customer_code}/...`. Order lookups filter by *both* folio and customer, so
   a guessed folio from another store returns 404. Isolation is enforced by the API, not
   by the prompt.
2. **Pre-rendered Spanish next to machine values.** For example, `promised_date` and `promised_date_es`
   (`"mañana, jueves 12 de noviembre"`), or `window_es` (`"hoy, entre 9:00 y 13:00"`), computed in the
   business timezone (America/Monterrey). The LLM reads the phrase instead of doing date math.
3. **Relayable errors.** Errors return `{code, message_es}`. `code` is for logs and tests.
   `message_es` tells the agent what to say or do next ("pide que lo repita dígito por dígito",
   "ask them to repeat it digit by digit").
4. **Tolerant inputs, strict outputs.** Customer codes accept STT artifacts (`"10 234"`).
   Phones accept any Mexican format. Products are found by fuzzy, accent-insensitive search over
   names *and* shopkeeper nicknames (`pg_trgm` + `unaccent`).
5. **Data minimization.** First names only. Phone numbers are never returned. Credit is exposed only as
   the *available* amount.
6. **Small, bounded lists.** `limit` defaults to 3 and is capped at 10.

## Alternatives considered
- **Return raw ISO dates and let the LLM phrase them.** Simpler API, but weekday/date errors
  are a known LLM failure mode and the most damaging kind of error in this use case.
- **Flat `/orders/{folio}` route plus prompt instruction to "only discuss the caller's
  orders".** Prompt-only isolation is not a security control.
- **Embedding search for products.** Better for semantic matches, but it needs an embedding model
  and infrastructure. Trigram matching covers the observed failure modes (accents, typos, nicknames)
  for a 26-SKU catalog. Revisit if the catalog grows into the thousands.

## Consequences
- Spanish phrasing lives in the API (`speech.py`). Adding another language means extending
  that module, which is acceptable because the customer is es-MX only.
- The nickname list (`products.search_terms`) is now business content that needs an owner
  (discovery risk R5).
