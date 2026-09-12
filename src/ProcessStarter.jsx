import React, { useEffect, useRef, useState } from "react";
import { Bot, Search } from "lucide-react";
import { api } from "./api";
import { Modal, Notice, StatusBadge } from "./components";

export default function ProcessStarter({
  cases,
  config,
  onClose,
  onImport,
  onOpenReview,
  onChanged,
}) {
  const [query, setQuery] = useState("");
  const [selected, setSelected] = useState(null);
  const [context, setContext] = useState(null);
  const [recipient, setRecipient] = useState("");
  const [error, setError] = useState("");
  const [busy, setBusy] = useState(false);
  const lock = useRef(false);
  const [reload, setReload] = useState(0);
  useEffect(() => {
    if (!selected) return;
    const controller = new AbortController();
    setContext(null);
    setError("");
    Promise.all([
      api(`/cases/${selected}`, { signal: controller.signal }),
      api(`/drafts?case_id=${selected}`, { signal: controller.signal }),
      api(`/proposals?case_id=${selected}`, { signal: controller.signal }),
      api(`/cases/${selected}/messages`, { signal: controller.signal }),
    ])
      .then(([detail, drafts, proposals, messages]) => {
        if (controller.signal.aborted) return;
        setContext({ detail, drafts, proposals, messages });
        setRecipient(detail.recipient);
      })
      .catch((e) => {
        if (e.name !== "AbortError") setError(e.message);
      });
    return () => controller.abort();
  }, [selected, reload]);
  const matches = cases.filter((c) =>
    [c.supplier_name, c.supplier_id, c.nart, c.id].some((value) =>
      value.toLowerCase().includes(query.toLowerCase()),
    ),
  );
  const fields =
    context?.detail.fields.filter(
      (f) =>
        [
          "Missing",
          "Outdated",
          "Flagged (needs supplier confirmation)",
        ].includes(f.data.Status) &&
        f.data["Editable by supplier"].toLowerCase() === "yes",
    ) || [];
  const existing = context?.drafts.find((d) =>
    ["pending", "approved", "sending", "uncertain"].includes(d.status),
  );
  const pending = context?.proposals.some((p) => p.status === "pending");
  const blockedReply = context?.messages.some((m) =>
    ["queued", "processing", "failed", "needs_review"].includes(m.status),
  );
  const waiting = context?.detail.status === "awaiting_reply";
  const allowed =
    config.mail_mode !== "gmail" ||
    recipient.toLowerCase() === config.gmail_supplier.toLowerCase();
  const contactDirty = context && recipient !== context.detail.recipient;
  async function act(work) {
    if (lock.current) return;
    lock.current = true;
    setBusy(true);
    setError("");
    try {
      await work();
    } catch (e) {
      setError(e.message);
      if (e.status === 409) setReload((n) => n + 1);
    } finally {
      setBusy(false);
      lock.current = false;
    }
  }
  function open(tab = "email") {
    onOpenReview(selected, tab);
  }
  return (
    <Modal
      title="Start a supplier process"
      subtitle="Choose the supplier, check what is missing, and prepare an email for review."
      onClose={onClose}
      busy={busy}
    >
      <div className="starter-message">
        <Bot size={22} />
        <p>Which supplier or article should we work on?</p>
      </div>
      {!selected ? (
        <>
          {!cases.length ? (
            <div className="review-card">
              <p>
                No supplier data has been imported yet. Upload a CSV and approve
                the import to start.
              </p>
              <button className="primary-btn" onClick={onImport}>
                Import supplier CSV
              </button>
            </div>
          ) : (
            <>
              <label className="field-label">
                Find a supplier or article
                <div className="search">
                  <Search size={17} />
                  <input
                    aria-label="Find a supplier or article"
                    placeholder="Supplier name, supplier ID, or article number"
                    value={query}
                    onChange={(e) => setQuery(e.target.value)}
                  />
                </div>
              </label>
              <div className="starter-options">
                {matches.slice(0, 50).map((c) => (
                  <button
                    className="starter-option"
                    key={c.id}
                    onClick={() => setSelected(c.id)}
                  >
                    <span>
                      <strong>{c.supplier_name}</strong>
                      <small>
                        Article {c.nart} · {c.outstanding_count} outstanding
                        fields
                      </small>
                    </span>
                    <StatusBadge status={c.status} />
                  </button>
                ))}
              </div>
              {!matches.length && (
                <p>
                  No matching supplier or article. Try another search or import
                  its data.
                </p>
              )}
              {matches.length > 50 && (
                <p className="muted">
                  Showing 50 of {matches.length} matches. Narrow your search to
                  find the right article.
                </p>
              )}
              <button className="secondary-btn" onClick={onImport}>
                Import another supplier CSV
              </button>
            </>
          )}
        </>
      ) : (
        <>
          <button
            className="secondary-btn"
            disabled={busy}
            onClick={() => {
              setSelected(null);
              setContext(null);
              setError("");
            }}
          >
            Choose another supplier
          </button>
          <Notice error>{error}</Notice>
          {!context ? (
            <p role="status">Checking supplier information…</p>
          ) : (
            <>
              <div className="starter-message user">
                <p>
                  {context.detail.supplier_name} · Article {context.detail.nart}
                </p>
              </div>
              <div className="starter-message">
                <Bot size={22} />
                <p>
                  {!fields.length
                    ? "All supplier-editable fields are complete. You can review the case history."
                    : `There ${fields.length === 1 ? "is 1 outstanding field" : `are ${fields.length} outstanding fields`}. Let's prepare the next step.`}
                </p>
              </div>
              {!!fields.length && (
                <details className="review-card" open>
                  <summary>Information to request ({fields.length})</summary>
                  <ul>
                    {fields.map((f) => (
                      <li key={f.id}>
                        {f.data["Field (label)"]}{" "}
                        <span className="muted">— {f.data.Status}</span>
                      </li>
                    ))}
                  </ul>
                </details>
              )}
              {pending || blockedReply ? (
                <div className="review-card">
                  <p>
                    A supplier reply or proposed change needs review first.
                    Finish that review before starting another request.
                  </p>
                  <button
                    className="primary-btn"
                    onClick={() => open(pending ? "data" : "replies")}
                  >
                    Review supplier reply
                  </button>
                </div>
              ) : existing ? (
                <div className="review-card">
                  <p>
                    An email is already{" "}
                    {existing.status === "pending"
                      ? "waiting for approval"
                      : existing.status === "uncertain"
                        ? "waiting for delivery verification"
                        : "approved or being sent"}
                    . Open it to continue this process.
                  </p>
                  <button className="primary-btn" onClick={() => open()}>
                    Review existing email
                  </button>
                </div>
              ) : !fields.length || waiting ? (
                <div className="review-card">
                  <p>
                    {waiting
                      ? "The request has been sent. We are waiting for the supplier response; due reminders are prepared through Check due cases."
                      : "No new information request is needed."}
                  </p>
                  <button
                    className="primary-btn"
                    onClick={() => open("activity")}
                  >
                    Review current process
                  </button>
                </div>
              ) : (
                <>
                  <div className="starter-message">
                    <Bot size={22} />
                    <p>
                      Confirm the recipient below. Preparing the request creates
                      a draft; you will review and approve the email before it
                      is sent.
                    </p>
                  </div>
                  <form
                    className="review-card"
                    onSubmit={(e) => {
                      e.preventDefault();
                      act(async () => {
                        await api(`/cases/${selected}/contact/approve`, {
                          method: "POST",
                          body: {
                            revision: context.detail.revision,
                            recipient,
                          },
                        });
                        setReload((n) => n + 1);
                        await onChanged();
                      });
                    }}
                  >
                    <label className="field-label">
                      Supplier email
                      <input
                        aria-label="Process recipient"
                        type="email"
                        required
                        value={recipient}
                        disabled={busy}
                        placeholder={config.gmail_supplier}
                        onChange={(e) => setRecipient(e.target.value)}
                      />
                    </label>
                    {!allowed && (
                      <Notice error>
                        This Gmail test setup sends only to{" "}
                        {config.gmail_supplier}. Use that address for the test
                        supplier.
                      </Notice>
                    )}
                    {(!context.detail.recipient || contactDirty) && (
                      <button
                        className="secondary-btn"
                        disabled={busy || !recipient || !allowed}
                      >
                        Approve supplier contact
                      </button>
                    )}
                  </form>
                  <button
                    className="primary-btn"
                    disabled={
                      busy ||
                      !context.detail.recipient ||
                      contactDirty ||
                      !allowed
                    }
                    onClick={() =>
                      act(async () => {
                        await api(`/cases/${selected}/draft`, {
                          method: "POST",
                        });
                        await onChanged();
                        open();
                      })
                    }
                  >
                    {busy ? "Preparing…" : "Prepare request for review"}
                  </button>
                </>
              )}
            </>
          )}
          {!context && error && (
            <button
              className="secondary-btn"
              onClick={() => setReload((n) => n + 1)}
            >
              Retry
            </button>
          )}
        </>
      )}
    </Modal>
  );
}
