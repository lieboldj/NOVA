import React, { useMemo, useState } from "react";
import { createRoot } from "react-dom/client";
import logo from "../logo.png";
import {
  Activity, AlertCircle, ArrowRight, Bot, CheckCircle2, ChevronDown,
  Bell, Clock3, FileCheck2, Filter, HelpCircle, LayoutDashboard, Moon,
  RefreshCw, Search, Send, ShieldCheck, Sparkles, Sun, UsersRound, X, Zap
} from "lucide-react";
import "./styles.css";

const initialRequests = [
  {
    id: "MDF-10482", supplier: "Bosch", date: "2026-09-12T09:42:00",
    status: "SENT", agent: "COMPLETED", priority: "normal",
    material: "Polyamide PA66", questions: [],
    activity: ["09:42 Agent validated all required fields", "09:43 Material declaration approved", "09:44 MDF sent to supplier"],
  },
  {
    id: "MDF-10481", supplier: "Siemens", date: "2026-09-12T09:21:00",
    status: "NEEDS_REVISION", agent: "NEEDS_HUMAN", priority: "high",
    material: "Recycled ABS", questions: [
      { id: "Q12", label: "What is the percentage of recycled material?", value: "120%", issue: "Value must be between 0% and 100%" },
      { id: "Q18", label: "Provide the supplier material grade.", value: "", issue: "Required field is missing" }
    ],
    activity: ["09:21 Agent started validation", "09:22 Invalid percentage detected in Q12", "09:22 Missing material grade detected in Q18", "09:23 Revision request generated", "09:23 Human review requested"],
  },
  {
    id: "MDF-10480", supplier: "ABB", date: "2026-09-11T16:18:00",
    status: "WAITING_FOR_SUPPLIER", agent: "WAITING", priority: "normal",
    material: "Copper alloy", questions: [],
    activity: ["16:18 Validation completed", "16:19 Revision request sent to supplier", "Waiting for supplier response"],
  },
  {
    id: "MDF-10479", supplier: "Bosch", date: "2026-09-11T14:06:00",
    status: "ERROR", agent: "ERROR", priority: "high",
    material: "Steel", questions: [],
    activity: ["14:06 Agent started validation", "14:07 Supplier endpoint returned an error", "14:07 Human intervention requested"],
  },
  {
    id: "MDF-10478", supplier: "Continental", date: "2026-09-11T11:37:00",
    status: "PROCESSING", agent: "RUNNING", priority: "normal",
    material: "EPDM rubber", questions: [],
    activity: ["11:37 Agent started validation", "11:38 Checking substance composition"],
  },
  {
    id: "MDF-10477", supplier: "ZF", date: "2026-09-10T15:24:00",
    status: "COMPLETED", agent: "COMPLETED", priority: "normal",
    material: "Aluminium", questions: [],
    activity: ["15:24 Agent validated declaration", "15:25 MDF archived"],
  },
  {
    id: "MDF-10476", supplier: "Valeo", date: "2026-09-10T10:11:00",
    status: "READY_TO_SEND", agent: "COMPLETED", priority: "normal",
    material: "Polypropylene", questions: [],
    activity: ["10:11 Validation passed", "10:12 Ready for automatic sending"],
  },
  {
    id: "MDF-10475", supplier: "Schaeffler", date: "2026-09-09T13:50:00",
    status: "NEEDS_REVISION", agent: "NEEDS_HUMAN", priority: "high",
    material: "NBR rubber", questions: [
      { id: "Q07", label: "Confirm the material weight in kg.", value: "—", issue: "Agent could not determine the correct unit" }
    ],
    activity: ["13:50 Agent detected ambiguous unit", "13:51 Escalated to human reviewer"],
  }
];

const statusMeta = {
  SENT: ["Sent", "green"], COMPLETED: ["Completed", "green"],
  PROCESSING: ["Processing", "blue"], READY_TO_SEND: ["Ready to send", "blue"],
  WAITING_FOR_SUPPLIER: ["Waiting for supplier", "amber"],
  NEEDS_REVISION: ["Needs revision", "red"], ERROR: ["Error", "red"],
  PENDING: ["Pending", "gray"]
};

function StatusBadge({ status }) {
  const [label, tone] = statusMeta[status] || [status, "gray"];
  return <span className={`badge ${tone}`}><span className="dot" />{label}</span>;
}

