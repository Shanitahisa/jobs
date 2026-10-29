# FLIP Gig House — Career Expo 2026 prototype

A locally running gig marketplace using Django REST Framework, React, TypeScript and PostgreSQL. Uses the supplied FLIP logo and a proposed black-and-white visual system. All seeded people, organisations, documents and opportunities are fictional. Sample jobs are not real vacancies.

## Open the app on this machine

- App: http://127.0.0.1:5174/
- Admin: http://127.0.0.1:8001/admin/
- Run `.\start.ps1` from PowerShell to start the local services if they are not already running.

Demo password for every seeded account: `FlipDemo!2026`

| Account | Email |
|---|---|
| Employer | employer@flip.demo |
| Worker / photographer | amina@flip.demo |
| Other photographer (weekday availability) | daniel@flip.demo |
| Graphic designer | sarah@flip.demo |
| Web developer | brian@flip.demo |
| Event assistant | joan@flip.demo |
| Accountant | moses@flip.demo |
| Administrator | admin@flip.demo |

Landing-page demo buttons sign in as the employer or Amina. Sign out using the bottom-left account row to switch roles. The admin account is used at the separate Django admin login.

## Install on another machine

Requires Python 3.12+, Node.js 20.19+ and optionally PostgreSQL. The existing virtual environment is machine-specific and must not be copied as an installation method.

```powershell
python -m venv venv
.\venv\Scripts\python.exe -m pip install -r requirements.txt
Copy-Item .env.example .env
# Edit .env: use your PostgreSQL credentials, or leave POSTGRES_DB empty for SQLite.
.\venv\Scripts\python.exe manage.py migrate
.\venv\Scripts\python.exe manage.py seed_demo
cd frontend
npm install
npm run build
```

Run the backend in one terminal and frontend in another:

```powershell
.\venv\Scripts\python.exe manage.py runserver 127.0.0.1:8001
```

```powershell
cd frontend
npm run dev
```

The PostgreSQL cluster on the original machine is isolated under ignored `.runtime/postgres-live`, listens only on `127.0.0.1:55432`, and has database `flip`. Local credentials are in ignored `.env`. Do not commit `.env`, media, runtime database files or tokens. These are local development services, not a production deployment.

## Implemented

- Worker and employer registration, validated passwords, sign-in and token authentication.
- Worker profiles with professions, skill checklists, custom skills, profession-specific experience, overall experience, situation, work preferences, availability, portfolio links, projects and work history.
- Profile drafts and required-field checks before discoverability.
- Private CV/certificate/clearance uploads, owner/admin downloads and expiry-aware verification.
- CV suggestions from text-based PDF/TXT files, explicitly reviewed before saving.
- Employer business profile, registration/licence uploads, submission and admin approval. Material edits require reapproval.
- Gig, full-time, part-time and internship opportunities, required/preferred skills, dates, budget and deliverables. Offers and acceptance support all four work types; managed payments and delivery workflows apply to gigs. Other accepted offers record a confirmed hire, with payroll outside this prototype.
- Deterministic, explained matching; filters; no-match explanations; shortlists; confirmed expressions of interest.
- Gig offers with snapshots of agreed amount, deliverables and dates; acceptance; coarse conflict checks; submission; revision requests; approval; dispute flagging; cancellation before acceptance.
- Clearly labelled simulated funding/payout, plus Flutterwave v3 test-mode checkout, collection verification, Uganda mobile-money payout initiation and payout verification.
- Separate collection and payout records, duplicate-action guards, private worker payout settings, and refusal to use live Flutterwave keys.
- Two-sided reviews after completion. Each review is private until both participants submit.
- Django administration for businesses, documents, opportunities, disputed engagements and read-only payment records.
- Six fictional worker profiles, one fictional approved business and four gigs.

## Four-minute demonstration

