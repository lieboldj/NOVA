import React, { useCallback, useEffect, useRef, useState } from "react";
import { api, dateLabel } from "./api";
import { Modal, Notice, StatusBadge } from "./components";

function EmailReview({ draft, caseId, config, busy, act }) {
  const [subject, setSubject] = useState(draft.subject);
  const [body, setBody] = useState(draft.body);
  const dirty = subject !== draft.subject || body !== draft.body;
  const editable = ["pending", "approved"].includes(draft.status);
  const allowed =
    config.mail_mode !== "gmail" ||
    draft.recipient.toLowerCase() === config.gmail_supplier.toLowerCase();
  const reference = subject.includes(`[NOVA:${caseId}]`);
  return (
    <article
      className="review-card"
      data-testid="email-review"
      data-review-dirty={dirty}
    >
      <div className="review-heading">
        <strong>
          {draft.kind === "request"
            ? "Information request"
            : draft.kind === "reminder"
              ? "Reminder"
              : "Follow-up"}
        </strong>
        <StatusBadge status={draft.status} />
      </div>
      <p className="muted">
        From: {config.gmail_mailbox} · To: <strong>{draft.recipient}</strong>
      </p>
      <p className="muted">
        Version {draft.version} · {dateLabel(draft.created_at)}
      </p>
      <label className="field-label">
        Subject
        <input
          aria-label="Email subject"
          value={subject}
          disabled={!editable || busy}
          onChange={(e) => setSubject(e.target.value)}
        />
      </label>
      <label className="field-label">
        Email body
        <textarea
          aria-label="Email body"
          rows={10}
          value={body}
          disabled={!editable || busy}
          onChange={(e) => setBody(e.target.value)}
        />
      </label>
      {editable && (
        <>
          {!allowed && (
            <Notice error>
              This contact is outside the configured Gmail test supplier.
              Approve the correct case contact before drafting again.
            </Notice>
          )}
          {!reference && (
            <Notice error>
              Keep [NOVA:{caseId}] in the subject so supplier replies can be
              matched.
            </Notice>
          )}
          {dirty && (
            <Notice>
              Save your edits, then review the new version before approval.
            </Notice>
          )}
          <div className="drawer-actions">
            <button
              className="secondary-btn"
              disabled={
                busy || !dirty || !subject.trim() || !body.trim() || !reference
              }
              onClick={() =>
                act(
                  () =>
                    api(`/drafts/${draft.id}`, {
                      method: "PATCH",
                      body: { version: draft.version, subject, body },
                    }),
                  "New email version saved. Review it before approval.",
                )
              }
            >
              Save email edits
            </button>
            <button
              className="secondary-btn"
              disabled={busy || dirty}
              onClick={() =>
                act(
                  () =>
                    api(`/drafts/${draft.id}/reject`, {
                      method: "POST",
                      body: { version: draft.version },
                    }),
                  "Email rejected. Case paused.",
                )
              }
            >
              Reject email
            </button>
            {draft.status === "pending" && (
              <button
                className="primary-btn"
                disabled={busy || dirty || !allowed || !reference}
                onClick={() =>
                  act(
                    () =>
                      api(`/drafts/${draft.id}/approve`, {
                        method: "POST",
                        body: { version: draft.version },
                      }),
                    config.mail_mode === "simulation"
                      ? "Email approved for simulated delivery."
                      : "Email approved and queued for delivery.",
                  )
                }
              >
                Approve email &amp; send
              </button>
            )}
          </div>
        </>
      )}
      {draft.status === "uncertain" && (
        <Reconcile draft={draft} act={act} busy={busy} />
      )}
      {draft.provider_id && (
        <p className="muted">Delivery reference: {draft.provider_id}</p>
      )}
    </article>
  );
}

