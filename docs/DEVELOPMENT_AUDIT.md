# ESONE development audit — 8 October 2026

Repository baseline: `ff6cc83d1e5499dcbcf81eb376197ec6336e3b43`.

## Website incident

The user's screenshot shows `https://esone.theearthshine.com/**`. The literal `/**` path is not a wildcard in a browser and had no route. A live GET of the root returned 200 and the login page; GET `/login` returned 405. The repair redirects only the literal copied wildcard to `/`, adds GET `/login`, and retains 404 for genuinely unknown URLs. DNS changes are not indicated by the observed root response.

## Implemented in this change

- Correct ESONE branding, responsive login, `/health` and read-only schema readiness check.
- Derived courtesy-call queue: latest completed field visit plus 7 calendar days, one row per salon, due and overdue, India business date.
- Open PTP due today and overdue with amount, promise date, original collection activity date, notes; date and salon/phone filters.
- Visit-history report, activity-only salon timeline and matching filtered XLSX exports.
- Real employee check-in count; unimplemented order/collection metrics no longer display invented zeros.
- Visit ownership enforced on detail/start/OTP endpoints, 200m GPS radius, finite valid coordinates, missing-record handling, repeated check-in/completion rejected.
- Visit fields previously assigned as unmapped Python attributes now use existing mapped columns; notes persist on Activity and verification on VerificationOTP. No new schema is needed for this correction.
- Test OTP disclosure restricted to explicit local `ESONE_ENV=test`. Production returns a clear unavailable response before queuing or storing any OTP when delivery is unconfigured.
- Replace publicly known session-signing secret with `SESSION_SECRET` or process-random fallback; HTTPS cookies on Render. Invalid password hashes/overlong bcrypt inputs return failed verification rather than crash.
- Database error responses omit SQL and credentials. Legacy Render postgres URL normalization and stale-connection checks.
- Automated regression workflow, isolated synthetic database tests.

## Existing versus planned capability

The current phase-1 workbook contains 123 features and no populated user decisions. Suggested NOW is a recommendation, not an approved complete scope. This request authorizes continuing planned development; priority here is existing defects and previously requested courtesy/PTP/export requirements. The larger workbook catalogs 41 modules; blank choices must not be represented as approved selections.

| Module / area | Audit result | Remaining work |
| --- | --- | --- |
| Users / roles | Basic login, user creation, four roles exist | Employee profiles, granular permissions, reset flow |
| CRM / leads | Client create/list exists; activity timeline added | Duplicate handling, scoped assignments, lead lifecycle |
| Field visits | Existing workflow repaired and tested | GPS accuracy, verified checkout GPS, outcomes, assignment UX, one-button suggestions |
| Courtesy calls | Derived due queue and XLSX now built | Persist call outcomes/history; completing a call must clear its due reminder through approved workflow |
| Collections / PTP / telecalling | Models existed; read-only due queue now built | Call entry, PTP entry/update, receipts, posting approvals and complete ledger |
| Demo management | Model only | Booking/calendar/assignment/conversion UI |
| Orders / delivery | Models only | Product/price master, line items, order lifecycle, dispatch/partial delivery |
| OTP / WhatsApp | Local test OTP previously exposed publicly; now guarded | Real provider integration, consent, delivery callbacks, resend limits, durable failed-attempt lockout |
| Command Center | Previously authentication placeholder; operations navigation added | Unified action queues and verified KPI summary |
| Reports / export | Courtesy/PTP/visits filtered XLSX built | Sales/ledger/inventory/employees/distributors/approval exports |
| Inventory / transfers / returns / distributors | No executable module | Schema and workflows |
| Attendance / leave / expenses / targets / performance / beat routes | No executable module | Schema and workflows |
| Approval center / immutable audit | Visit audit records exist; timestamps protected from sequential repeat actions | Governed edit requests, management review, concurrency guarantees |
| Notifications / global search / attachments / imports | Not implemented | Module workflows |
| PWA / offline / live tracking | Mobile HTML only | Installability/offline/sync/tracking, consistent with scope decisions |
| Backup / archive / system settings | No governed automation | Backup/restore plan and configuration |

## Production protection and release status

No production data, users, credentials, schema or infrastructure settings were changed. No automatic initialization, migrations, admin creation or startup seeding was added. Tests use synthetic users and an in-memory SQLite database.

GitHub write access was restored after reconnection. PR #1 passed GitHub Actions and was merged as `846d06c6f71009c648b8f2690bdffb1cec749216`. Render automatic deployment was verified publicly: `/health`, `/login`, and `/health/ready` return 200; the literal `/**` redirects to `/` and loads the login page. No production login or write operations were used for verification.

For future releases: publish the tested commit, observe build status, check `/health`, `/`, `/login` and `/**`, then inspect read-only readiness. If schema setup is needed, prepare an exact migration plan and obtain approval before executing it. Never run `init_db.py`, `create_admin.py`, or `upgrade_*.py` automatically.

## Validation result

24 automated tests passed against the repository's exact pinned dependencies; `pip check` found no broken requirements and `git diff --check` passed. Tests include public URL recovery, unauthenticated redirects, role/ownership denial, latest-visit courtesy dates, PTP date boundaries, matching XLSX filters, HTML/formula escaping, check-in replay, GPS validity/radius, synthetic OTP completion/replay, blocked production test-OTP disclosure, schema readiness and non-mutating read paths. Render deployment and read-only production database schema readiness passed. PostgreSQL write workflows have not been tested against production; authenticated report views were tested with synthetic data only.

Remaining timestamp convention issue: historic local SQLite timestamps and Render server-generated naive timestamps need an agreed timezone/UTC migration strategy before a complete time-based reporting rollout. No historic timestamps were rewritten.
