import React, { useCallback, useEffect, useRef, useState } from "react";
import { createRoot } from "react-dom/client";
import {
  MessageSquarePlus,
  AlertCircle,
  ArrowRight,
  Bell,
  Bot,
  CheckCircle2,
  ChevronDown,
  Clock3,
  Download,
  Filter,
  HelpCircle,
  LayoutDashboard,
  LogOut,
  Moon,
  RefreshCw,
  Search,
  Sparkles,
  Sun,
  UsersRound,
} from "lucide-react";
import logo from "../logo.png";
import { allCases, api, dateLabel, setSession, statusMeta } from "./api";
import { Notice, StatusBadge } from "./components";
import CaseDrawer from "./CaseDrawer";
import ProcessStarter from "./ProcessStarter";
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

function StatCard({ icon: Icon, label, value, tone, note, onClick }) {
  return (
    <button
      type="button"
      className={`stat-card ${onClick ? "clickable" : ""}`}
      onClick={onClick}
    >
      <div className={`stat-icon ${tone}`}>
        <Icon size={19} />
      </div>
      <div>
        <div className="stat-label">{label}</div>
        <div className="stat-value">{value}</div>
        <div className="stat-note">{note}</div>
      </div>
    </button>
  );
}

function Operations({ jobs, onOpen }) {
  return (
    <section className="workspace-page">
      <div className="page-heading">
        <div>
          <div className="eyebrow">
            <UsersRound size={14} /> AGENT OPERATIONS
          </div>
          <h1>Delivery and evaluation</h1>
          <p>Select an agent to see its work and the case history.</p>
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
          <button
            type="button"
            onClick={() => onOpen(j.case_id)}
            disabled={!j.case_id}
            className="agent-card clickable"
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
          </button>
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
  const [starting, setStarting] = useState(false);
  const [selectedTab, setSelectedTab] = useState(undefined);
  const [sort, setSort] = useState({ key: "nart", direction: 1 });
  const [reviewOnly, setReviewOnly] = useState(false);
  const [query, setQuery] = useState("");
  const [status, setStatus] = useState("ALL");
  const [supplier, setSupplier] = useState("ALL");
  const [showFilters, setShowFilters] = useState(false);
  const [page, setPage] = useState("overview");
  const [darkMode, setDarkMode] = useState(false);
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
  const cases = data?.cases || [];
  const jobs = data?.jobs || [];
  const urgent = (c) =>
    c.next_action_at &&
    new Date(
      /Z$|[+-]\d\d:\d\d$/.test(c.next_action_at)
        ? c.next_action_at
        : `${c.next_action_at}Z`,
    ) <= new Date();
  const attention = cases.filter((c) =>
    ["email_review", "data_review", "escalated", "paused"].includes(c.status),
  );
  const failed = jobs.filter((j) => j.status === "failed");
  const alertCases = cases
    .filter(
      (c) =>
        attention.includes(c) || (c.status === "awaiting_reply" && urgent(c)),
    )
    .sort((a, b) => Number(!!urgent(b)) - Number(!!urgent(a)));
  const alertCount = alertCases.length + failed.length;
  const filtered = cases.filter(
    (c) =>
      (!reviewOnly || attention.some((item) => item.id === c.id)) &&
      (status === "ALL" || c.status === status) &&
      (supplier === "ALL" || c.supplier_id === supplier) &&
      [c.id, c.supplier_id, c.supplier_name, c.nart].some((v) =>
        v.toLowerCase().includes(query.toLowerCase()),
      ),
  );
  const sortValue = (c) =>
    sort.key === "updated"
      ? c.last_reply_at || c.last_sent_at || ""
      : sort.key === "status"
        ? statusMeta[c.status]?.[0] || c.status
        : c[sort.key];
  filtered.sort(
    (a, b) =>
      sort.direction *
      (typeof sortValue(a) === "number"
        ? sortValue(a) - sortValue(b)
        : String(sortValue(a)).localeCompare(String(sortValue(b)), undefined, {
            numeric: true,
          })),
  );
  function openActivity(id) {
    setSelectedTab("activity");
    setSelected(id);
  }
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
        {data?.config.ai_mode === "fixture" && (
          <Notice>
            Demo evaluation uses scripted answers from fictional evidence. It
            does not call Gemini or Anymize.
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
                <h1>My Dashboard</h1>
                <p>
                  Review supplier requests, email drafts, and proposed data
                  changes.
                </p>
              </div>
              <div className="hero-actions">
                <button
                  className="primary-btn"
                  disabled={busy}
                  onClick={() => setStarting(true)}
                >
                  <MessageSquarePlus size={16} /> Talk to NOVA
                </button>
              </div>
            </section>
            <section className="stats">
              <StatCard
                icon={HelpCircle}
                label="Need review"
                value={attention.length}
                tone="amber"
                note={
                  reviewOnly
                    ? "Showing cases needing review · Click to show all"
                    : "Open cases needing your decision"
                }
                onClick={() => {
                  setReviewOnly((value) => !value);
                  setStatus("ALL");
                  setSupplier("ALL");
                  setQuery("");
                }}
              />
              <StatCard
                icon={CheckCircle2}
                label="Completed"
                value={cases.filter((c) => c.status === "closed").length}
                tone="green"
                note="All requested data points complete"
                onClick={() => {
                  setReviewOnly(false);
                  setStatus("closed");
                }}
              />
              <StatCard
                icon={Clock3}
                label="Waiting"
                value={
                  cases.filter((c) => c.status === "awaiting_reply").length
                }
                tone="amber"
                note="Supplier response or email delivery pending"
                onClick={() => {
                  setReviewOnly(false);
                  setStatus("awaiting_reply");
                }}
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
                <a
                  className="secondary-btn"
                  href="/api/exports/submissions.csv"
                >
                  <Download size={16} /> Export CSV
                </a>
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
                      setReviewOnly(false);
                      setStatus("ALL");
                      setSupplier("ALL");
                      setQuery("");
                    }}
                  >
                    Clear filters
                  </button>
                </div>
              )}
              {reviewOnly && (
                <p className="review-filter">
                  Showing cases that need review.{" "}
                  <button
                    className="clear-btn"
                    onClick={() => setReviewOnly(false)}
                  >
                    Show all requests
                  </button>
                </p>
              )}
              <div className="table-head">
                {[
                  ["nart", "Article / Case"],
                  ["updated", "Last reply / send"],
                  ["supplier_name", "Supplier"],
                  ["status", "Status"],
                  ["outstanding_count", "Outstanding"],
                ].map(([key, label]) => (
                  <button
                    key={key}
                    className="sort-heading"
                    onClick={() =>
                      setSort((old) => ({
                        key,
                        direction: old.key === key ? -old.direction : 1,
                      }))
                    }
                    aria-label={`Sort by ${label}`}
                  >
                    {label}{" "}
                    {sort.key === key
                      ? sort.direction === 1
                        ? "↑"
                        : "↓"
                      : "↕"}
                  </button>
                ))}
                <div />
              </div>
              <div className="rows">
                {filtered.map((c) => (
                  <button
                    className="table-row"
                    key={c.id}
                    onClick={() => {
                      setSelectedTab(undefined);
                      setSelected(c.id);
                    }}
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
                      <StatusBadge
                        status={c.status}
                        waitingSince={c.last_sent_at}
                      />
                    </div>
                    <div>
                      {c.outstanding_count}{" "}
                      {c.outstanding_count === 1 ? "data point" : "data points"}
                    </div>
                    <div className="row-arrow">
                      <ArrowRight size={17} />
                    </div>
                  </button>
                ))}
                {!filtered.length && (
                  <div className="empty">
                    {cases.length
                      ? "No requests match your filters."
                      : "No supplier cases yet. Supplier data will appear here when available."}
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
          <Operations jobs={jobs} onOpen={openActivity} />
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
              {alertCases.map((c) => (
                <article
                  className={`alert-card ${urgent(c) ? "urgent" : "info"}`}
                  key={c.id}
                >
                  <div className="alert-icon">
                    <AlertCircle size={19} />
                  </div>
                  <div>
                    <StatusBadge
                      status={c.status}
                      waitingSince={c.last_sent_at}
                    />
                    <h2>{c.supplier_name}</h2>
                    {urgent(c) && (
                      <p>
                        Response overdue · Due {dateLabel(c.next_action_at)}
                      </p>
                    )}
                    <p>
                      Article {c.nart} · {c.outstanding_count} outstanding data
                      points
                    </p>
                  </div>
                  <button
                    className="secondary-btn"
                    onClick={() => {
                      setSelectedTab(undefined);
                      setSelected(c.id);
                    }}
                  >
                    Review
                  </button>
                </article>
              ))}
              {failed.map((j) => (
                <article className="alert-card info" key={j.id}>
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
          initialTab={selectedTab}
          onClose={() => setSelected(null)}
          backLabel={starting ? "Return to search list" : undefined}
          onChanged={refresh}
        />
      )}
      {starting && data && (
        <div hidden={!!selected}>
          <ProcessStarter
            cases={cases}
            config={data.config}
            onClose={() => setStarting(false)}
            onChanged={refresh}
            onOpenReview={(id, tab) => {
              setSelectedTab(tab);
              setSelected(id);
            }}
          />
        </div>
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