function Reconcile({ draft, busy, act }) {
  const [outcome, setOutcome] = useState("");
  const [note, setNote] = useState("");
  const [provider, setProvider] = useState("");
  const [sentAt, setSentAt] = useState("");
  return (
    <div>
      <Notice error>
        Delivery is uncertain. Check Gmail Sent before deciding. Retrying
        without checking could send a duplicate.
      </Notice>
      <label className="field-label">
        Confirmed outcome
        <select value={outcome} onChange={(e) => setOutcome(e.target.value)}>
          <option value="">Choose after checking Gmail</option>
          <option value="sent">Email was sent</option>
          <option value="not_sent">Email was not sent</option>
        </select>
      </label>
      <label className="field-label">
        Verification note
        <input value={note} onChange={(e) => setNote(e.target.value)} />
      </label>
      {outcome === "sent" && (
        <>
          <label className="field-label">
            Gmail message ID
            <input
              value={provider}
              onChange={(e) => setProvider(e.target.value)}
            />
          </label>
          <label className="field-label">
            Sending time (your local timezone)
            <input
              type="datetime-local"
              value={sentAt}
              onChange={(e) => setSentAt(e.target.value)}
            />
          </label>
        </>
      )}
      <button
        className="secondary-btn"
        disabled={
          busy ||
          !outcome ||
          note.length < 5 ||
          (outcome === "sent" && (!provider || !sentAt))
        }
        onClick={() =>
          act(
            () =>
              api(`/drafts/${draft.id}/reconcile`, {
                method: "POST",
                body: {
                  version: draft.version,
                  outcome,
                  note,
                  ...(outcome === "sent"
                    ? {
                        provider_id: provider,
                        sent_at: new Date(sentAt).toISOString(),
                      }
                    : {}),
                },
              }),
            "Delivery outcome recorded.",
          )
        }
      >
        Confirm checked outcome
      </button>
    </div>
  );
}

function ProposalReview({ proposal, field, busy, act }) {
  const [value, setValue] = useState(proposal.value);
  const dirty = value !== proposal.value;
  const pending = proposal.status === "pending";
  const unchanged = proposal.value === proposal.old_value;
  return (
    <article
      className="review-card"
      data-testid="proposal-review"
      data-review-dirty={dirty}
    >
      <div className="review-heading">
        <strong>{field?.data["Field (label)"] || proposal.field_id}</strong>
        <StatusBadge status={proposal.status} />
      </div>
      <p className="muted">
        {proposal.field_id} · Version {proposal.version}
      </p>
      <p className="muted">
        {unchanged
          ? "Unchanged confirmation"
          : proposal.old_value
            ? "Changed value"
            : "New value"}
      </p>
      <div className="value-comparison">
        <div>
          <span className="muted">Previous accepted value</span>
          <p>{proposal.old_value || "(empty)"}</p>
        </div>
        <div>
          <span className="muted">Current accepted value</span>
          <p>{field?.data["Value submitted"] || "(empty)"}</p>
        </div>
      </div>
      <label className="field-label">
        Proposed value
        <textarea
          aria-label="Proposed value"
          rows={3}
          value={value}
          disabled={!pending || busy}
          onChange={(e) => setValue(e.target.value)}
        />
      </label>
      <p>{proposal.rationale}</p>
      <blockquote>{proposal.evidence?.quote}</blockquote>
      <p className="muted">
        Evidence: {proposal.evidence?.source_id}
        {proposal.evidence?.page ? ` · Page ${proposal.evidence.page}` : ""}
      </p>
      {proposal.evidence?.document_id && (
        <a href={`/api/documents/${proposal.evidence.document_id}`}>
          Download source attachment
        </a>
      )}
      {!!proposal.validation_errors?.length && (
        <Notice error>{proposal.validation_errors.join("; ")}</Notice>
      )}
      {pending && (
        <div className="drawer-actions">
          <button
            className="secondary-btn"
            disabled={busy || !dirty || !value.trim()}
            onClick={() =>
              act(
                () =>
                  api(`/proposals/${proposal.id}`, {
                    method: "PATCH",
                    body: { version: proposal.version, value },
                  }),
                "Proposal saved. Review the new version before approval.",
              )
            }
          >
            Save proposed value
          </button>
          <button
            className="secondary-btn"
            disabled={busy || dirty}
            onClick={() =>
              act(
                () =>
                  api(`/proposals/${proposal.id}/reject`, {
                    method: "POST",
                    body: { version: proposal.version },
                  }),
                "Supplier value rejected.",
              )
            }
          >
            {unchanged ? "Reject confirmation" : "Reject change"}
          </button>
          <button
            className="primary-btn"
            disabled={busy || dirty || !!proposal.validation_errors?.length}
            onClick={() =>
              act(
                () =>
                  api(`/proposals/${proposal.id}/approve`, {
                    method: "POST",
                    body: { version: proposal.version },
                  }),
                "Approved value written to the database.",
              )
            }
          >
            {unchanged ? "Approve confirmation" : "Approve data change"}
          </button>
        </div>
      )}
    </article>
  );
}

