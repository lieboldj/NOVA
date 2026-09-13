import React, { useRef, useState } from "react";
import { api, supplierName } from "./api";
import { Notice } from "./components";

export default function NaturalLanguageStarter({
  onChanged,
  onOpenReview,
  onBusyChange,
}) {
  const [command, setCommand] = useState("");
  const [preview, setPreview] = useState(null);
  const [expanded, setExpanded] = useState(false);
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
    <section aria-label="Request questionnaires in natural language">
      <form
        onSubmit={(e) => {
          e.preventDefault();
          act(async () => {
            setPreview(null);
            setResult(null);
            setExpanded(false);
            const data = await api("/processes/preview", {
              method: "POST",
              body: {
                command: /\bmdf\b/i.test(command) ? command : `MDF ${command}`,
              },
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
        <p className="muted">Use case: MDF</p>
        <label className="field-label">
          Describe your supplier request
          <textarea
            rows={3}
            required
            maxLength={2000}
            disabled={busy}
            placeholder="For example: suppliers in APAC and the automotive industry"
            value={command}
            onChange={(e) => {
              setCommand(e.target.value);
              setPreview(null);
              setResult(null);
              setError("");
            }}
          />
        </label>
        <button className="primary-btn" disabled={busy || !command.trim()}>
          {busy ? "Searching…" : "Search"}
        </button>
      </form>
      <Notice error>{error}</Notice>
      {preview && !result && (
        <div className="process-preview" aria-live="polite">
          <button
            className="match-count"
            disabled={!preview.matches.length}
            aria-expanded={expanded}
            onClick={() => setExpanded((value) => !value)}
          >
            {preview.supplier_count} matching{" "}
            {preview.supplier_count === 1 ? "supplier" : "suppliers"}
          </button>
          {expanded && (
            <>
              <div className="starter-options">
                {preview.matches.map((item) => (
                  <div className="audience-row" key={item.id}>
                    <input
                      type="checkbox"
                      aria-label={`Select ${supplierName(item.supplier_name)} ${item.nart}`}
                      disabled={busy || !item.eligible}
                      checked={selected.includes(item.id)}
                      onChange={(e) =>
                        setSelected((ids) =>
                          e.target.checked
                            ? [...ids, item.id]
                            : ids.filter((id) => id !== item.id),
                        )
                      }
                    />
                    <button
                      className="supplier-result"
                      disabled={busy}
                      onClick={() => onOpenReview(item.id, "email")}
                    >
                      <strong>{supplierName(item.supplier_name)}</strong>
                      <small>Article {item.nart || "Supplier level"}</small>
                      {item.reason && <small>{item.reason}</small>}
                    </button>
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
            </>
          )}
        </div>
      )}
      {result && (
        <div className="process-preview">
          <p role="status">
            {result.drafts.length}{" "}
            {result.drafts.length === 1 ? "request" : "requests"} prepared
          </p>
          <div className="starter-options">
            {result.drafts.map((draft) => {
              const item = preview.matches.find(
                (match) => match.id === draft.case_id,
              );
              return (
                <button
                  className="secondary-btn"
                  key={draft.id}
                  onClick={() => onOpenReview(draft.case_id, "email")}
                >
                  Review {supplierName(item.supplier_name)} ·{" "}
                  {item.nart || "Supplier level"}
                </button>
              );
            })}
          </div>
        </div>
      )}
    </section>
  );
}
