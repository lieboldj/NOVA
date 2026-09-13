# Usability review changes

Implemented from the September 2026 usability feedback.

| Feedback | Result |
| --- | --- |
| Unclear inactive email button | Says "Contact saved" when unchanged; a new address enables "Save supplier email." |
| Mandatory/optional, types | Review rows show required/optional, data type, date format, dropdown choices. |
| Need-review prominence | Compact clickable card without secondary grey text; "Total requests" removed. |
| "Fields" → "data points" | Labels updated in the UI; database column names unchanged. |
| Clickable agent cards | Two cards beside Waiting: Email agent and Reply evaluation agent. Each opens paginated supplier activity, most recent first. |
| Remove manual controls | Connection label, CSV import buttons, Sync inbox, Check due cases removed from the dashboard — scheduled automation still runs behind the scenes. |
| Export by filters | Export CSV lives in the search/filter toolbar; still exports the full dataset. |
| Alert colors | Blue/amber for ordinary alerts; red only when a case's next-action time is actually due. |
| Sortable columns | All review-table headers sort; review defaults to lowest-confidence-first. |
| Status names | "Initiation pending", "Review needed", "Pending supplier" (with elapsed days). |
| Friendlier email copy | Subject: "Your business partner has an information request." Opening: "Let us stay compliant together." Existing generated, pending templates are refreshed too. |
| Drop NOVA subject IDs | New drafts omit them; Gmail threading (In-Reply-To/References) handles matching, legacy `[NOVA:...]` still supported. |
| Drop "Demo" from names | Removed from display/search; historical records unchanged. |
| Post-approval state | Approving a draft moves the case to "Pending supplier" immediately; no duplicate cases/jobs on repeat approval. |
| Confidence hint | Evidence-based score with an explanation: missing 0%, invalid 25%, conflicting 45%, uncertain/partial in between, explicit valid answers up to 97%. Above 90% is accepted automatically; remaining answers need review. |
| Read-only received values | Received values can't be edited (backend rejects it too); the old "accepted" column is removed. |
| Required rejection reason | Rejecting requires a free-text reason, prefilled on validation failures, kept with the audit history. |
| Immediate correction email | Rejecting atomically creates one approved correction email with a send job ready right away — no extra approval step or reminder delay. |
| Inline review guidance | A short explainer sits above each reply's review table. |
| Simplified start flow | "Who should receive an MDF request?" — one use case, no preload; a clickable match count reveals results. |

## Notable interpretation calls

- The later request explicitly authorizes automatic acceptance above 90%. The reply evaluation agent combines model/category confidence, evidence links, format checks, conflicts and data revisions. The score expresses confidence in the answer and category match, not verified real-world compliance. All-clear new replies can complete automatically; replies with missing, unaccounted-for, or ambiguous inputs remain available for human review.
- "How fast the supplier is" = elapsed waiting days (no historical response-speed metric exists).
- Received values stay immutable; the UI explains *requesting a correction* instead of letting reviewers edit them directly.
- "Directly sent" = queued transactionally with no artificial delay, still dependent on a running worker/provider; verified with simulated mail, not live supplier messages.

No schema migration is needed. `python -m nova.review_policy` scores existing pending answers and automatically accepts those that qualify, preserving their original evidence. It refreshes generated unsent templates without sending them, and preserves sent history, custom emails and previous human decisions.

The dashboard hides technical case, supplier, proposal, document and job identifiers and revision counters. Business article references, timestamps and workload counts remain visible. Alerts sits beside Talk to NOVA. Agent totals cover all recorded work; histories paginate rather than silently stopping at the last 500 jobs.

`AUTO_ACCEPT_HIGH_CONFIDENCE=true` enables acceptance by the trusted reply worker. Public automation credentials still cannot call reviewer approval endpoints. Set false to retain manual acceptance while keeping confidence scoring.
