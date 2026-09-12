import React, { useCallback, useEffect, useRef, useState } from "react";
import { createRoot } from "react-dom/client";
import {
  Activity,
  AlertCircle,
  ArrowRight,
  Bell,
  Bot,
  CheckCircle2,
  ChevronDown,
  Clock3,
  Download,
  FileCheck2,
  Filter,
  HelpCircle,
  LayoutDashboard,
  LogOut,
  Mail,
  Moon,
  RefreshCw,
  Search,
  Sparkles,
  Sun,
  Upload,
  UsersRound,
  Zap,
} from "lucide-react";
import logo from "../logo.png";
import { allCases, api, dateLabel, setSession, statusMeta } from "./api";
import { Notice, StatusBadge } from "./components";
import CaseDrawer from "./CaseDrawer";
import ImportDialog from "./ImportDialog";
import "./styles.css";

function Login({ onLogin }) {
  const [token, setToken] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  async function submit(e) {
    e.preventDefault();
    setBusy(true);
    setError("");
    try {
      const session = await api("/session", {
        method: "POST",
        body: { token },
      });
      setToken("");
      onLogin(session);
    } catch (e) {
      setError(e.message);
    } finally {
      setBusy(false);
    }
  }
  return (
    <div className="login-page">
      <form className="login-card" onSubmit={submit}>
        <img className="brand-mark" src={logo} alt="NOVA logo" />
        <h1>NOVA Control Center</h1>
        <p>Sign in to review supplier emails and proposed data changes.</p>
        <Notice error>{error}</Notice>
        <label className="field-label">
          Reviewer access key
          <input
            aria-label="Reviewer access key"
            type="password"
            autoComplete="current-password"
            required
            value={token}
            onChange={(e) => setToken(e.target.value)}
          />
        </label>
        <button className="primary-btn" disabled={busy || !token}>
          {busy ? "Signing in…" : "Sign in"}
        </button>
        <p className="muted">
          Use the reviewer access key provided by your NOVA administrator.
        </p>
      </form>
    </div>
  );
}

function StatCard({ icon: Icon, label, value, tone, note }) {
  return (
    <div className="stat-card">
      <div className={`stat-icon ${tone}`}>
        <Icon size={19} />
      </div>
      <div>
        <div className="stat-label">{label}</div>
        <div className="stat-value">{value}</div>
        <div className="stat-note">{note}</div>
      </div>
    </div>
  );
}

function Operations({ jobs }) {
  return (
    <section className="workspace-page">
      <div className="page-heading">
        <div>
          <div className="eyebrow">
            <UsersRound size={14} /> AGENT OPERATIONS
          </div>
          <h1>Delivery and evaluation</h1>
          <p>Recent backend jobs and their actual processing state.</p>
        </div>
        <span className="page-count">
          {jobs.filter((j) => ["queued", "running"].includes(j.status)).length}{" "}
          queued or running
        </span>
      </div>
      {!jobs.length && (
        <div className="empty panel">No processing jobs yet.</div>
      )}
      <div className="agent-grid">
        {jobs.map((j) => (
          <article
            className={`agent-card ${j.status === "failed" ? "needs-help" : ""}`}
            key={j.id}
          >
            <div className="agent-card-icon">
              <Bot size={20} />
            </div>
            <div className="agent-card-copy">
              <span>{j.id.slice(0, 8)}</span>
              <h2>
                {j.kind === "send"
                  ? "Email delivery"
                  : "Supplier reply evaluation"}
              </h2>
              <p>{j.error || `Attempts: ${j.attempts}`}</p>
              <p>{dateLabel(j.available_at)}</p>
            </div>
            <div className="agent-card-footer">
              <StatusBadge status={j.status} />
            </div>
          </article>
        ))}
      </div>
      {!!jobs.length && (
        <p className="muted">
          Showing the most recent {jobs.length} jobs (up to 500). Open the
          related case to review or retry a failed job.
        </p>
      )}
    </section>
  );
}

