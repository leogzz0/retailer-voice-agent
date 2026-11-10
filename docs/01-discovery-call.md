# Discovery call summary: Productos Nopalia

> **Fictional.** Productos Nopalia, its people, figures and systems are invented for a
> portfolio exercise. Any resemblance to a real company is unintended.

| | |
|---|---|
| **Date** | 2026-11-09 (60 min, video call) |
| **Customer** | Productos Nopalia S.A. de C.V., Monterrey, N.L. |
| **Attendees (Nopalia)** | Head of Customer Service; Engineering Lead, Integrations; Commercial Credit Manager |
| **Attendees (us)** | Forward Deployed Engineer |
| **Goal of call** | Understand the problem, scope a first voice-agent use case, and agree on success criteria |

## 1. Context

- Nopalia makes and distributes snacks, beverages and pantry staples under its own brands.
  It sells directly to about **12,000 tiendas de abarrotes** (small independent grocery stores) in
  Nuevo León, Coahuila and Tamaulipas, through 40 delivery routes out of two distribution centers.
- Shopkeepers order mostly through **sales reps on weekly visits**. A WhatsApp channel exists
  but is handled manually.
- The **call center** (14 agents, Monday to Saturday, 8:00–18:00) receives about **2,300 calls per week**.
  The Head of Customer Service estimates the mix from a two-week manual tally:

| Call reason | Share | Notes |
|---|---|---|
| "¿Dónde está mi pedido?" (where is my order?) | ~45% | Peaks 10:00–13:00 on delivery days |
| Repeat last order / add items before cutoff | ~20% | Often "lo mismo de la otra vez" ("the same as last time") |
| Delivery problem (missed, incomplete, damaged) | ~15% | Highest frustration; drives churn |
| Credit, invoices, prices | ~12% | Needs the credit team; out of scope for v1 |
| Other | ~8% | Complaints about reps, new store sign-ups, etc. |

- Average wait at peak is **6–9 minutes**, and about 18% of calls are abandoned. Shopkeepers call while
  serving customers at the counter, so they are often interrupted and background noise is high.

## 2. Requirements we heard

### Must have (v1)
1. **Spanish (Mexican) voice agent** that can be called by phone. *For the pilot, a web
   widget is acceptable while telephony is procured.*
2. Identify the store by **customer number** (5 digits, printed on every remisión, the delivery note) or
   by the **registered phone number**.
3. **Order status:** status, delivery window and driver. Must say *"hoy entre 9 y 13 horas"*
   ("today between 9 and 13"), not a timestamp.
4. **Reorder** the store's usual products with quantity changes, before the next-day cutoff
   (18:00).
5. **Report a delivery problem.** Create an incident the logistics team sees in their queue.
6. **Hand off to a human** for anything out of scope, after two failed attempts to understand,
   or whenever the caller asks for a person. *"Never trap a shopkeeper with a robot."*
   (Head of Customer Service)
7. Answer **FAQ** from approved content only: returns, delivery windows, credit terms.

### Constraints from engineering
- Back-office systems (orders, customers, logistics) are exposed through an internal REST layer.
  Nothing calls the ERP directly.
- Every integration must use **authenticated** endpoints, and **no shared admin credentials**.
- The agent must not create **duplicate orders** if a request is retried.
- Logs must be **structured** and joinable with the call/conversation id.
- They want the agent configuration **in their Git repo** with review and CI. "We don't
  click-configure production."
- PII: return the **minimum** needed. The agent should never read back full names or phone numbers.

### Out of scope (v1)
- Credit-limit changes, payments, invoice disputes (go to the credit team via handoff).
- Outbound calls (e.g., "your order is late" proactive calls). *A candidate for phase 2.*
- New customer onboarding.

## 3. Success criteria (agreed)

| Metric | Target for pilot (4 weeks, 200 stores) |
|---|---|
| Order-status calls resolved without a human | ≥ 70% |
| Reorders created by the agent with zero duplicates | 100% |
| Correct handoff when requested or out of scope | ≥ 95% (from transcript review) |
| Tool latency p95 (API side) | < 500 ms |
| Shopkeeper satisfaction (1-question post-call survey) | ≥ 4/5 |

## 4. Risks and open questions

| # | Item | Owner | Status |
|---|---|---|---|
| R1 | **Speech recognition of numbers:** customer codes and folios spoken as "diez mil doscientos treinta y cuatro" vs "uno cero dos tres cuatro" | FDE | Mitigate: digit-by-digit confirmation; API tolerant to spaces |
| R2 | **Product names:** shopkeepers use nicknames and competitor brand names generically | FDE | Mitigate: fuzzy search over nickname list maintained by commercial team |
| R3 | **Noisy environments and interruptions** at the counter | FDE | Test manually in voice; tune turn-taking |
| R4 | Telephony provider and Mexican number procurement | Nopalia IT | Open; pilot uses web widget |
| R5 | Who owns the nickname list and FAQ content after go-live | Nopalia CS | Open. **Need a named owner** |
| Q1 | Can the agent see credit availability, even if it can't change it? | Credit Manager | Yes, read-only, say "disponible" amount only |
| Q2 | Cutoff for next-day delivery identical on all routes? | Logistics | No: 18:00 metro, 14:00 foreign routes. *Follow-up* |

## 5. Next steps

1. **FDE:** solution design draft and a working read-only prototype against a sandbox copy of the
   back-office API (this repo's `api/`). *Due: end of week 1.*
2. **Nopalia Engineering:** sandbox API credentials and an outbound IP allowlist decision.
3. **Nopalia CS:** approved FAQ text (returns, delivery windows, credit terms) in Spanish.
4. **Both:** 30-minute weekly check-in, Thursdays 10:00.
