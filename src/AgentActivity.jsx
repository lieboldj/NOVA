import React, { useEffect, useState } from "react";
import { ArrowLeft, ArrowRight } from "lucide-react";
import { api, dateLabel } from "./api";
import { Notice, StatusBadge } from "./components";

export default function AgentActivity({ kind, summary, onBack, onOpen }) {
  const [data, setData] = useState(null);
  const [offset, setOffset] = useState(0);
  const [error, setError] = useState("");
  const [refresh, setRefresh] = useState(0);
  useEffect(() => {
    const timer = setInterval(() => setRefresh((value) => value + 1), 15000);
    return () => clearInterval(timer);
  }, []);
  useEffect(() => {
    const controller = new AbortController();
    setError("");
    api(`/agents/${kind}/activity?offset=${offset}&limit=50`, {
      signal: controller.signal,
    })
      .then(setData)
      .catch((error) => {
        if (error.name !== "AbortError") setError(error.message);
      });
    return () => controller.abort();
  }, [kind, offset, refresh]);
  return (
    <section className="workspace-page">
      <button className="secondary-btn" onClick={onBack}>
        <ArrowLeft size={16} /> My Dashboard
      </button>
      <div className="page-heading">
        <div>
          <h1>
            {summary?.name ||
              (kind === "email" ? "Email agent" : "Reply evaluation agent")}
          </h1>
          <p>Supplier activity, most recent first.</p>
        </div>
        <span className="page-count">
          {data?.total ?? summary?.total ?? 0}{" "}
          {kind === "email" ? "emails" : "replies"} · {summary?.suppliers ?? 0}{" "}
          suppliers
        </span>
      </div>
      <Notice error>{error}</Notice>
      {!data ? (
        <p>Loading supplier activity…</p>
      ) : (
        <div className="panel agent-history">
          {!data.items.length && (
            <p className="empty">
              This agent has not handled any suppliers yet.
            </p>
          )}
          {data.items.map((item) => (
            <button
              className="agent-history-row"
              key={item.id}
              onClick={() =>
                onOpen(item.case_id, kind === "email" ? "email" : "data")
              }
            >
              <div>
                <strong>{item.supplier_name}</strong>
                <p>
                  {item.work} · Article {item.article || "Supplier level"}
                </p>
                {!!item.automatically_accepted && (
                  <p>
                    {item.automatically_accepted} data points accepted
                    automatically
                  </p>
                )}
              </div>
              <time>{dateLabel(item.last_touched_at)}</time>
              <StatusBadge status={item.status} />
              <ArrowRight size={16} />
            </button>
          ))}
          {data.total > 50 && (
            <div className="table-footer">
              <button
                className="secondary-btn"
                disabled={!offset}
                onClick={() => {
                  setData(null);
                  setOffset((value) => Math.max(0, value - 50));
                }}
              >
                Newer activity
              </button>
              <span>
                {offset + 1}–{Math.min(offset + 50, data.total)} of {data.total}
              </span>
              <button
                className="secondary-btn"
                disabled={offset + 50 >= data.total}
                onClick={() => {
                  setData(null);
                  setOffset((value) => value + 50);
                }}
              >
                Older activity
              </button>
            </div>
          )}
        </div>
      )}
    </section>
  );
}
