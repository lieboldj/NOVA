# Usability review changes

Implemented from the September 2026 usability feedback.

| Feedback | Result |
| --- | --- |
| Unclear inactive email button | Says "Contact saved" when unchanged; a new address enables "Save supplier email." |
| Mandatory/optional, types | Review rows show required/optional, data type, date format, dropdown choices. |
| Need-review prominence | Larger first dashboard card filters to attention-needed cases; "Total requests" removed. |
| "Fields" → "data points" | Labels updated in the UI; database column names unchanged. |
| Clickable agent cards | Open the case's Activity tab (jobs + audit history). |
| Remove manual controls | Connection label, CSV import buttons, Sync inbox, Check due cases removed from the dashboard — scheduled automation still runs behind the scenes. |
| Export by filters | Export CSV lives in the search/filter toolbar; still exports the full dataset. |
| Alert colors | Blue/amber for ordinary alerts; red only when a case's next-action time is actually due. |
| Sortable columns | All review-table headers sort; review defaults to lowest-confidence-first. |
| Status names | "Initiation pending", "Review needed", "Pending supplier" (with elapsed days). |
| Friendlier email copy | More conversational subject/greeting wording. |
| Drop NOVA subject IDs | New drafts omit them; Gmail threading (In-Reply-To/References) handles matching, legacy `[NOVA:...]` still supported. |
| Drop "Demo" from names | Removed from display/search; historical records unchanged. |
| Post-approval state | Approving a draft moves the case to "Pending supplier" immediately; no duplicate cases/jobs on repeat approval. |
| Confidence hint | Above 90% + no validation errors suggests Approve; otherwise Reject — always still a human decision. |
| Read-only received values | Received values can't be edited (backend rejects it too); the old "accepted" column is removed. |
| Required rejection reason | Rejecting requires a free-text reason, prefilled on validation failures, kept with the audit history. |
| Immediate correction email | Rejecting atomically creates one approved correction email with a send job ready right away — no extra approval step or reminder delay. |
| Inline review guidance | A short explainer sits above each reply's review table. |
| Simplified start flow | "Who should receive an MDF request?" — one use case, no preload; a clickable match count reveals results. |

## Notable interpretation calls

- "Confidence approval" = a preselected decision still requiring human submission, not an unattended write — self-reported confidence isn't a calibrated guarantee, and clear format failures suggest rejection regardless of score.
- "How fast the supplier is" = elapsed waiting days (no historical response-speed metric exists).
- Received values stay immutable; the UI explains *requesting a correction* instead of letting reviewers edit them directly.
- "Directly sent" = queued transactionally with no artificial delay, still dependent on a running worker/provider; verified with simulated mail, not live supplier messages.

No schema migration was needed; no live supplier records or email history were rewritten.