1. Open the app and choose **Explore as employer**.
2. Open **Discover talent**, select **Capture the energy. Event photographer.**
3. Open Amina's profile. Show matching skills, Kampala location and weekend availability. Daniel has the skills but is only available weekdays.
4. Shortlist Amina. Sign out and explore as worker. Open the photography opportunity and express interest, confirming availability.
5. Return as employer to **My shortlist**. Amina now shows **Interested**. Open her profile and send the gig offer.
6. Switch to Amina, open **My gigs**, accept. Switch to employer and **Simulate funding**. Switch to Amina and submit fictional delivery notes. Employer approves and **Simulate payout**. No real money moves.
7. Each participant leaves a review. Show that it is shared once both have reviewed.
8. Return to talent matching, edit the photography gig, and add an essential skill such as **Underwater photography** using Other required skill. Save. Show the no-match state and specific missing-skill explanation. Remove the extra requirement afterward if needed.

Business-verification demonstration: register a fresh employer, fill business details, upload fictional TXT/PDF registration and licence documents, submit, then approve the business through Django admin. Never use genuine identity, business or medical documents during the expo.

## Matching rules

Eligibility requires the selected profession, every essential skill, the worker's selected work type, sufficient relevant experience, requested availability, the same location for on-site work, and any explicitly required verified and unexpired certification or clearance. Accepted/funded/submitted/approved engagements block overlapping dates. `Immediately` means unrestricted availability in this simplified prototype; `Flexible` opportunities accept all availability labels. Location matching is case-insensitive exact text. Skills use case-insensitive exact terms.

Score: required skill coverage 60%, availability fit 20%, location/remote fit 10%, relevant experience 10%. Eligible candidates appear first; preferred skills break ties. Because all these dimensions are strict eligibility checks, fully eligible candidates normally receive 100; the score describes requirement coverage rather than quality or probability of success. Explanations and missing requirements matter more than numerical ranking. No sensitive medical information is used in scoring. The employer makes the hiring decision.

Limitations: no semantic skill inference, travel-radius matching, calendar/time-zone planning, verified skill assessment, production background checks or guarantee of suitability. Custom skills are supported but there is no custom-skill moderation queue yet. Reviews do not influence ranking. CV parsing uses simple rules, supports text PDFs/TXT, has no OCR/DOCX support and can infer the wrong profession; every suggestion must be checked. Overall experience is used when a profession has no separate experience value.

## Flutterwave sandbox

The app works with simulations immediately. To enable actual provider test requests:

1. Set `FLUTTERWAVE_SECRET_KEY` in `.env` to your own **v3 TEST secret key**. Never paste it into chat or put it in React code.
2. Restart Django. The **Flutterwave sandbox** button appears after the worker accepts a gig.
3. Complete provider checkout using Flutterwave's documented test payment details. Return to the app; Django verifies transaction reference, amount, currency and success status directly with Flutterwave before confirming collection.
4. Worker saves fictional sandbox mobile-money beneficiary details in **My gigs → Sandbox payout details**.
5. After employer approval, employer can initiate a sandbox payout. Refresh its status to verify completion; only a matching successful provider response completes the gig.

Sandbox transfers depend on account transfer permissions, supported test rails and test wallet balance. Initiation is not completion. A timeout leaves a reconciliation-required record and prevents a blind duplicate payout. The prototype supports manual status verification, not production webhook processing, refunds, escrow, automatic settlements or live funds. Admin must reconcile ambiguous/failed transfers with the provider before further action. Provider fees are external; the prototype charges no platform commission.

Official references:
- https://developer.flutterwave.com/docs/transaction-verification
- https://developer.flutterwave.com/docs/uganda-3
- https://developer.flutterwave.com/docs/split-payments

## Checks

```powershell
.\venv\Scripts\python.exe manage.py check
.\venv\Scripts\python.exe manage.py test marketplace
cd frontend
npm run build
```

Automated coverage includes the cross-role core journey, persistence, no-match results, required fields, private downloads, CV draft review, business-verification gating, review privacy, duplicate payment actions, clearance expiry and mocked Flutterwave collection/payout verification. Mocked provider tests do not establish that a real Flutterwave account is configured correctly.

## Before production

Replace demo users/credentials, disable simulations, configure HTTPS and production authentication/token handling, implement email/phone verification and password recovery, scan uploads, add retention/access auditing, confirm profession-specific document policies, add robust payment webhooks/reconciliation/refunds and appropriate dispute handling. The current medical-clearance feature is a private fictional evidence workflow, not a medical-record system. Business approval is a demo review process, not a regulatory guarantee. Never expose local development servers as a live marketplace.

