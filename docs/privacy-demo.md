# Demo and data flow

NOVA's Cloud SQL database is **not anonymized** — supplier records, drafts, original email text,
proposals, and approved values stay identifiable there; originals also live in private Cloud
Storage. Google Cloud hosts that original data; restricting the Gemini API is a separate boundary.

1. Import `examples/cloud-demo.csv`, approve it, start the process — identity/values stored as-is.
2. Approve the contact, approve the request email — Gmail sends the real recipient/subject/text
   unanonymized.
3. Reply (keeping the subject) with:
   ```text
   CLOUD-DEMO-F1=80% recycled aluminium
   CLOUD-DEMO-F2=2028-12-31
   CLOUD-DEMO-F3=Renewable energy confirmed

   The certificate expires on 31 December 2028.
   ```
4. Gmail's Pub/Sub notification wakes n8n (a content-free signal); n8n triggers NOVA's own sync,
   which fetches and stores the reply — n8n never sees the body or attachments.
5. NOVA replaces known identifiers locally, then sends the full extraction bundle (labels, existing
   values, rules, email/document text — scanned pages via OCR too) to Anymize, the approved
   processor for sensitive originals. A failed/invalid Anymize result stops extraction; originals
   are never used as a fallback.
6. Gemini receives only Anymize's sanitized fields/sources with aliases, and proposes the unchanged
   confirmation, missing date, and energy update. This is not a guarantee every identifying phrase
   is always caught — detection quality is still bounded by Anymize.
7. NOVA restores real values/evidence for review. **Supplier review** shows the full original reply,
   attachments, and every proposal; approval (`approve-all`) is still required before anything
   becomes accepted data.

This is reversible pseudonymization for model input, not permanent database anonymization —
storage, Gmail transport, Anymize processing, and Gemini extraction are four distinct boundaries.
