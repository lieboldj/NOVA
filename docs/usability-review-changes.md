# Usability review changes

Implemented from the September 2026 usability feedback.

| Feedback | Result |
| --- | --- |
| Unclear inactive supplier email button | The action says “Contact saved” for an unchanged address, with an explanation. Entering a different address enables “Save supplier email.” |
| Mandatory/optional entries and types | Review rows show the existing required/optional metadata, data type, date format, and configured dropdown choices. Unspecified requirements remain explicitly unspecified. |
| Need review prominent and clickable | Larger first dashboard card filters to cases needing attention. Completed and Waiting cards also filter the list. Total requests removed. |
| Fields → data points | Visible review and request labels use data points; existing database column names stay compatible. |
| Clickable active agents | Agent cards open the associated case’s Activity tab with delivery/evaluation jobs and audit history. |
| Remove connection/import/sync/check controls | Backend connection label, CSV import buttons, Sync inbox, and Check due cases are removed from the dashboard/start flow. Scheduled backend automation continues. |
| Export by filters | Export CSV is in the search/filter toolbar. It continues to export the complete dataset. |
| Talk to NOVA | Right-aligned dashboard action; dashboard title is My Dashboard. |
| Red only for time pressure | Ordinary review and failed-job alerts are blue/amber. Case alerts become red only when their recorded next-action time is due. Workflow tags have distinct colors, including in dark mode. |
| Sort by columns | Request headers and all review-table headers toggle ascending/descending sorting. Review initially sorts by confidence, lowest first; unknown scores come first. |
| Status names | Initiation pending, Review needed, and Pending supplier. Pending supplier includes elapsed days or “sending” before the first delivery. |
| Human email copy | New subjects say “Your business partner has an information request.” New messages begin “Let's stay compliant together.” Greetings and requests use more conversational wording. |
| Remove NOVA subject IDs | New drafts omit IDs. Gmail uses In-Reply-To/References to match replies; legacy subject references remain supported. Ambiguous/unreferenced messages still require manual routing. |
| Remove Demo from supplier names | Standalone “Demo” is removed from displayed names, supplier searches, and new email greetings. Source identities and historical messages remain intact. |
| Waiting record after approval | Email approval immediately moves the existing case to Pending supplier; repeated approval does not duplicate cases or send jobs. |
| Confidence and decision | Model confidence is retained with evidence. Above 90% with no validation errors suggests Approve; 90% or below, unknown confidence, or invalid format suggests Reject. All decisions still require the final human submission. Existing records without scores show Unknown. |
| Received, not Proposed; remove accepted column | Received values are read-only. Backend edit attempts are also rejected. The accepted-value column is removed. Saved supplier data remains available below the review. |
| Rejection explanation | Reject reveals a required free-text reason. Validation failures prefill an explanation. Reasons remain with the original received value and the audit history. |
| Email immediately after rejection | Submitting rejections atomically creates one approved correction email and an immediately available durable send job. No extra email approval or reminder delay applies. Original answers remain unchanged. Actual transmission is performed by the existing worker and mail provider. |
| Review guidance above database | Guidance appears above each reply’s review table, explaining one submission for all decisions and how to request corrections. |
| Simplify start process | Heading is “Who should receive an MDF request?” with one explicit use case, MDF. No NOVA REVIEW label, blue introductory box, CSV button, example button, or preloaded supplier results. Search shows a clickable match count, which reveals compact supplier/article rows. Supplier details return to the preserved search list. |

## Interpretations and remaining uncertainty

- **Confidence approval:** interpreted as preselected decisions for human submission, rather than unattended database writes, because the feedback also requires reviewing every original input and submitting all decisions together. Model confidence is self-reported, not a calibrated guarantee. Clear format failures suggest rejection even at high confidence.
- **“How fast the supplier is”:** interpreted as elapsed waiting days, not a historical response-speed average. The existing model does not provide a historical speed metric.
- **“Edit values” versus “Received cannot be changed”:** prioritized immutable received values. The instruction above the table consequently says “Select Approve or Reject” and explains correction requests instead of telling users to edit received answers.
- **“Remove all results” versus clickable suppliers:** interpreted as hiding the results list until the match count is clicked, while preserving the requested ability to open suppliers and return to the list.
- **Types and requirements:** exposed the existing data definitions; did not invent new mandatory fields or change which data points must be completed to close a case. Date, dropdown, reporting-year, evidence-file, and placeholder checks continue to apply.
- **“Directly sent”:** means queued transactionally without an artificial delay. Transmission still depends on a running worker and a configured provider. Failed or uncertain deliveries remain visible in agent activity. Verification used simulated mail and mocked Gmail, not live supplier messages.
- **Wording corrections:** “an information request” and “Let's stay compliant together” are grammatical interpretations of the supplied text.

Deployment does not rewrite live supplier records or existing email history. Confidence and rejection metadata use the existing evidence JSON, so no database schema migration is required.
