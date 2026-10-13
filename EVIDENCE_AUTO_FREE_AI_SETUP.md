# Evidence Lab Daily Auto Processor — free-only multi-provider setup

This patch keeps all existing manual/interactive Evidence Lab AI functions on Groq. Only the Daily Auto Processor receives the fallback router below:

1. Groq — existing account, internal Evidence Lab ceiling 120,000 tokens/day.
2. OpenRouter — free-only model endpoint, maximum 45 requests/day.
3. Cloudflare Workers AI — optional free-only fallback, maximum 6,000 estimated neurons/day and 40 calls/day.
4. Stop until the next UTC day. There is no paid-provider fallback.

## 1. OpenRouter

Create an OpenRouter API key and add it to the Cloudflare Pages production environment as a secret:

- `OPENROUTER_API_KEY`

Optional variable:

- `OPENROUTER_FREE_MODEL=nvidia/nemotron-3-ultra-550b-a55b:free`

The Worker rejects an OpenRouter model unless its ID ends in `:free` or is exactly `openrouter/free`. This prevents accidental use of a paid OpenRouter endpoint even if the account has credits.

No GitHub secret is required. The scheduled GitHub Action still calls the same protected Evidence Lab endpoint.

## 2. Cloudflare Workers AI (optional third fallback)

For a Cloudflare Pages Function, create a Workers AI binding in the Cloudflare dashboard:

- Binding name: `AI`

Then add this production environment variable:

- `EVIDENCE_AUTO_CF_FREE_ENABLED=true`

Optional model variable:

- `EVIDENCE_AUTO_CF_MODEL=@cf/zai-org/glm-4.7-flash`

The Worker only accepts these models for this fallback:

- `@cf/zai-org/glm-4.7-flash`
- `@cf/google/gemma-4-26b-a4b-it`

The default internal ceiling is 6,000 estimated neurons/day, below Cloudflare's 10,000-neuron daily free allocation, leaving 4,000 neurons of headroom.

Important: Cloudflare's free allocation is account-wide. The Worker can track only Evidence Lab's own estimated usage, not usage by other Workers AI projects on the same account. To preserve a strict zero-cost policy, enable this fallback only if the account is on Workers Free or if other Workers AI usage is known to stay within the remaining 4,000-neuron headroom. If uncertain, leave `EVIDENCE_AUTO_CF_FREE_ENABLED` unset; the router will stop after Groq + OpenRouter rather than risk paid usage.

## 3. Default limits

These are optional Cloudflare environment variables. If absent, the defaults shown are used:

- `EVIDENCE_AUTO_DAILY_TOKEN_BUDGET=120000`
- `EVIDENCE_AUTO_TOKEN_CALL_RESERVE=6000`
- `EVIDENCE_AUTO_OPENROUTER_DAILY_CALL_CAP=45`
- `EVIDENCE_AUTO_CF_DAILY_CALL_CAP=40`
- `EVIDENCE_AUTO_CF_DAILY_NEURON_BUDGET=6000`
- `EVIDENCE_AUTO_CF_NEURON_CALL_RESERVE=250`
- `EVIDENCE_AUTO_AREA_DAILY_CAP=24`
- `EVIDENCE_AUTO_BATCH_SIZE=6`

The Cloudflare neuron budget is hard-clamped below 10,000 in code. The OpenRouter call cap is hard-clamped to at most 50/day.

## 4. Dashboard

The Daily Auto Processor panel now reports separately:

- Groq tokens used / Evidence Lab ceiling
- OpenRouter free calls used / cap
- Cloudflare estimated neurons used / Evidence Lab ceiling
- next AI provider
- last provider used

Existing `Groq tokens today` counters are retained for backward compatibility with today's ledger.

## 5. Deployment

Commit the changed source files and let `Deploy Scientific Library to Cloudflare` deploy them. No change is required to `.github/workflows/evidence-lab-daily-auto.yml` or `EVIDENCE_AUTOMATION_SECRET`.

After deployment, add `OPENROUTER_API_KEY`. Add the Workers AI `AI` binding and `EVIDENCE_AUTO_CF_FREE_ENABLED=true` only if you want the optional third fallback under the zero-cost conditions above.