function SupplierReplyReview({
  message,
  proposals,
  fields,
  busy,
  act,
  showProposals = true,
}) {
  const pending = proposals.some((p) => p.status === "pending");
  return (
    <article className="review-card" data-testid="supplier-reply-review">
      <div className="review-heading">
        <strong>{message.sender}</strong>
        <StatusBadge status={message.status} />
      </div>
      <p className="muted">Received {dateLabel(message.created_at)}</p>
      <h3>Complete supplier reply</h3>
      <pre className="email-text">
        {message.body || "(No email text; see attachments below.)"}
      </pre>
      <h3>All attachments ({message.documents.length})</h3>
      {message.documents.length ? (
        message.documents.map((d) => (
          <p key={d.id}>
            <a href={`/api/documents/${d.id}`}>{d.filename}</a>
          </p>
        ))
      ) : (
        <p className="muted">No attachments received.</p>
      )}
      {showProposals && (
        <>
          <h3>Extracted supplier values ({proposals.length})</h3>
          {!proposals.length && (
            <p className="muted">
              No extracted values are available for this reply. Review the full
              text and every attachment, including information that could not be
              matched to a field.
            </p>
          )}
          {proposals.map((p) => (
            <ProposalReview
              key={`${p.id}:${p.version}`}
              proposal={p}
              field={fields.find((f) => f.id === p.field_id)}
              busy={busy}
              act={act}
            />
          ))}
        </>
      )}
      {["needs_review", "evaluated", "failed"].includes(message.status) && (
        <>
          <p className="muted">
            Check the complete reply and every attachment, including unchanged
            values and additional information. Decide all extracted values for
            this reply before completing its review.
          </p>
          <button
            className="secondary-btn"
            disabled={busy || pending}
            onClick={() =>
              act(
                () =>
                  api(`/messages/${message.id}/review-complete`, {
                    method: "POST",
                  }),
                "Reply review completed.",
              )
            }
          >
            Complete reply review
          </button>
        </>
      )}
    </article>
  );
}