function Dashboard({ session, onLogout }) {
  const [data, setData] = useState(null);
  const [error, setError] = useState("");
  const [notice, setNotice] = useState("");
  const [busy, setBusy] = useState(false);
  const [updated, setUpdated] = useState(null);
  const [selected, setSelected] = useState(null);
  const [importing, setImporting] = useState(false);
  const [query, setQuery] = useState("");
  const [status, setStatus] = useState("ALL");
  const [supplier, setSupplier] = useState("ALL");
  const [showFilters, setShowFilters] = useState(false);
  const [page, setPage] = useState("overview");
  const [darkMode, setDarkMode] = useState(false);
  const [syncReview, setSyncReview] = useState([]);
  const fetching = useRef(false);
  const actionLock = useRef(false);
  const refresh = useCallback(async () => {
    if (fetching.current) return;
    fetching.current = true;
    try {
      const [cases, jobs, config] = await Promise.all([
        allCases(),
        api("/jobs"),
        api("/configuration"),
      ]);
      setData({ cases, jobs, config });
      setUpdated(new Date());
      setError("");
    } catch (e) {
      setError(e.message);
    } finally {
      fetching.current = false;
    }
  }, []);
  useEffect(() => {
    refresh();
    const interval = setInterval(refresh, 15000);
    return () => clearInterval(interval);
  }, [refresh]);
  async function action(work) {
    if (actionLock.current) return;
    actionLock.current = true;
    setBusy(true);
    setError("");
    setNotice("");
    try {
      await work();
      await refresh();
    } catch (e) {
      setError(e.message);
    } finally {
      setBusy(false);
      actionLock.current = false;
    }
  }
  async function runCheck() {
    const result = await api("/automation/tick", { method: "POST" });
    setNotice(
      `Check completed: ${result.drafted} drafts prepared, ${result.closed} cases completed, ${result.escalated} escalated. Drafts await your approval.`,
    );
  }
  async function syncInbox() {
    let token = null,
      received = 0,
      duplicates = 0;
    const reviews = [];
    const seen = new Set();
    try {
      do {
        const result = await api(
          `/automation/gmail/sync${token ? `?page_token=${encodeURIComponent(token)}` : ""}`,
          { method: "POST" },
        );
        for (const item of result.results) {
          if (item.status === "manual_review") reviews.push(item);
          else if (item.duplicate) duplicates++;
          else received++;
        }
        token = result.next_page_token;
        if (token && seen.has(token))
          throw new Error("Inbox pagination repeated. Refresh and try again.");
        if (token) seen.add(token);
      } while (token);
      setNotice(
        `Inbox sync: ${received} new replies, ${duplicates} already received, ${reviews.length} need manual routing.`,
      );
    } finally {
      setSyncReview(reviews);
    }
  }
  const cases = data?.cases || [];
  const jobs = data?.jobs || [];
  const attention = cases.filter((c) =>
    ["email_review", "data_review", "escalated", "paused"].includes(c.status),
  );
  const failed = jobs.filter((j) => j.status === "failed");
  const alertCount = attention.length + failed.length + syncReview.length;
  const filtered = cases.filter(
    (c) =>
      (status === "ALL" || c.status === status) &&
      (supplier === "ALL" || c.supplier_id === supplier) &&
      [c.id, c.supplier_id, c.supplier_name, c.nart].some((v) =>
        v.toLowerCase().includes(query.toLowerCase()),
      ),
  );
  const suppliers = [
    ...new Map(
      cases.map((c) => [
        c.supplier_id,
        { id: c.supplier_id, name: c.supplier_name },
      ]),
    ).values(),
  ];
  return (
    <div className={`app ${darkMode ? "dark-mode" : ""}`}>
      <header className="topbar">
        <div className="brand">
          <img className="brand-mark" src={logo} alt="NOVA logo" />
          <span className="brand-label">Control Center</span>
        </div>
        <nav className="main-nav" aria-label="Main navigation">
          {[
            ["overview", "Overview", LayoutDashboard],
            ["agents", "Active agents", UsersRound],
            ["alerts", "Alerts", Bell],
          ].map(([id, label, Icon]) => (
            <button
              key={id}
              className={page === id ? "active" : ""}
              onClick={() => setPage(id)}
            >
              <Icon size={16} />
              {label}
              {id === "alerts" && !!alertCount && <span>{alertCount}</span>}
            </button>
          ))}
        </nav>
        <div className="top-actions">
          <div className="agent-online">
            {data && !error ? "Backend connected" : "Checking connection"}
          </div>
          <button
            className="theme-toggle"
            aria-label="Toggle dark mode"
            onClick={() => setDarkMode((v) => !v)}
          >
            {darkMode ? <Sun size={17} /> : <Moon size={17} />}
          </button>
          <button
            className="icon-btn"
            aria-label="Sign out"
            title={`Sign out ${session.reviewer}`}
            disabled={busy}
            onClick={() => action(onLogout)}
          >
            <LogOut size={18} />
          </button>
        </div>
      </header>
      <main>
        <Notice error>{error}</Notice>
        <Notice>{notice}</Notice>
        {data &&
          data.config.ai_mode === "gemini" &&
          !data.config.anymize_configured && (
            <Notice>
              Reply evaluation is waiting for Anymize setup. You can review
              cases, approve emails, and read incoming replies.
            </Notice>
          )}
        {data?.config.mail_mode === "simulation" && (
          <Notice>
            Simulation mode: approved emails are recorded without sending real
            mail.
          </Notice>
        )}
        {!data ? (
          <div className="empty panel">
            <p>Loading backend data…</p>
            <button className="secondary-btn" onClick={refresh}>
              Retry connection
            </button>
          </div>
        ) : page === "overview" ? (
          <>
            <section className="hero">
              <div>
                <div className="eyebrow">
                  <Sparkles size={14} /> AUTOMATION OVERVIEW
                </div>
                <h1>Request operations</h1>
                <p>
                  Review supplier requests, email drafts, and proposed data
                  changes.
                </p>
              </div>
              <div className="hero-actions">
                <button
                  className="secondary-btn"
                  disabled={busy}
                  onClick={() => setImporting(true)}
                >
                  <Upload size={16} /> Import CSV
                </button>
                <a
                  className="secondary-btn"
                  href="/api/exports/submissions.csv"
                >
                  <Download size={16} /> Export CSV
                </a>
                <button
                  className="secondary-btn"
                  disabled={busy || !data.config.gmail_configured}
                  onClick={() => action(syncInbox)}
                >
                  <Mail size={16} /> Sync inbox
                </button>
                <button
                  className="primary-btn"
                  disabled={busy}
                  onClick={() => action(runCheck)}
                >
                  <Zap size={16} /> {busy ? "Working…" : "Run agent"}
                </button>
              </div>
            </section>
            <section className="stats">
              <StatCard
                icon={FileCheck2}
                label="Total requests"
                value={cases.length}
                tone="blue"
                note="Supplier/article cases"
              />
              <StatCard
                icon={CheckCircle2}
                label="Completed"
                value={cases.filter((c) => c.status === "closed").length}
                tone="green"
                note="All required values complete"
              />
              <StatCard
                icon={Clock3}
                label="Waiting"
                value={
                  cases.filter((c) => c.status === "awaiting_reply").length
                }
                tone="amber"
                note="Supplier response"
              />
              <StatCard
                icon={HelpCircle}
                label="Need review"
                value={attention.length}
                tone="red"
                note="Approval or attention required"
              />
            </section>
            <section className="panel">
              <div className="toolbar">
                <div className="search">
                  <Search size={17} />
                  <input
                    aria-label="Search requests"
                    value={query}
                    onChange={(e) => setQuery(e.target.value)}
                    placeholder="Search case ID, supplier or article…"
                  />
                </div>
                <button
                  className={`filter-btn ${showFilters ? "active" : ""}`}
                  onClick={() => setShowFilters((v) => !v)}
                >
                  <Filter size={16} /> Filters <ChevronDown size={15} />
                </button>
                <button
                  className="refresh-btn"
                  aria-label="Refresh requests"
                  onClick={refresh}
                >
                  <RefreshCw size={16} />
                </button>
              </div>
              {showFilters && (
                <div className="filter-row">
                  <label>
                    Status
                    <select
                      value={status}
                      onChange={(e) => setStatus(e.target.value)}
                    >
                      <option value="ALL">All statuses</option>
                      {[...new Set(cases.map((c) => c.status))].map((s) => (
                        <option key={s} value={s}>
                          {statusMeta[s]?.[0] || s}
                        </option>
                      ))}
                    </select>
                  </label>
                  <label>
                    Supplier
                    <select
                      value={supplier}
                      onChange={(e) => setSupplier(e.target.value)}
                    >
                      <option value="ALL">All suppliers</option>
                      {suppliers.map((s) => (
                        <option key={s.id} value={s.id}>
                          {s.name}
                        </option>
                      ))}
                    </select>
                  </label>
                  <button
                    className="clear-btn"
                    onClick={() => {
                      setStatus("ALL");
                      setSupplier("ALL");
                      setQuery("");
                    }}
                  >
                    Clear filters
                  </button>
                </div>
              )}
              <div className="table-head">
                <div>ARTICLE / CASE</div>
                <div>LAST REPLY / SEND</div>
                <div>SUPPLIER</div>
                <div>STATUS</div>
                <div>OUTSTANDING</div>
                <div />
              </div>
              <div className="rows">
                {filtered.map((c) => (
                  <button
                    className="table-row"
                    key={c.id}
                    onClick={() => setSelected(c.id)}
                  >
                    <div className="request-cell">
                      <span className="request-id">{c.nart}</span>
                      <span className="material" title={c.id}>
                        {c.id.slice(0, 8)}
                      </span>
                    </div>
                    <div className="date">
                      {dateLabel(c.last_reply_at || c.last_sent_at)}
                    </div>
                    <div className="supplier-name">{c.supplier_name}</div>
                    <div>
                      <StatusBadge status={c.status} />
                    </div>
                    <div>{c.outstanding_count} fields</div>
                    <div className="row-arrow">
                      <ArrowRight size={17} />
                    </div>
                  </button>
                ))}
                {!filtered.length && (
                  <div className="empty">
                    {cases.length
                      ? "No requests match your filters."
                      : "No supplier cases yet. Import a CSV to get started."}
                  </div>
                )}
              </div>
              <div className="table-footer">
                <span>
                  Showing {filtered.length} of {cases.length} requests
                </span>
                <span>
                  Updated {updated?.toLocaleTimeString()} · Refreshes every 15
                  seconds
                </span>
              </div>
            </section>
          </>
        ) : page === "agents" ? (
          <Operations jobs={jobs} />
        ) : (
          <section className="workspace-page">
            <div className="page-heading">
              <div>
                <div className="eyebrow">
                  <Bell size={14} /> ALERTS
                </div>
                <h1>Attention center</h1>
                <p>
                  Cases needing review, failed jobs, and inbox routing issues.
                </p>
              </div>
              <span className="page-count">{alertCount} items</span>
            </div>
            <div className="alert-list">
              {attention.map((c) => (
                <article className="alert-card" key={c.id}>
                  <div className="alert-icon">
                    <AlertCircle size={19} />
                  </div>
                  <div>
                    <StatusBadge status={c.status} />
                    <h2>{c.supplier_name}</h2>
                    <p>
                      Article {c.nart} · {c.outstanding_count} outstanding
                      fields
                    </p>
                  </div>
                  <button
                    className="secondary-btn"
                    onClick={() => setSelected(c.id)}
                  >
                    Review
                  </button>
                </article>
              ))}
              {failed.map((j) => (
                <article className="alert-card" key={j.id}>
                  <div className="alert-icon">
                    <AlertCircle size={19} />
                  </div>
                  <div>
                    <h2>
                      {j.kind === "send"
                        ? "Email delivery"
                        : "Reply evaluation"}{" "}
                      failed
                    </h2>
                    <p>{j.error}</p>
                    <p>{j.id}</p>
                  </div>
                  <button
                    className="secondary-btn"
                    onClick={() => setPage("agents")}
                  >
                    View jobs
                  </button>
                </article>
              ))}
              {syncReview.map((r) => (
                <article className="alert-card" key={r.gmail_id}>
                  <div className="alert-icon">
                    <Mail size={19} />
                  </div>
                  <div>
                    <h2>Inbox reply needs manual routing</h2>
                    <p>{r.reason}</p>
                    <p>Gmail message: {r.gmail_id}</p>
                  </div>
                  <a
                    className="secondary-btn"
                    href="https://mail.google.com/"
                    target="_blank"
                    rel="noreferrer"
                  >
                    Open Gmail
                  </a>
                </article>
              ))}
              {!alertCount && (
                <div className="empty panel">No items need attention.</div>
              )}
            </div>
          </section>
        )}
      </main>
      {selected && data && (
        <CaseDrawer
          key={selected}
          caseId={selected}
          config={data.config}
          onClose={() => setSelected(null)}
          onChanged={refresh}
        />
      )}
      {importing && (
        <ImportDialog onClose={() => setImporting(false)} onChanged={refresh} />
      )}
    </div>
  );
}

function App() {
  const [session, updateSession] = useState(null);
  const [ready, setReady] = useState(false);
  const [error, setError] = useState("");
  const login = useCallback((value) => {
    setSession(value);
    updateSession(value?.authenticated ? value : null);
  }, []);
  useEffect(() => {
    api("/session")
      .then(login)
      .catch((e) => setError(e.message))
      .finally(() => setReady(true));
    const expired = () => {
      login(null);
      setError("Your session expired. Please sign in again.");
    };
    window.addEventListener("nova-session-expired", expired);
    return () => window.removeEventListener("nova-session-expired", expired);
  }, [login]);
  if (!ready) return <div className="login-page">Connecting to NOVA…</div>;
  return session ? (
    <Dashboard
      session={session}
      onLogout={async () => {
        await api("/session", { method: "DELETE" });
        login(null);
      }}
    />
  ) : (
    <>
      <Notice error>{error}</Notice>
      <Login
        onLogin={(value) => {
          setError("");
          login(value);
        }}
      />
    </>
  );
}

createRoot(document.getElementById("root")).render(<App />);