function AgentBadge({ status }) {
  const map = {
    COMPLETED: ["Automatic", "green", CheckCircle2],
    RUNNING: ["Running", "blue", Activity],
    WAITING: ["Waiting", "amber", Clock3],
    NEEDS_HUMAN: ["Needs help", "red", HelpCircle],
    ERROR: ["Error", "red", AlertCircle]
  };
  const [label, tone, Icon] = map[status] || ["Unknown", "gray", HelpCircle];
  return <span className={`agent-badge ${tone}`}><Icon size={14} />{label}</span>;
}

function StatCard({ icon: Icon, label, value, tone, note }) {
  return (
    <div className="stat-card">
      <div className={`stat-icon ${tone}`}><Icon size={19} /></div>
      <div>
        <div className="stat-label">{label}</div>
        <div className="stat-value">{value}</div>
        {note && <div className="stat-note">{note}</div>}
      </div>
    </div>
  );
}

function ActiveAgentsPage() {
  const agents = [
    ["MDF validation agent", "Validating material composition", "MDF-10478", "Processing"],
    ["Supplier follow-up agent", "Waiting for supplier response", "MDF-10480", "Waiting"],
    ["Quality review agent", "Escalated to a human reviewer", "MDF-10481", "Needs help"]
  ];
  return <section className="workspace-page">
    <div className="page-heading"><div><div className="eyebrow"><UsersRound size={14} /> ACTIVE AGENTS</div><h1>Agent operations</h1><p>See what each automation is working on right now.</p></div><span className="page-count">3 active</span></div>
    <div className="agent-grid">{agents.map(([name, detail, request, state]) => <article className={`agent-card ${state === "Needs help" ? "needs-help" : ""}`} key={name}>
      <div className="agent-card-icon"><Bot size={20} /></div><div className="agent-card-copy"><span>{request}</span><h2>{name}</h2><p>{detail}</p></div><div className="agent-card-footer"><span className={`agent-state ${state === "Needs help" ? "attention" : ""}`}><span />{state}</span><ArrowRight size={17} /></div>
    </article>)}</div>
  </section>;
}

function AlertsPage() {
  const alerts = [
    ["Human review requested", "MDF-10481 has two fields that need correction before processing can continue.", "Just now", "Needs attention"],
    ["Supplier endpoint unavailable", "The supplier endpoint for MDF-10479 returned an error. A retry is recommended.", "35 min ago", "Action needed"],
    ["Request ready to send", "MDF-10476 passed validation and is ready for automatic delivery.", "1 hr ago", "Info"]
  ];
  return <section className="workspace-page">
    <div className="page-heading"><div><div className="eyebrow"><Bell size={14} /> ALERTS</div><h1>Attention center</h1><p>Review events that may need action from your team.</p></div><span className="page-count">2 unread</span></div>
    <div className="alert-list">{alerts.map(([title, description, time, kind]) => <article className={`alert-card ${kind === "Info" ? "info" : ""}`} key={title}>
      <div className="alert-icon"><AlertCircle size={19} /></div><div><div className="alert-meta"><span>{kind}</span><time>{time}</time></div><h2>{title}</h2><p>{description}</p></div><button className="secondary-btn">Review</button>
    </article>)}</div>
  </section>;
}