export default function CaseDrawer({
  caseId,
  config,
  initialTab,
  onClose,
  onChanged,
}) {
  const [data, setData] = useState(null);
  const [tab, setTab] = useState(initialTab || "email");
  const [error, setError] = useState("");
  const [notice, setNotice] = useState("");
  const [busy, setBusy] = useState(false);
  const [recipient, setRecipient] = useState("");
  const generation = useRef(0);
  const first = useRef(true);
  const actionLock = useRef(false);
  const load = useCallback(async () => {
    const ticket = ++generation.current;
    const [detail, drafts, proposals, messages, jobs, activity] =
      await Promise.all([
        api(`/cases/${caseId}`),
        api(`/drafts?case_id=${caseId}`),
        api(`/proposals?case_id=${caseId}`),
        api(`/cases/${caseId}/messages`),
        api(`/jobs?case_id=${caseId}`),
        api(`/cases/${caseId}/activity`),
      ]);
    if (ticket !== generation.current) return;
    setData({ detail, drafts, proposals, messages, jobs, activity });
    if (first.current) {
      setRecipient(detail.recipient);
      if (
        !initialTab &&
        (proposals.some((p) => p.status === "pending") ||
          messages.some((m) => m.status !== "reviewed"))
      )
        setTab("data");
      first.current = false;
    }
  }, [caseId, initialTab]);
  useEffect(() => {
    load().catch((e) => setError(e.message));
    return () => {
      generation.current++;
    };
  }, [load]);
  useEffect(() => {
    if (busy) return;
    const timer = setInterval(() => {
      if (!document.querySelector('[data-review-dirty="true"]'))
        load().catch((e) => setError(e.message));
    }, 10000);
    return () => clearInterval(timer);
  }, [load, busy]);
  async function act(work, success) {
    if (actionLock.current) return;
    actionLock.current = true;
    setBusy(true);
    setError("");
    setNotice("");
    try {
      await work();
      setNotice(success);
      await load();
      await onChanged();
    } catch (e) {
      setError(e.message);
      if (e.status === 409) await load().catch(() => {});
    } finally {
      setBusy(false);
      actionLock.current = false;
    }
  }
  const detail = data?.detail;
  const activeDraft = data?.drafts.some((d) =>
    ["pending", "approved", "sending", "uncertain"].includes(d.status),
  );
  const pendingProposals = data?.proposals.some((p) => p.status === "pending");
  const blockedReply = data?.messages.some((m) =>
    ["queued", "processing", "failed", "needs_review", "evaluated"].includes(
      m.status,
    ),
  );
  return (
    <Modal
      title={detail?.supplier_name || "Loading case…"}
      subtitle={detail ? `Article ${detail.nart} · ${detail.id}` : caseId}
      onClose={onClose}
      busy={busy}
    >
      <Notice error>{error}</Notice>
      <Notice>{notice}</Notice>
      {!data ? (
        <p>Loading case details…</p>
      ) : (
        <>
          <div className="detail-status">
            <StatusBadge status={detail.status} />
            <span className="muted">
              {detail.supplier_id} · Revision {detail.revision}
            </span>
          </div>
          <div
            className="review-tabs"
            role="tablist"
            aria-label="Case review sections"
          >
            {[
              ["email", "Email"],
              ["data", "Supplier review"],
              ["replies", "Replies"],
              ["activity", "Activity"],
            ].map(([id, label]) => (
              <button
                role="tab"
                aria-selected={tab === id}
                key={id}
                onClick={() => setTab(id)}
                className={tab === id ? "active" : ""}
              >
                {label}
                {id === "data" && (pendingProposals || blockedReply)
                  ? " •"
                  : ""}
              </button>
            ))}
          </div>
          {tab === "email" && (
            <>
              <form
                className="review-card"
                onSubmit={(e) => {
                  e.preventDefault();
                  act(
                    () =>
                      api(`/cases/${caseId}/contact/approve`, {
                        method: "POST",
                        body: { revision: detail.revision, recipient },
                      }),
                    "Supplier contact approved. Previous drafts invalidated.",
                  );
                }}
              >
                <label className="field-label">
                  Supplier email
                  <input
                    aria-label="Supplier email"
                    type="email"
                    required
                    value={recipient}
                    disabled={busy}
                    placeholder={config.gmail_supplier}
                    onChange={(e) => setRecipient(e.target.value)}
                  />
                </label>
                <button
                  className="secondary-btn"
                  disabled={
                    busy || !recipient || recipient === detail.recipient
                  }
                >
                  Approve contact
                </button>
              </form>
              {!activeDraft && detail.status !== "closed" && (
                <div className="review-card">
                  <p>
                    Create an email draft for the remaining supplier
                    information.
                  </p>
                  <button
                    className="primary-btn"
                    disabled={
                      busy ||
                      !detail.recipient ||
                      pendingProposals ||
                      blockedReply
                    }
                    onClick={() =>
                      act(
                        () => api(`/cases/${caseId}/draft`, { method: "POST" }),
                        "Draft created. Review it before sending.",
                      )
                    }
                  >
                    Create email draft
                  </button>
                  {(pendingProposals || blockedReply) && (
                    <p className="muted">
                      Complete reply and data review before drafting the next
                      email.
                    </p>
                  )}
                </div>
              )}
              {!data.drafts.length && (
                <p className="empty">No email drafts yet.</p>
              )}
              {data.drafts.map((d) => (
                <EmailReview
                  key={`${d.id}:${d.version}`}
                  draft={d}
                  caseId={caseId}
                  config={config}
                  busy={busy}
                  act={act}
                />
              ))}
            </>
          )}
          {tab === "data" && (
            <>
              <Notice>
                Review every supplier reply and attachment, including unchanged
                confirmations and information without an extracted value.
                Approve or reject extracted values, then complete each reply
                review. Email sending is approved separately.
              </Notice>
              {!config.anymize_configured && config.ai_mode !== "fixture" && (
                <Notice>
                  Extraction is waiting for Anymize setup. Complete supplier
                  inputs remain available below.
                </Notice>
              )}
              {!data.messages.length && (
                <p className="empty">
                  No supplier replies received for this case yet.
                </p>
              )}
              {data.messages.map((m) => (
                <SupplierReplyReview
                  key={m.id}
                  message={m}
                  proposals={data.proposals.filter(
                    (p) => p.message_id === m.id,
                  )}
                  fields={detail.fields}
                  busy={busy}
                  act={act}
                />
              ))}
              <details className="review-card">
                <summary>
                  Accepted supplier fields ({detail.fields.length})
                </summary>
                <div className="field-list">
                  {detail.fields.map((f) => (
                    <div key={f.id}>
                      <strong>{f.data["Field (label)"]}</strong>
                      <span>{f.data.Status}</span>
                      <p>{f.data["Value submitted"] || "(empty)"}</p>
                    </div>
                  ))}
                </div>
              </details>
            </>
          )}
          {tab === "replies" && (
            <>
              {!config.anymize_configured && config.ai_mode !== "fixture" && (
                <Notice>
                  Reply evaluation is waiting for Anymize setup. Emails and
                  attachments remain available for review.
                </Notice>
              )}
              {!data.messages.length && (
                <p className="empty">
                  No supplier replies ingested for this case.
                </p>
              )}
              {data.messages.map((m) => (
                <SupplierReplyReview
                  key={m.id}
                  message={m}
                  proposals={data.proposals.filter(
                    (p) => p.message_id === m.id,
                  )}
                  fields={detail.fields}
                  busy={busy}
                  act={act}
                  showProposals={false}
                />
              ))}
            </>
          )}
          {tab === "activity" && (
            <>
              <h3>Delivery and evaluation jobs</h3>
              {!data.jobs.length && <p>No jobs for this case yet.</p>}
              {data.jobs.map((j) => (
                <article className="review-card" key={j.id}>
                  <div className="review-heading">
                    <strong>
                      {j.kind === "send"
                        ? "Email delivery"
                        : "Reply evaluation"}
                    </strong>
                    <StatusBadge status={j.status} />
                  </div>
                  <p className="muted">
                    {dateLabel(j.available_at)} · Attempts: {j.attempts}
                  </p>
                  <Notice error>{j.error}</Notice>
                  {j.status === "failed" &&
                    (j.kind === "evaluate" ||
                      data.drafts.some(
                        (d) => d.id === j.target_id && d.status === "approved",
                      )) && (
                      <button
                        className="secondary-btn"
                        disabled={busy}
                        onClick={() =>
                          act(
                            () =>
                              api(`/jobs/${j.id}/retry`, { method: "POST" }),
                            "Job queued for retry.",
                          )
                        }
                      >
                        Retry job
                      </button>
                    )}
                </article>
              ))}
              <h3>Audit history</h3>
              {!data.activity.length && <p>No case activity recorded yet.</p>}
              {data.activity.map((a) => (
                <div className="activity-item" key={a.id}>
                  <span className="timeline-dot" />
                  <span>
                    {a.action.replaceAll(".", " · ")}
                    <small>
                      {dateLabel(a.at)} · {a.actor}
                    </small>
                  </span>
                </div>
              ))}
            </>
          )}
        </>
      )}
    </Modal>
  );
}
