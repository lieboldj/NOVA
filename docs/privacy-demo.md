# Demo and data flow

NOVA's Cloud SQL database is **not anonymized**. Imported supplier records, email drafts,
original received email text, proposals and approved values remain identifiable. Original
attachments are in the private Cloud Storage evidence bucket. Hosting in Google Cloud
means Google Cloud hosts that original data; restricting the Gemini API is a separate boundary.

1. Import `examples/cloud-demo.csv`, approve the import and start the supplier process.
   Supplier identity and existing values are stored unchanged in NOVA.
2. Approve the test mailbox contact, prepare the request and approve its exact email version.
   Gmail sends the real recipient, subject and request text; outbound requests are not anonymized.
3. Reply to that email, keeping its subject, with:

   ```text
   CLOUD-DEMO-F1=80% recycled aluminium
   CLOUD-DEMO-F2=2028-12-31
   CLOUD-DEMO-F3=Renewable energy confirmed

   The certificate expires on 31 December 2028.
   ```

4. Gmail publishes a mailbox-change notification through Pub/Sub. NOVA authenticates it
   and sends a content-free wake-up signal to n8n. n8n calls NOVA's Gmail sync; NOVA fetches
   and stores the original reply and attachments. n8n receives sync status and opaque IDs,
   not the original email body or attachments.
5. Before extraction, NOVA replaces known supplier/case identifiers and field IDs locally.
   The full extraction bundle (field labels, existing values, rules and email/document text)
   passes through Anymize. Scanned PDF pages may be sent directly to Anymize for OCR and
   anonymization. Anymize is the approved processor allowed to receive sensitive originals.
6. Gemini receives only the selected fields and sources returned from Anymize, with field
   aliases. It proposes the unchanged material confirmation, missing date and energy update.
   A failed or structurally invalid Anymize result stops extraction; originals are not used
   as fallback. Detection still depends on Anymize: this is not proof that every possible
   identifying phrase will always be detected.
7. NOVA restores masked proposal values and evidence through Anymize and local mappings,
   then stores the identifiable results for review. Open **Supplier review** to see the
   entire original reply, attachments and all proposals, including unchanged confirmations.
   Accepted supplier data changes only after human approval; mark the whole reply reviewed.

The masking is reversible pseudonymization for model processing, not permanent database
anonymization. Google Cloud storage, Gmail transport, Anymize processing and Gemini
extraction are distinct data boundaries.
