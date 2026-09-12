import React, { useRef, useState } from "react";
import { api } from "./api";
import { Notice } from "./components";

const example =
  "For suppliers who are in region APAC and are in automotive industry, send the MDF request.";

export default function NaturalLanguageStarter({
  onChanged,
  onOpenReview,
  onBusyChange,
}) {
  const [command, setCommand] = useState("");
  const [preview, setPreview] = useState(null);
  const [selected, setSelected] = useState([]);
  const [result, setResult] = useState(null);
  const [error, setError] = useState("");
  const [busy, setBusy] = useState(false);
  const lock = useRef(false);

  async function act(work) {
    if (lock.current) return;
    lock.current = true;
    setBusy(true);
    onBusyChange(true);
    setError("");
    try {
      await work();
    } catch (e) {
      setError(e.message);
      if (e.status === 409) setPreview(null);
    } finally {
      lock.current = false;
      setBusy(false);
      onBusyChange(false);
    }
  }

  return (
    <section
      className="review-card"
      aria-label="Request questionnaires in natural language"
    >
      <form
        onSubmit={(event) => {
          event.preventDefault();
          act(async () => {
            setPreview(null);
            setResult(null);
            const data = await api("/processes/preview", {
              method: "POST",
              body: { command },
            });
            setPreview(data);
            setSelected(
              data.matches
                .filter((item) => item.eligible)
                .map((item) => item.id),
            );
          });
        }}
      >
        <label className="field-label">
          Describe your supplier request
          <textarea
            rows={3}
            required
            maxLength={2000}
            disabled={busy}
            placeholder={example}
            value={command}
            onChange={(event) => {
              setCommand(event.target.value);
              setPreview(null);
              setResult(null);
              setError("");
            }}
          />
        </label>
        <p>
          Request the MDF questionnaire by supplier name or ID, region and
          industry. Combine criteria with “and”, or explicitly ask for all
          suppliers.
        </p>
        <div className="drawer-actions">
          <button className="primary-btn" disabled={busy || !command.trim()}>
            {busy ? "Working…" : "Preview matching suppliers"}
          </button>
          <button
            type="button"
            className="secondary-btn"
            disabled={busy}
            onClick={() => {
              setCommand(example);
              setPreview(null);
              setResult(null);
              setError("");
            }}
          >
            Use APAC automotive example
          </button>
        </div>
      </form>
      <Notice error>{error}</Notice>
      {preview && !result && (
        <div className="process-preview" aria-live="polite">
          <h3>
            {preview.supplier_count} suppliers · {preview.matches.length}{" "}
            article cases
          </h3>
          <p>
            Questionnaire: MDF
            {preview.criteria.region.length > 0 &&
              ` · Region: ${preview.criteria.region.join(", ").toUpperCase()}`}
            {preview.criteria.industry.length > 0 &&
              ` · Industry: ${preview.criteria.industry.join(", ")}`}
          </p>
          {preview.missing_metadata_count > 0 && (
            <Notice>
              {preview.missing_metadata_count} cases have missing or conflicting
              targeting attributes and were excluded. Import supplier
              submissions with Region and Industry columns to make them
              available for targeting.
            </Notice>
          )}
          {!preview.matches.length && (
            <p>
              No suppliers match these criteria. Check the imported attributes
              or change your request.
            </p>
          )}
          {!!preview.matches.length && (
            <>
              <p>
                Select the article cases to request. Each selected case creates
                one email for review.
              </p>
              <div className="starter-options">
                {preview.matches.map((item) => (
                  <div className="review-card" key={item.id}>
                    <label className="audience-option">
                      <input
                        type="checkbox"
                        disabled={busy || !item.eligible}
                        checked={selected.includes(item.id)}
                        onChange={(event) =>
                          setSelected((ids) =>
                            event.target.checked
                              ? [...ids, item.id]
                              : ids.filter((id) => id !== item.id),
                          )
                        }
                      />
                      <span>
                        <strong>{item.supplier_name}</strong> ·{" "}
                        {item.supplier_id} · Article{" "}
                        {item.nart || "Supplier level"}
                        <br />
                        {item.region?.toUpperCase() ||
                          "Region unavailable"} ·{" "}
                        {item.industry || "Industry unavailable"}
                        <br />
                        {item.recipient || "No approved email"} ·{" "}
                        {item.fields.length} outstanding MDF fields
                      </span>
                    </label>
                    {item.reason && <p>{item.reason}</p>}
                    {item.fields.length > 0 && (
                      <details>
                        <summary>Information to request</summary>
                        <ul>
                          {item.fields.map((field) => (
                            <li key={field.id}>{field.label}</li>
                          ))}
                        </ul>
                      </details>
                    )}
                    {!item.eligible && (
                      <button
                        className="secondary-btn"
                        disabled={busy}
                        onClick={() => onOpenReview(item.id, "activity")}
                      >
                        Review case
                      </button>
                    )}
                  </div>
                ))}
              </div>
              <button
                className="primary-btn"
                disabled={busy || !selected.length}
                onClick={() =>
                  act(async () => {
                    const data = await api("/processes/start", {
                      method: "POST",
                      body: {
                        preview_token: preview.preview_token,
                        case_ids: selected,
                      },
                    });
                    setResult(data);
                    await onChanged();
                  })
                }
              >
                Prepare {selected.length}{" "}
                {selected.length === 1 ? "request" : "requests"} for review
              </button>
              <p>Review and approve each email before it is sent.</p>
            </>
          )}
        </div>
      )}
      {result && (
        <div className="process-preview" role="status">
          <h3>
            {result.drafts.length}{" "}
            {result.drafts.length === 1 ? "request" : "requests"} prepared
          </h3>
          <p>Your requests are waiting for email approval.</p>
          <div className="starter-options">
            {result.drafts.map((draft) => {
              const item = preview.matches.find(
                (match) => match.id === draft.case_id,
              );
              return (
                <button
                  className="secondary-btn"
                  key={draft.id}
                  disabled={busy}
                  onClick={() => onOpenReview(draft.case_id, "email")}
                >
                  Review {item.supplier_name} · {item.nart || "Supplier level"}
                </button>
              );
            })}
          </div>
        </div>
      )}
    </section>
  );
}
