> Historical planning document, superseded by [cloud-deployment.md](cloud-deployment.md), which
> records what's actually deployed and verified. Kept only for the items below that are still open.

# Remaining work

Everything else this plan originally covered — Anymize/Gemini live validation, n8n connection,
Cloud Run/SQL/Storage/Secret Manager deployment, Gmail integration — is done; see
[cloud-deployment.md](cloud-deployment.md) for what was verified and how to repeat the checks.
Approval gates remain mandatory throughout.

Still open:

- **Individual reviewer sign-in.** The demo uses one shared reviewer token. Production needs
  per-person identity (SSO or similar) resolved server-side before a shared hosted portal accepts
  approvals — never embed the reviewer secret in a public frontend bundle.
- **Task-driven worker (alternative to the continuous worker).** Cloud Run currently runs the
  worker continuously with allocated CPU. A Cloud Tasks → bounded HTTP job-handler design is a
  possible alternative: keep PostgreSQL job records as the source of truth, include a stable job
  ID/generation per task (never dispatch an arbitrary "next job"), split long Anymize/Gemini steps
  into bounded calls so task deadlines and leases hold, and keep the existing idempotency/version/
  approval-digest checks — Cloud Tasks can redeliver, and a retry must never send twice.
  [Cloud Tasks with Cloud Run](https://docs.cloud.google.com/run/docs/triggering/using-tasks),
  [common pitfalls](https://docs.cloud.google.com/tasks/docs/common-pitfalls).
- **Vertex AI as a Gemini alternative.** Not configured; would need its own verification of model
  availability, project permissions, region, auth and response contract — don't assume the current
  API key grants Vertex access, and don't switch models silently.
- **Real detection-quality measurement** for scanned/mixed-page PDFs and indirect identifiers beyond
  known names — the current checks prove the pipeline works end-to-end, not that anonymization
  catches every identifier in an arbitrary real document layout.
- **Dedicated least-privilege service accounts** — the lab project currently reuses its existing
  Editor-scoped compute service account (see the IAM note in cloud-deployment.md).