## Latest prototype updates

- Project images: My profile → Edit profile → Projects & portfolio → Add project image. Up to six JPG/PNG/WebP images per project, 5 MB each, displayed on worker and employer profile views. Uploads are validated/re-encoded; save the profile to attach them. Unpublished/unattached images are visible only to the owner/admin.
- Optional skill certificates: My profile → Skills & professions → expand Skill certificates under a profession. Add evidence against any checked skill. A certificate is never required just to add a skill. General Documents upload also has an optional skill selector. Files remain private; employers see verified credential status.
- Worker My interests and employer Interested talent list all relevant expressions of interest, with opportunity and message. Shortlists now aggregate all opportunities, with per-opportunity filtering.
- Every overview summary card opens its corresponding filtered list.
- Employer industry choices use the same profession-category catalog as workers.
- Registration requires matching password confirmation, 8–128 characters, uppercase, lowercase, number, special character, no whitespace, plus server checks for common passwords and similarity to name/email.
- Sign out is visible in the header and account row for every app role. It clears all local account data immediately, revokes server tokens, clears the web session, synchronises sign-out across tabs and prevents stale requests from restoring the previous account. If the server is unreachable, the app reports that only local sign-out could be confirmed.

## Notifications and Gmail SMTP

The bell and Notifications page show a private inbox, refreshed every 15 seconds. Users can mark updates read/unread, filter categories and manage opportunity, activity, payment and email preferences. Browser alerts require permission and work only while an app tab is running.

Matching opportunities, interest/withdrawals, shortlists, offers, acceptance, work submission/revisions/approval, completion, payments, verification, expiring documents, disputes and reviews generate relevant notifications. Updated or closed opportunities also alert interested workers. Alerts are created after successful transaction commits and match alerts are deduplicated. Raw CVs, medical details and hidden reviews are never included.

### Gmail configuration in .env

```dotenv
EMAIL_HOST=smtp.gmail.com
EMAIL_PORT=587
EMAIL_HOST_USER=your-account@gmail.com
EMAIL_HOST_PASSWORD=your-google-app-password
EMAIL_USE_TLS=1
EMAIL_USE_SSL=0
EMAIL_SENDER_NAME=Gig House
EMAIL_REPLY_TO=
EMAIL_ENABLED=1
FRONTEND_URL=http://127.0.0.1:5174
```

Enable Google 2-Step Verification and create an App Password for this app. Use that App Password, not the normal Google sign-in password. App Password availability can depend on your account or organisation policy. The default sender is the authenticated account; set DEFAULT_FROM_EMAIL only if you have configured an approved send-as alias. Keep credentials in ignored .env, never in React or source control. For a deployed app, set FRONTEND_URL to the real HTTPS address.

Port 587 uses STARTTLS with certificate verification. Alternatively use EMAIL_PORT=465, EMAIL_USE_TLS=0 and EMAIL_USE_SSL=1 for implicit TLS. Exactly one secure transport must be enabled; plaintext authentication is refused. Email settings are read into non-deprecated internal settings so they work with this machine's Django 6.1 MAILERS configuration.

After editing .env run `.\restart.ps1`. This restarts Django and the notification worker, while leaving PostgreSQL and the frontend running. Start the app with `.\start.ps1`. To run or inspect the queue manually:

```powershell
.\venv\Scripts\python.exe manage.py notification_worker --interval 10
# Or process one batch and exit:
.\venv\Scripts\python.exe manage.py notification_worker --once
```

Sign in with your real email and use Notifications → Send me a test email. This queues only to the signed-in account. Development checks use mocked SMTP and send no actual test email. Fictional .demo/.test/.invalid/.example and example.com addresses are suppressed automatically. Existing match alerts can be safely backfilled with `manage.py sync_notifications`.

### Queue reliability

EmailDelivery is a persistent outbox. The worker locks and claims records, rechecks preferences and connects securely to Gmail SMTP. Missing credentials leave messages queued without disrupting in-app alerts. Accepted means Gmail accepted the SMTP message; it does not guarantee inbox delivery. The recorded ID is the email's RFC Message-ID, not a Gmail delivery receipt.

