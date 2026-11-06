# Demo subscriptions

Illustrative monthly INR prices, not a commercial offer or validated pricing recommendation:

| Plan | Active patients | Demo price/month |
| --- | ---: | ---: |
| Starter | 100 | ₹999 |
| Growth | 500 | ₹2,499 |
| Scale | 2,000 | ₹4,999 |

Only clinic admins can manage subscriptions. An active patient has a pending, confirmed or booked follow-up in an ACTIVE plan. Each patient counts once. This is a current snapshot, not a monthly peak or real billing meter.

Select a plan under Clinic > Subscription. The server determines price and rejects plans smaller than current usage. Repeating the same selection for the month creates no duplicate. Changing plans adds a full-price demonstration entry without proration. Period end is exclusive; history retains the latest 20 entries.

History says SIMULATED_NO_PAYMENT. No money, taxes, bank/card data, refunds or recurring charges are processed. Entries are not financial/tax invoices. SMS, AI and hosting costs are not included or metered. Limits are advisory: existing care and records are never blocked. Activation is disabled outside DEMO_MODE.

Pricing constants are in backend/app/routers/billing.py. Real payments require agreed prices, merchant configuration, verified webhooks, metering and reconciliation.
