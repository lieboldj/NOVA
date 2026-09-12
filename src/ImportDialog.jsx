import React, { useState } from "react";
import { api } from "./api";
import { Modal, Notice } from "./components";

export default function ImportDialog({ onClose, onChanged }) {
  const [file, setFile] = useState(null);
  const [batch, setBatch] = useState(null);
  const [contacts, setContacts] = useState({});
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  async function preview(e) {
    e.preventDefault();
    setBusy(true);
    setError("");
    try {
      const form = new FormData();
      form.append("file", file);
      const result = await api("/imports", { method: "POST", body: form });
      const detail = await api(`/imports/${result.id}`);
      setBatch({ ...result, sample: detail.rows.slice(0, 10) });
    } catch (e) {
      setError(e.message);
    } finally {
      setBusy(false);
    }
  }
  async function approve(e) {
    e.preventDefault();
    setBusy(true);
    setError("");
    try {
      await api(`/imports/${batch.id}/approve`, {
        method: "POST",
        body: {
          contacts: Object.fromEntries(
            Object.entries(contacts).filter(([, v]) => v.trim()),
          ),
        },
      });
      await onChanged();
      onClose();
    } catch (e) {
      setError(e.message);
    } finally {
      setBusy(false);
    }
  }
  return (
    <Modal
      title="Import supplier CSV"
      subtitle="Preview the data before approving its addition to NOVA."
      onClose={onClose}
      busy={busy}
    >
      <Notice error>{error}</Notice>
      {!batch ? (
        <form onSubmit={preview}>
          <p>
            For requests by region and industry, include optional Region and
            Industry columns in your supplier submissions CSV.
          </p>
          <label className="field-label">
            Supplier submissions CSV
            <input
              aria-label="Supplier CSV"
              type="file"
              accept=".csv,text/csv"
              required
              disabled={busy}
              onChange={(e) => setFile(e.target.files[0] || null)}
            />
          </label>
          <button className="primary-btn" disabled={busy || !file}>
            {busy ? "Reading CSV…" : "Preview import"}
          </button>
        </form>
      ) : (
        <form onSubmit={approve}>
          <h3>
            {batch.row_count.toLocaleString()} fields · {batch.suppliers.length}{" "}
            suppliers
          </h3>
          <Notice>
            These rows are staged only. Approving the import adds them to the
            database. Emails will still need separate approval.
          </Notice>
          <details className="review-card" open>
            <summary>First {batch.sample.length} rows</summary>
            {batch.sample.map((row, i) => (
              <div className="import-row" key={i}>
                <strong>
                  {row["Supplier Name"]} · {row.NART}
                </strong>
                <p>
                  {row["Field (label)"]}: {row["Value submitted"] || "(empty)"}{" "}
                  · {row.Status}
                </p>
              </div>
            ))}
          </details>
          <details className="review-card">
            <summary>
              Optional supplier contacts ({batch.suppliers.length})
            </summary>
            <p className="muted">
              Leave unknown addresses blank. Approve them later on the case
              before drafting an email.
            </p>
            {batch.suppliers.map((id) => (
              <label className="field-label" key={id}>
                {id}
                <input
                  type="email"
                  value={contacts[id] || ""}
                  onChange={(e) =>
                    setContacts({ ...contacts, [id]: e.target.value })
                  }
                />
              </label>
            ))}
          </details>
          <button className="primary-btn" disabled={busy}>
            {busy ? "Importing…" : "Approve import into database"}
          </button>
        </form>
      )}
    </Modal>
  );
}