Connection failures before sending and explicit temporary SMTP rejections retry with backoff, up to five attempts. Authentication and permanent rejections fail with a safe error that never includes credentials. An ambiguous timeout after message sending starts is marked uncertain and is never automatically resent. Interrupted sends become uncertain after five minutes. Admin can retry confirmed failed sends after checking the sending account; uncertain sends require reconciliation to avoid duplicate email. Delivery/bounce webhooks are not implemented.

The expiry scanner runs at startup and hourly. Queue logs are in .runtime/notifications.log and .runtime/notifications-error.log. Email templates escape user content and link back to the app. The custom smiling-house SVG appears beside FLIP and as the favicon.

### Landing page

The signed-out landing page has no footer, ticker or bottom demo strip. Its navigation, hero copy and photographer image fit a single viewport, with compact responsive layouts for phones and short landscape screens. Demo sign-ins remain available through the Sign in dialog. Authenticated pages and dialogs keep their normal scrolling.

Google setup references:
- https://support.google.com/mail/answer/7104828
- https://support.google.com/accounts/answer/185833
- https://developers.google.com/workspace/gmail/imap/imap-smtp

### Profiles, work delivery, payments and system administration

Users can add or remove a profile photo from their account avatar. Workers can edit their profile, choose a unique public address and publish a shareable `/talent/<address>/` page. The public page includes their introduction, skills, portfolio projects, experience and verified credential metadata. Email addresses, CVs and private credential files are excluded. Unpublishing the profile or suspending the account removes public access.

For an in-progress gig, select Submit completed work. Add delivery notes, up to 10 HTTP/HTTPS links and up to 10 files per submission. Images accept JPG, PNG or WebP up to 5 MB; documents accept PDF, DOCX or TXT up to 10 MB. Uploaded drafts are private to the worker and system admins until submitted. Submitted files are accessible only to the engagement participants and admins. Each submission creates a separate revision record; requesting changes preserves previous deliveries.

Payments is a separate navigation page with agreement totals, next actions, payout details, transaction filters and downloadable payment records. Flutterwave remains in sandbox mode. Local test funding and payout actions are clearly labelled in this page; these records are not receipts for actual transferred money. General screens no longer repeat prototype/fiction notices. Never use test records to claim that a live payment occurred.

Sign in to the main React app as `admin@flip.demo` with password `FlipDemo!2026` to open System admin. This dashboard supports business verification, credential review, account suspension/restoration, opportunity moderation, delivery inspection, dispute workflow resolution, payment inspection and email queue review. Confirmed failed emails can be retried; uncertain sends require reconciliation. Admin decisions require reasons where appropriate and are recorded in an audit log. Admin dispute actions do not release money. Staff accounts cannot be suspended from this dashboard. The existing Django admin remains available at port 8001 `/admin/`.

Apply migrations when updating an existing checkout: `python manage.py migrate`. The backend suite includes access-control checks for public profiles, profile photos, private submission files, admin permissions, payment visibility and dispute funding safeguards. The interface source is in `frontend/src/`; the build output is in `frontend/dist/`.

### Welcome emails and people search

Registration normalises email addresses to lowercase and queues one welcome notification/email in the same account-creation transaction. Existing profile-created welcome events share the same idempotency key, preventing duplicate welcome emails. The durable worker sends through the configured Gmail SMTP account; missing credentials leave delivery queued. Configure Gmail in .env and restart as documented above. Configuration details are no longer shown in the Notifications screen.

Account email addresses are case-insensitively unique, enforced both in registration validation and by a database index. Migration 0008 checks for existing duplicate emails before adding the index and never deletes accounts. Login resolves the email address to the account's actual username, including admin-created users.

Signed-in users can open People to search active members by name, profession, business or location and view a profile. Published worker details and approved business information appear in the profile view. Unpublished profiles expose only basic directory details; private documents, email addresses, delivery files and medical records remain excluded. Suspended accounts are not searchable. Results show up to 60 members per search.
