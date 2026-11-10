# Demo script and manual voice checklist

Interruptions, background noise, pronunciation and real latency **can't be tested in text**
(discovery risk R3). This is the script for the recorded demo and the checklist for manual
voice testing. A voice call uses voice minutes from the plan, so keep each call to 2–3 minutes.

## Before the call (free)

```bash
make up && make seed     # fresh data: order 4721 is "en ruta" today
make tunnel              # keep open
make agent-deploy        # only if agent/ changed
make logs                # optional, third terminal: watch tool calls live
```

Open ElevenLabs → Agents → **Vera** → **Test AI agent**, and start a screen recording
(macOS: ⇧⌘5).

## Demo script (≈ 2½ minutes)

You play Lupe, owner of **Abarrotes Doña Lupe**.

| # | You say | Expect Vera to |
|---|---|---|
| 1 | *(listen)* | Introduce herself as a **virtual assistant** and ask for the customer number |
| 2 | "Es el diez mil doscientos treinta y cuatro" | Confirm "uno, cero, dos, tres, cuatro" and ask "¿Hablo de Abarrotes Doña Lupe?" |
| 3 | "Sí" | Ask for the last 4 digits of the registered phone |
| 4 | "Uno, dos, tres, cuatro" | Greet Guadalupe by first name |
| 5 | "¿Dónde está mi pedido cuarenta y siete veintiuno?" | "En ruta… con Martín… hoy entre ocho y doce" |
| 6 | "Y mándeme lo de siempre pero con tres cajas de papas" | Read the order back with an approximate total and **wait** |
| 7 | "Sí, así está bien" | Give a folio and "mañana…" (or the next day after the cutoff) |
| 8 | "Quiero hablar con una persona" | Give a short reference ("referencia número …") and the 30-minute callback promise, then ask if there's anything else |
| 9 | "No, gracias" | Say goodbye and end the call |

Afterwards: `make latency` for API timings, and check the webhook row (runbook §4).

## Manual voice checklist

Mark each one ✅/❌ with a note. Run them in a separate short call, not in the demo.

| # | Check | Pass when |
|---|---|---|
| V1 | **Barge-in:** interrupt Vera mid-sentence with "perdón, otra cosa" | She stops within ~1 s and answers the interruption |
| V2 | **Background noise:** TV or music at counter volume | Customer code still recognized; she asks to repeat at most once |
| V3 | **Numbers said in pairs:** "cuarenta y siete veintiuno" | Calls `get_order` with 4721 |
| V4 | **Self-correction:** "es el 10234… no, perdón, 20518" | Uses the corrected code and confirms it |
| V5 | **Wrong digits:** say "9999" for the phone | She says it doesn't match, without hints; after 3 failures offers a human |
| V6 | **Long pause:** stay silent for 10 s | Prompts once; doesn't hang up abruptly |
| V7 | **Pronunciation:** "Nopalia", "remisión", the folio digits, the peso amounts | Natural es-MX, digits read one by one |
| V8 | **Latency:** time from the end of your sentence to the start of the reply, with a tool call | Feels under ~2 s; note any long gaps |
| V9 | **Out of scope:** "¿me puede dar una factura?" | Offers a human, doesn't improvise |
| V10 | **API down:** stop the tunnel (Ctrl-C), then ask for an order | Apologizes, retries once, then gives the call center number; doesn't claim anything was saved |

Record the results in this file under a dated heading, so voice quality is tracked over time.
