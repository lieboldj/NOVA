let csrf = "";
export function setSession(session) {
  csrf = session?.csrf || "";
}

export async function api(path, { method = "GET", body, signal } = {}) {
  const headers = {};
  if (body && !(body instanceof FormData))
    headers["Content-Type"] = "application/json";
  if (method !== "GET" && csrf) headers["X-NOVA-CSRF"] = csrf;
  const response = await fetch(`/api${path}`, {
    method,
    headers,
    credentials: "same-origin",
    signal,
    body:
      body instanceof FormData
        ? body
        : body === undefined
          ? undefined
          : JSON.stringify(body),
  });
  const data =
    response.status === 204 ? null : await response.json().catch(() => null);
  if (!response.ok) {
    if (response.status === 401 && path !== "/session")
      window.dispatchEvent(new Event("nova-session-expired"));
    const detail = data?.detail;
    const message = Array.isArray(detail)
      ? detail.map((e) => e.msg).join("; ")
      : detail;
    const error = new Error(
      message || `Request failed (${response.status}). Please try again.`,
    );
    error.status = response.status;
    throw error;
  }
  return data;
}

export async function allCases(signal) {
  const result = [];
  for (let offset = 0; ; offset += 500) {
    const page = await api(`/cases?offset=${offset}&limit=500`, { signal });
    result.push(...page);
    if (page.length < 500) return result;
  }
}

export function dateLabel(value) {
  if (!value) return "—";
  // Backend timestamps are UTC, stored without a timezone suffix.
  const date = new Date(/Z$|[+-]\d\d:\d\d$/.test(value) ? value : `${value}Z`);
  return Number.isNaN(date.getTime())
    ? "—"
    : date.toLocaleString("en-GB", { dateStyle: "medium", timeStyle: "short" });
}

export const statusMeta = {
  open: ["Open", "blue"],
  closed: ["Completed", "green"],
  email_review: ["Email approval", "amber"],
  data_review: ["Supplier review", "amber"],
  awaiting_reply: ["Waiting for supplier", "amber"],
  processing_reply: ["Processing reply", "blue"],
  paused: ["Paused", "gray"],
  escalated: ["Needs attention", "red"],
  pending: ["Awaiting approval", "amber"],
  approved: ["Approved", "blue"],
  sending: ["Sending", "blue"],
  sent: ["Sent", "green"],
  simulated: ["Simulated", "gray"],
  uncertain: ["Check delivery", "red"],
  rejected: ["Rejected", "gray"],
  superseded: ["Superseded", "gray"],
  queued: ["Queued", "blue"],
  running: ["Running", "blue"],
  done: ["Completed", "green"],
  failed: ["Failed", "red"],
  cancelled: ["Cancelled", "gray"],
  processing: ["Processing", "blue"],
  evaluated: ["Ready for review", "amber"],
  reviewed: ["Reviewed", "green"],
  needs_review: ["Review required", "amber"],
};