function App() {
  const [requests, setRequests] = useState(initialRequests);
  const [selected, setSelected] = useState(null);
  const [query, setQuery] = useState("");
  const [status, setStatus] = useState("ALL");
  const [supplier, setSupplier] = useState("ALL");
  const [showFilters, setShowFilters] = useState(false);
  const [toast, setToast] = useState("");
  const [page, setPage] = useState("overview");
  const [darkMode, setDarkMode] = useState(false);

  const suppliers = [...new Set(requests.map(r => r.supplier))];

  const stats = useMemo(() => ({
    total: 248,
    completed: 181,
    waiting: 52,
    help: requests.filter(r => r.agent === "NEEDS_HUMAN" || r.agent === "ERROR").length + 11
  }), [requests]);

  const filtered = requests.filter(r => {
    const q = query.toLowerCase();
    return (status === "ALL" || r.status === status) &&
      (supplier === "ALL" || r.supplier === supplier) &&
      (!q || r.id.toLowerCase().includes(q) || r.supplier.toLowerCase().includes(q) || r.material.toLowerCase().includes(q));
  });

  function notify(message) {
    setToast(message);
    setTimeout(() => setToast(""), 2600);
  }

  function resolveRequest(id) {
    setRequests(prev => prev.map(r => r.id === id ? {
      ...r,
      status: "READY_TO_SEND",
      agent: "COMPLETED",
      questions: [],
      activity: [...r.activity, "Human reviewer approved corrections", "Agent resumed processing", "Request is ready to send"]
    } : r));
    setSelected(null);
    notify(`${id} approved — agent resumed processing.`);
  }

  function retryRequest(id) {
    setRequests(prev => prev.map(r => r.id === id ? {
      ...r, status: "PROCESSING", agent: "RUNNING",
      activity: [...r.activity, "Human reviewer triggered retry", "Agent resumed processing"]
    } : r));
    setSelected(null);
    notify(`${id} sent back to the agent.`);
  }

  return (
    <div className={`app ${darkMode ? "dark-mode" : ""}`}>
      <header className="topbar">
        <div className="brand">
          <img className="brand-mark" src={logo} alt="NOVA logo" />
          <span className="brand-label">Control Center</span>
        </div>
        <nav className="main-nav" aria-label="Main navigation">
          <button className={page === "overview" ? "active" : ""} onClick={() => setPage("overview")}><LayoutDashboard size={16} /> Overview</button>
          <button className={page === "agents" ? "active" : ""} onClick={() => setPage("agents")}><UsersRound size={16} /> Active agents</button>
          <button className={page === "alerts" ? "active" : ""} onClick={() => setPage("alerts")}><Bell size={16} /> Alerts <span>2</span></button>
        </nav>
        <div className="top-actions">
          <div className="agent-online"><span /> Agent online</div>
          <button className="theme-toggle" onClick={() => setDarkMode(v => !v)} title="Toggle blue dark mode" aria-label="Toggle blue dark mode">{darkMode ? <Sun size={17} /> : <Moon size={17} />}</button>
          <button className="icon-btn" title="Notifications"><AlertCircle size={18} /><b>3</b></button>
          <div className="avatar">AM</div>
        </div>
      </header>

      <main>
        {page === "overview" ? <>
        <section className="hero">
          <div>
            <div className="eyebrow"><Sparkles size={14} /> AUTOMATION OVERVIEW</div>
            <h1>Request operations</h1>
            <p>Monitor MDF requests and step in when the agent needs human judgment.</p>
          </div>
          <button className="primary-btn" onClick={() => notify("Agent is running. All queued requests are being processed.")}>
            <Zap size={16} /> Run agent
          </button>
        </section>

        <section className="stats">
          <StatCard icon={FileCheck2} label="Total requests" value={stats.total} tone="blue" note="+12 today" />
          <StatCard icon={CheckCircle2} label="Completed" value={stats.completed} tone="green" note="73% automated" />
          <StatCard icon={Clock3} label="Waiting" value={stats.waiting} tone="amber" note="Supplier response" />
          <StatCard icon={HelpCircle} label="Need help" value={stats.help} tone="red" note="Requires attention" />
        </section>

        <section className="panel">
          <div className="toolbar">
            <div className="search">
              <Search size={17} />
              <input value={query} onChange={e => setQuery(e.target.value)} placeholder="Search request ID, supplier or material..." />
            </div>
            <button className={`filter-btn ${showFilters ? "active" : ""}`} onClick={() => setShowFilters(v => !v)}>
              <Filter size={16} /> Filters <ChevronDown size={15} />
            </button>
            <button className="refresh-btn" onClick={() => notify("Request list refreshed.")}><RefreshCw size={16} /></button>
          </div>

          {showFilters && (
            <div className="filter-row">
              <label>Status<select value={status} onChange={e => setStatus(e.target.value)}>
                <option value="ALL">All statuses</option>
                {Object.keys(statusMeta).map(s => <option key={s} value={s}>{statusMeta[s][0]}</option>)}
              </select></label>
              <label>Supplier<select value={supplier} onChange={e => setSupplier(e.target.value)}>
                <option value="ALL">All suppliers</option>
                {suppliers.map(s => <option key={s}>{s}</option>)}
              </select></label>
              <button className="clear-btn" onClick={() => { setStatus("ALL"); setSupplier("ALL"); setQuery(""); }}>Clear filters</button>
            </div>
          )}

          <div className="table-head">
            <div>REQUEST</div><div>DATE</div><div>SUPPLIER</div><div>STATUS</div><div>AGENT</div><div></div>
          </div>

          <div className="rows">
            {filtered.map(r => (
              <button className="table-row" key={r.id} onClick={() => setSelected(r)}>
                <div className="request-cell"><span className="request-id">{r.id}</span><span className="material">{r.material}</span></div>
                <div className="date">{new Date(r.date).toLocaleDateString("en-GB", { day: "2-digit", month: "short", year: "numeric" })}<small>{new Date(r.date).toLocaleTimeString("en-GB", { hour: "2-digit", minute: "2-digit" })}</small></div>
                <div className="supplier-name">{r.supplier}</div>
                <div><StatusBadge status={r.status} /></div>
                <div><AgentBadge status={r.agent} /></div>
                <div className="row-arrow"><ArrowRight size={17} /></div>
              </button>
            ))}
            {!filtered.length && <div className="empty">No requests match your filters.</div>}
          </div>
          <div className="table-footer"><span>Showing {filtered.length} of {requests.length} recent requests</span><span className="live"><span /> Live updates enabled</span></div>
        </section>
        </> : page === "agents" ? <ActiveAgentsPage /> : <AlertsPage />}
      </main>

      {selected && (
        <div className="overlay" onMouseDown={e => e.target === e.currentTarget && setSelected(null)}>
          <aside className="drawer">
            <div className="drawer-head">
              <div><span className="drawer-kicker">REQUEST DETAILS</span><h2>{selected.id}</h2><p>{selected.supplier} · {selected.material}</p></div>
              <button className="icon-btn close" onClick={() => setSelected(null)}><X size={19} /></button>
            </div>

            <div className="drawer-body">
              <div className="detail-status"><div><span className="muted">Request status</span><StatusBadge status={selected.status} /></div><div><span className="muted">Agent</span><AgentBadge status={selected.agent} /></div></div>

              {selected.questions.length > 0 && (
                <>
                  <div className="section-title"><div><span className="section-number">01</span> Human review required</div><span className="count">{selected.questions.length} question{selected.questions.length > 1 ? "s" : ""}</span></div>
                  <div className="agent-callout"><Bot size={18} /><div><strong>Agent needs your help</strong><p>The agent found data that is missing, invalid, or ambiguous. Review the questions below before processing continues.</p></div></div>
                  <div className="questions">
                    {selected.questions.map((q, i) => (
                      <div className="question" key={q.id}>
                        <div className="q-top"><span>Question {q.id}</span><span className="issue">Needs revision</span></div>
                        <label>{q.label}</label>
                        <div className="answer-row"><input defaultValue={q.value} /><span className="issue-text">{q.issue}</span></div>
                      </div>
                    ))}
                  </div>
                  <div className="drawer-actions">
                    <button className="secondary-btn" onClick={() => retryRequest(selected.id)}><Send size={16} /> Send back to agent</button>
                    <button className="primary-btn" onClick={() => resolveRequest(selected.id)}><CheckCircle2 size={16} /> Approve & continue</button>
                  </div>
                </>
              )}

              {selected.questions.length === 0 && (
                <div className="normal-state"><div className="success-icon"><ShieldCheck size={27} /></div><h3>{selected.status === "ERROR" ? "Agent encountered an error" : "No human action required"}</h3><p>{selected.status === "ERROR" ? "The agent could not complete this request automatically. Trigger a retry to continue processing." : "This request is currently being handled automatically."}</p>{selected.status === "ERROR" && <button className="primary-btn" onClick={() => retryRequest(selected.id)}><RefreshCw size={16} /> Retry request</button>}</div>
              )}

              <div className="activity">
                <div className="section-title"><div><span className="section-number">02</span> Activity log</div></div>
                {selected.activity.map((item, i) => (
                  <div className="activity-item" key={i}><span className={`timeline-dot ${i === selected.activity.length - 1 ? "current" : ""}`} /><span>{item}</span></div>
                ))}
              </div>
            </div>
          </aside>
        </div>
      )}

      {toast && <div className="toast"><CheckCircle2 size={17} />{toast}</div>}
    </div>
  );
}

createRoot(document.getElementById("root")).render(<App />);
