# Energy Admin Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build a backend-owned energy product catalog, move redemption authority to the backend, and add a standalone admin web page for managing products.

**Architecture:** Add an `energy_products` table plus backend APIs for public product reads and admin CRUD, then switch the mini program mall to render server data and redeem by `product_id` only. Serve a lightweight admin SPA-like page from FastAPI static assets and protect admin APIs with a dedicated token flow.

**Tech Stack:** FastAPI, SQLAlchemy ORM, Alembic, pytest, WeChat mini program JavaScript, plain HTML/CSS/JS admin page.

---

## File Map

- Create: `faq-backend/app/models/energy_product.py`
- Create: `faq-backend/app/api/v1/admin.py`
- Create: `faq-backend/app/services/admin_auth.py`
- Create: `faq-backend/app/static/admin/index.html`
- Create: `faq-backend/app/static/admin/admin.css`
- Create: `faq-backend/app/static/admin/admin.js`
- Create: `faq-backend/migrations/versions/<new>_create_energy_products.py`
- Create: `faq-backend/scripts/seed_energy_products.py`
- Modify: `faq-backend/app/models/__init__.py`
- Modify: `faq-backend/app/api/v1/router.py`
- Modify: `faq-backend/app/api/v1/energy.py`
- Modify: `faq-backend/app/services/energy.py`
- Modify: `faq-backend/app/core/config.py`
- Modify: `faq-backend/app/main.py`
- Modify: `faq-backend/tests/test_energy_redemptions.py`
- Create: `faq-backend/tests/test_energy_products.py`
- Create: `faq-backend/tests/test_admin_products.py`
- Modify: `faq-miniprogram/pages/energy-mall/index.js`
- Modify: `faq-miniprogram/pages/energy-mall/index.wxml`

### Task 1: Add Product Model And Migration

**Files:**
- Create: `faq-backend/app/models/energy_product.py`
- Modify: `faq-backend/app/models/__init__.py`
- Create: `faq-backend/migrations/versions/<new>_create_energy_products.py`
- Create: `faq-backend/tests/test_energy_products.py`

- [ ] Step 1: Write failing tests for product querying and active filtering
- [ ] Step 2: Add `EnergyProduct` ORM model with unique `product_id`
- [ ] Step 3: Add Alembic migration for `energy_products`
- [ ] Step 4: Run targeted tests for product model behaviors

### Task 2: Make Backend Redemption Authoritative

**Files:**
- Modify: `faq-backend/app/api/v1/energy.py`
- Modify: `faq-backend/app/services/energy.py`
- Modify: `faq-backend/tests/test_energy_redemptions.py`

- [ ] Step 1: Write failing tests proving frontend-forged `cost` and `product_name` are ignored
- [ ] Step 2: Add product lookup and active checks to redemption creation
- [ ] Step 3: Change redemption payload to accept only `client_record_id` and `product_id`
- [ ] Step 4: Return clear business errors for missing, inactive, and insufficient-energy products
- [ ] Step 5: Run redemption test suite

### Task 3: Add Public Product APIs And Seed Script

**Files:**
- Modify: `faq-backend/app/api/v1/energy.py`
- Create: `faq-backend/scripts/seed_energy_products.py`
- Modify: `faq-backend/tests/test_energy_products.py`

- [ ] Step 1: Write failing tests for `GET /api/energy/products`
- [ ] Step 2: Implement grouped product serialization for mini program use
- [ ] Step 3: Add a seed script that imports the current mini program catalog into MySQL
- [ ] Step 4: Run API tests

### Task 4: Add Admin Auth And Product CRUD APIs

**Files:**
- Create: `faq-backend/app/api/v1/admin.py`
- Create: `faq-backend/app/services/admin_auth.py`
- Modify: `faq-backend/app/api/v1/router.py`
- Modify: `faq-backend/app/core/config.py`
- Create: `faq-backend/tests/test_admin_products.py`

- [ ] Step 1: Write failing tests for admin login and protected CRUD endpoints
- [ ] Step 2: Add admin config fields for username, password, and token secret
- [ ] Step 3: Implement admin login and token validation
- [ ] Step 4: Implement list/create/update/toggle product endpoints
- [ ] Step 5: Run admin API tests

### Task 5: Serve Standalone Admin Web Page

**Files:**
- Modify: `faq-backend/app/main.py`
- Create: `faq-backend/app/static/admin/index.html`
- Create: `faq-backend/app/static/admin/admin.css`
- Create: `faq-backend/app/static/admin/admin.js`

- [ ] Step 1: Add a route that serves `/admin/`
- [ ] Step 2: Build login form and product management layout
- [ ] Step 3: Wire the page to admin APIs for login, list, create, edit, and toggle
- [ ] Step 4: Verify the page loads from FastAPI static hosting

### Task 6: Switch Mini Program Mall To Backend Catalog

**Files:**
- Modify: `faq-miniprogram/pages/energy-mall/index.js`
- Modify: `faq-miniprogram/pages/energy-mall/index.wxml`

- [ ] Step 1: Replace hardcoded catalog-as-source-of-truth with fetched product data
- [ ] Step 2: Keep current mall visuals but render server-provided featured and grouped products
- [ ] Step 3: Submit redemption payloads with only `client_record_id` and `product_id`
- [ ] Step 4: Verify the page still handles guest mode, insufficient energy, and success refresh

### Task 7: Verify End-To-End

**Files:**
- Modify as needed: docs or configs discovered during verification

- [ ] Step 1: Run focused backend tests for products, redemptions, and admin APIs
- [ ] Step 2: Run any lightweight local checks for the admin static page
- [ ] Step 3: Smoke-check mini program request payload and response shape
- [ ] Step 4: Document required production env vars: `ADMIN_USERNAME`, `ADMIN_PASSWORD`, `ADMIN_SECRET_KEY`

## Self-Review

- Spec coverage: product table, public product reads, backend authority, admin auth, admin page, and mini program migration all map to explicit tasks above.
- Placeholder scan: the migration filename remains date-based by repo convention; implementation should use the next Alembic revision filename when created.
- Type consistency: `product_id` remains the public business identifier across backend, admin, and mini program.
