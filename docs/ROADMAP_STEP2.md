# Step 2 — Productionising for 100–500 franchise owners

Goal: a subscription product you two can build and operate, without re-writing the business logic.
Stack chosen for low cost, low ops burden and your Django preference.

## 1. Target architecture

```
Browser / phone ──► Django (HTMX templates or DRF + small JS) ──► PostgreSQL
                       │                                            ▲
                       ├── core/  (this repo, unchanged)            │
                       ├── Celery-lite: Django-Q / cron jobs ───────┘   (nightly backups, alerts)
                       └── Razorpay webhooks (subscriptions)
```

| Concern | Choice | Why |
|---|---|---|
| Backend | **Django 5** + `django-allauth` (login, Google sign-in) | batteries included: auth, admin, ORM, migrations |
| UI | Django templates + **HTMX** + Plotly.js, or DRF + React later | Streamlit cannot do multi-user auth/tenancy properly; HTMX keeps you full-stack Python |
| Database | **PostgreSQL** on Neon or Supabase (free → ~$19–25/mo) | managed, branching, point-in-time restore, no DBA |
| Hosting | **Railway** or **Render** (web service + cron) | git push deploys, ~$5–10/mo per service, autoscale later |
| Static/media | WhiteNoise (static) · Cloudflare R2 (exports/backups, free 10 GB) | |
| Payments | **Razorpay Subscriptions** (India, UPI autopay) | webhook → activate/suspend tenant |
| Email/alerts | Resend or Brevo free tier · WhatsApp Cloud API later | low-stock & unsettled-day nudges are the retention feature |
| Monitoring | Sentry free tier · UptimeRobot | |

At 500 tenants × ~50 rows/day this is a few hundred MB per year — a single small Postgres and
one web dyno is comfortable. There is no need for Kubernetes, microservices or a queue broker.

## 2. Multi-tenancy

Use **one database, shared tables, `tenant_id` on every row** (row-level tenancy). It is the
simplest to operate and plenty for this scale. Enforce it in one place with a `TenantManager`
default manager and middleware that sets the current tenant from the logged-in user. Add
Postgres row-level security later only if a customer demands it.

```
Tenant(id, name, plan, status, currency, locale, created_at)
Membership(user, tenant, role: owner|partner|staff)
```

Roles: *owner* (billing, catalog), *partner* (everything except billing), *staff* (Day Close and
expense entry only — this is the 18-year-old at the cart, and it is the reason the Day Close
form exists).

## 3. Django models = the SQL schema already in `data/sql_repo.py`

```python
class Product(TenantModel):   name, category, sell_price, unit_margin, reorder_threshold, fridge_threshold, fridge_tracked, active, sort_order
class Partner(TenantModel):   name, share_pct, user (nullable FK)
class Expense(TenantModel):   date, type, description, amount, paid_via, is_operational, paid_by (FK Partner), comments, created_by
class Purchase(TenantModel):  date, product (FK), qty, batch
class StockMovement(TenantModel): date, mode, product (FK), qty, batch
class Revenue(TenantModel):   date, amount, comments
class Payout(TenantModel):    date, partner (FK), amount, batch
class Batch(TenantModel):     kind, date, created_by, created_at, note        # groups one Day Close / one purchase
```

Add a `DailyClose(date, status: open|closed, closed_at)` row so "settled" becomes an explicit
state instead of being inferred from the presence of a `from vendor` row.

### Reusing `core/`
`core/inventory.py` and `core/finance.py` take DataFrames. In Django, a `services.py` does:

```python
frames = {S.FRIDGE: read_frame(StockMovement.objects.filter(tenant=t)), ...}
inv = compute_inventory(frames[S.BOUGHT], frames[S.FRIDGE], catalog_for(t))
```

`read_frame` is the same pivot that `data/sql_repo.py` already does. Cache the result per tenant
for 60 s (Django cache / Redis later). When a tenant exceeds ~50k movements, move the heavy
sums to a nightly materialised `ProductDailyStats` table — `core/` keeps working on the summary.

## 4. Phased plan (keep shipping while you build)

**Phase 0 — now (done in this repo)**
Layered Streamlit app, repository interface, SQL backend, migration script, tests.

**Phase 1 — 2–3 weeks: run on Postgres, still Streamlit**
- Create a Neon/Supabase Postgres; `python scripts/migrate_to_db.py --to postgresql+psycopg://…`
- Switch `data_backend = "sql"`. You are now off Google Sheets quota and rate limits.
- Nightly `pg_dump` to R2 (GitHub Action is enough).
- Keep the sheet as a read-only mirror if you like (a weekly export job).

**Phase 2 — 4–6 weeks: Django skeleton behind the same data**
- `django-admin startproject`, apps: `tenants`, `catalog`, `ledger`, `dashboard`, `billing`.
- Point Django at the same Postgres; `inspectdb` the existing tables or write the models above and
  run a one-off data copy.
- Build **Day Close** and **Expense** pages first (the daily workflow), then the dashboard,
  reusing `core/`. Streamlit stays live until parity.
- Django admin gives you the ops console (tenants, users, plans) for free.

**Phase 3 — 2–3 weeks: SaaS plumbing**
- Sign-up → create Tenant → seed catalog from a **franchise template** (your `business.json`).
  Franchise-level templates (one per franchisor) are the sales hook: an owner signs up and the
  flavours, prices and thresholds are already there.
- Razorpay subscription + webhook, trial period, suspend on failed payment.
- Invite flow for partners/staff; audit log on every write.

**Phase 4 — ongoing: the features worth charging for**
- Low-stock / unsettled-day reminders on WhatsApp.
- Monthly P&L PDF per tenant; partner settlement statement.
- Franchisor view: aggregate sell-through across owners (opt-in) — this is what makes the
  *franchise owner* want to resell it for you.
- Mobile-first Day Close with "same as yesterday" and a barcode/photo later.

## 5. Costs (realistic, INR/month)

| Stage | Stack | ≈ cost |
|---|---|---|
| 1–10 tenants | Render free/starter + Neon free | ₹0–800 |
| 10–100 | Railway Hobby + Neon Launch + Resend | ₹2,500–4,000 |
| 100–500 | 2 web instances + Neon Scale + R2 + Sentry team | ₹8,000–15,000 |

Pricing anchor: if an owner pays ₹499–999/month, 50 tenants cover infra and your time
comfortably; 300 tenants is a real business.

## 6. Non-negotiables before charging money

1. Daily automated backups with a tested restore (do a restore drill once).
2. HTTPS, password hashing (Django default), 2FA for owner role (allauth).
3. Per-tenant data export (CSV/XLSX) — owners must be able to leave with their data.
4. Soft deletes + audit log — no row ever disappears silently.
5. Terms + privacy page; data stays in-region (Neon/Supabase have Mumbai/Singapore regions).
6. A staging environment that mirrors production (Railway/Render make this a button).

## 7. What *not* to do

- Don't move Streamlit to multi-user with hacks (`st.session_state` auth, one process per tenant).
  It is single-process and re-runs the whole script per interaction — fine for two of you, not for 500.
- Don't start with microservices, Kubernetes or a message broker.
- Don't keep Google Sheets as the system of record past Phase 1; quota (60 req/min/user) and
  write latency will bite at ~20 active tenants.
- Don't build a mobile app before the HTMX pages are mobile-friendly; a home-screen PWA is enough for a year.
