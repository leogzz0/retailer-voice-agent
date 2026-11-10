# Executive summary: Vera pilot

> **Fictional.** Productos Nopalia and all figures are invented for a portfolio exercise.

**For:** Nopalia's Head of Customer Service, Engineering Lead (Integrations), Credit Manager
**Status:** pilot build complete and running end to end on test data. Ready for an internal voice trial.

## The problem
The call center gets about **2,300 calls a week**. At peak, callers wait **6–9 minutes** and **18% hang
up**. Most calls are repetitive: *where is my order* (~45%), *same order as last time* (~20%) and
*delivery problems* (~15%).

## What we built
**Vera**, a Spanish (Mexican) voice assistant. Shopkeepers talk to her in plain language. She:
- **finds and confirms the store**, and verifies the caller before sharing anything;
- tells them **where their order is**: status, driver, and a delivery window in natural Spanish ("hoy entre ocho y doce");
- **reorders "lo de siempre"**, with changes, and always reads the order back and waits for a "sí";
- **reports delivery problems** straight into logistics' queue;
- answers questions on **returns, delivery times and credit terms** from approved text only;
- **hands off to a person** whenever asked, or when the request is out of scope. A callback is promised within 30 minutes.

In a simulated test conversation against the live back office, she verified the store, found the late order, filed the report and
booked a human callback with a full summary, without making anything up.

## How we kept it safe
- Every call to Nopalia's systems is **authenticated**. Each caller is **verified** before seeing account data, and
  can't ask about another store.
- **No duplicate orders**, even when a request is retried.
- The agent configuration lives in **Nopalia's Git repository** and is deployed by one command.
  An automated check in CI catches mismatches between the agent and the back office before release.
- Transcripts are kept **30 days**. No phone numbers or full names are ever read back.

## Against the agreed targets

| Target (pilot) | Where we are |
|---|---|
| ≥ 70% order-status calls resolved without a human | Flow working; measure in the pilot |
| 100% reorders without duplicates | Guaranteed by design, covered by automated tests |
| ≥ 95% correct handoffs | Handoff on request, out of scope and system failure; tests written |
| API p95 < 500 ms | **4–71 ms** measured locally |
| Satisfaction ≥ 4/5 | Needs the post-call survey (phase 2 with telephony) |

## Decisions needed from Nopalia
1. **Verification for staff.** Store employees often don't know the registered phone number.
   Options: caller ID once we have telephony (recommended), or a per-store PIN printed on the remisión.
2. **Owners of the FAQ and product-nickname content** after go-live (open risk R5).
3. **Telephony provider and a Mexican number** (R4). Until then, the pilot runs on the web widget.
4. **Holiday calendar** for delivery dates. Not modeled yet.

## Next steps
1. A one-week internal voice trial with CS agents playing shopkeepers, using the demo script.
2. Move the API from the laptop to Cloud Run + Cloud SQL (documented, about 1 day of work).
3. Pilot with 200 stores for 4 weeks, with a weekly transcript review against the targets above.
