import { test, expect } from "@playwright/test";
import { readFileSync } from "node:fs";

async function login(page) {
  await page.goto("/");
  await page.getByLabel("Reviewer access key").fill("ui-review-secret");
  await page.getByRole("button", { name: "Sign in", exact: true }).click();
  await expect(
    page.getByRole("heading", { name: "My Dashboard" }),
  ).toBeVisible();
}

const columns = [
  "Row ID",
  "Supplier ID",
  "Supplier Name",
  "NART",
  "Use case",
  "Module (ID)",
  "Category",
  "Section",
  "Field (label)",
  "Field Type",
  "Required @ go-live",
  "Editable by supplier",
  "Value submitted",
  "Submission date",
  "Status",
];
const row = [
  "UI-F1",
  "UI-SUPPLIER",
  "Fictional UI Supplier",
  "UI-ARTICLE",
  "MDF",
  "1",
  "",
  "Demo",
  "Material statement",
  "Freetext",
  "Yes",
  "yes",
  "",
  "",
  "Missing",
];

// Actual browser -> session -> API -> durable worker -> proposal approval, using isolated fixtures.
test("email approval and data approval remain separate across reloads", async ({
  page,
  request,
}) => {
  const errors = [];
  page.on("pageerror", (e) => errors.push(e.message));
  await login(page);
  const seedHeaders = { Authorization: "Bearer ui-review-secret" };
  const imported = await request.post("/api/imports", {
    headers: seedHeaders,
    multipart: {
      file: {
        name: "supplier.csv",
        mimeType: "text/csv",
        buffer: Buffer.from(columns.join(",") + "\n" + row.join(",") + "\n"),
      },
    },
  });
  const batch = await imported.json();
  await request.post(`/api/imports/${batch.id}/approve`, {
    headers: seedHeaders,
    data: { contacts: {} },
  });
  await page.reload();
  await page.getByRole("button", { name: "Talk to NOVA", exact: true }).click();
  await page
    .getByLabel("Describe your supplier request")
    .fill("Fictional UI Supplier");
  await page.getByRole("button", { name: "Search", exact: true }).click();
  await page
    .getByRole("button", { name: "1 matching supplier", exact: true })
    .click();
  await page
    .getByRole("dialog")
    .getByRole("button")
    .filter({ hasText: "Fictional UI Supplier" })
    .click();
  await expect(
    page.getByRole("button", { name: "Create email draft", exact: true }),
  ).toBeDisabled();
  await page
    .getByLabel("Supplier email", { exact: true })
    .fill("supplier@example.com");
  await page
    .getByRole("button", { name: "Save supplier email", exact: true })
    .click();
  await expect(
    page.getByText(
      "This email is saved. Change the address to save a new contact.",
    ),
  ).toBeVisible();
  await page
    .getByRole("button", { name: "Create email draft", exact: true })
    .click();
  await expect(
    page
      .getByTestId("email-review")
      .getByText("Awaiting approval", { exact: true }),
  ).toBeVisible();
  await page
    .getByLabel("Email body")
    .fill("Please confirm the material statement.");
  await expect(
    page.getByRole("button", { name: "Approve email & send", exact: true }),
  ).toBeDisabled();
  await page
    .getByRole("button", { name: "Save email edits", exact: true })
    .click();
  await expect(page.getByLabel("Email body")).toHaveValue(
    "Please confirm the material statement.",
  );
  await page
    .getByRole("button", { name: "Return to search list", exact: true })
    .click();
  await expect(page.getByLabel("Describe your supplier request")).toHaveValue(
    "Fictional UI Supplier",
  );
  await page
    .getByRole("dialog")
    .getByRole("button")
    .filter({ hasText: "Fictional UI Supplier" })
    .click();
  await expect(page.getByLabel("Email body")).toHaveValue(
    "Please confirm the material statement.",
  );
  const apiHeaders = { Authorization: "Bearer ui-review-secret" };
  const cases = await (
    await request.get("/api/cases", { headers: apiHeaders })
  ).json();
  const caseId = cases[0].id;
  expect(
    (
      await (
        await request.get(`/api/drafts?case_id=${caseId}`, {
          headers: apiHeaders,
        })
      ).json()
    ).length,
  ).toBe(1);
  expect(
    (
      await (
        await request.get(`/api/jobs?case_id=${caseId}`, {
          headers: apiHeaders,
        })
      ).json()
    ).length,
  ).toBe(0);
  await page
    .getByRole("button", { name: "Approve email & send", exact: true })
    .click();
  await page.getByRole("button", { name: "Close review", exact: true }).click();
  await page.reload();
  await page.getByRole("button").filter({ hasText: "UI-ARTICLE" }).click();
  await expect(
    page.getByTestId("email-review").getByText("Simulated", { exact: true }),
  ).toBeVisible();
  const reply = await request.post(`/api/cases/${caseId}/messages`, {
    headers: { Authorization: "Bearer ui-automation-secret" },
    multipart: {
      external_id: "ui-reply-1",
      sender: "supplier@example.com",
      body: "See attached material statement.",
      attachments: {
        name: "supplier-evidence.pdf",
        mimeType: "application/pdf",
        buffer: readFileSync(
          new URL("../fixtures/supplier-evidence.pdf", import.meta.url),
        ),
      },
    },
  });
  expect(reply.status()).toBe(201);
  await expect
    .poll(
      async () =>
        (
          await (
            await request.get(`/api/proposals?case_id=${caseId}`, {
              headers: apiHeaders,
            })
          ).json()
        ).length,
    )
    .toBe(1);
  await page.getByRole("button", { name: "Close review", exact: true }).click();
  await page.reload();
  await page.getByRole("button").filter({ hasText: "UI-ARTICLE" }).click();
  const proposal = page.getByTestId("proposal-review");
  await expect(proposal.getByLabel("Received value")).toHaveValue(
    "Verified recycled content",
  );
  let detail = await (
    await request.get(`/api/cases/${caseId}`, { headers: apiHeaders })
  ).json();
  expect(detail.fields[0].data["Value submitted"]).toBe("");
  await page.screenshot({
    path: ".data/screenshots/data-review.png",
    fullPage: true,
    animations: "disabled",
  });
  await page
    .getByRole("button", { name: "Submit reply review", exact: true })
    .click();
  await expect(
    page.getByText(
      "Reply review saved. Approved values written to the database.",
      { exact: true },
    ),
  ).toBeVisible();
  detail = await (
    await request.get(`/api/cases/${caseId}`, { headers: apiHeaders })
  ).json();
  expect(detail.fields[0].data["Value submitted"]).toBe(
    "Verified recycled content",
  );
  expect(detail.status).toBe("closed");
  await expect
    .poll(
      async () =>
        (
          await (
            await request.get(`/api/cases/${caseId}`, { headers: apiHeaders })
          ).json()
        ).status,
    )
    .toBe("closed");
  await page.getByRole("tab", { name: "Replies", exact: true }).click();
  await expect(
    page.getByText("See attached material statement.", { exact: true }),
  ).toBeVisible();
  const attachment = page.getByRole("link", {
    name: "supplier-evidence.pdf",
    exact: true,
  });
  await expect(attachment).toBeVisible();
  const download = await page.request.get(
    await attachment.getAttribute("href"),
  );
  expect(download.ok()).toBe(true);
  expect((await download.body()).subarray(0, 5).toString()).toBe("%PDF-");
  await page.getByRole("tab", { name: "Activity", exact: true }).click();
  await expect(
    page.getByText("change · approved", { exact: false }),
  ).toBeVisible();
  await page.getByRole("button", { name: "Close review", exact: true }).click();
  await page.getByRole("button", { name: "Sign out", exact: true }).click();
  await expect(
    page.getByRole("button", { name: "Sign in", exact: true }),
  ).toBeVisible();
  expect(errors).toEqual([]);
});

test("supplier review shows unchanged values, all replies and unused attachments", async ({
  page,
  request,
}) => {
  const headers = { Authorization: "Bearer ui-review-secret" };
  const records = [
    ["ALL-F1", "Material statement", "Existing composition", "Complete"],
    ["ALL-F2", "Packaging statement", "", "Missing"],
    ["ALL-F3", "Energy statement", "Previous energy mix", "Complete"],
  ].map(([id, label, value, status]) => {
    const record = [...row];
    record[0] = id;
    record[1] = "ALL-SUPPLIER";
    record[2] = "Complete Input Supplier";
    record[3] = "ALL-ARTICLE";
    record[8] = label;
    record[12] = value;
    record[14] = status;
    return record;
  });
  const imported = await request.post("/api/imports", {
    headers,
    multipart: {
      file: {
        name: "all-inputs.csv",
        mimeType: "text/csv",
        buffer: Buffer.from(
          columns.join(",") +
            "\n" +
            records.map((r) => r.join(",")).join("\n") +
            "\n",
        ),
      },
    },
  });
  expect(imported.status()).toBe(201);
  const batch = await imported.json();
  const approved = await request.post(`/api/imports/${batch.id}/approve`, {
    headers,
    data: { contacts: { "ALL-SUPPLIER": "supplier@example.com" } },
  });
  const caseId = (await approved.json()).case_ids[0];
  const draft = await (
    await request.post(`/api/cases/${caseId}/draft`, { headers })
  ).json();
  expect(draft.requested_fields).toEqual(["ALL-F2"]);
  expect(
    (
      await request.post(`/api/drafts/${draft.id}/approve`, {
        headers,
        data: { version: draft.version },
      })
    ).ok(),
  ).toBe(true);
  await expect
    .poll(
      async () =>
        (
          await (
            await request.get(`/api/drafts?case_id=${caseId}`, { headers })
          ).json()
        )[0].status,
    )
    .toBe("simulated");
  const body =
    "ALL-F1=Existing composition\nALL-F2=Reusable packaging\nAdditional note: delivery is delayed.";
  const first = await request.post(`/api/cases/${caseId}/messages`, {
    headers,
    multipart: {
      external_id: "ui-all-inputs",
      sender: "supplier@example.com",
      body,
      attachments: {
        name: "energy.txt",
        mimeType: "text/plain",
        buffer: Buffer.from("ALL-F3=Renewable energy confirmed"),
      },
    },
  });
  expect(first.status()).toBe(201);
  const second = await request.post(`/api/cases/${caseId}/messages`, {
    headers,
    multipart: {
      external_id: "ui-no-extraction",
      sender: "supplier@example.com",
      body: "We will send further details next week.",
      attachments: {
        name: "additional-notes.txt",
        mimeType: "text/plain",
        buffer: Buffer.from("Please call us about packaging."),
      },
    },
  });
  expect(second.status()).toBe(201);
  await expect
    .poll(async () =>
      (
        await (
          await request.get(`/api/cases/${caseId}/messages`, { headers })
        ).json()
      ).every((m) => ["evaluated", "needs_review"].includes(m.status)),
    )
    .toBe(true);
  await login(page);
  await page.getByRole("button").filter({ hasText: "ALL-ARTICLE" }).click();
  await expect(
    page.getByRole("tab", { name: /Supplier review/ }),
  ).toHaveAttribute("aria-selected", "true");
  const replies = page.getByTestId("supplier-reply-review");
  await expect(replies).toHaveCount(2);
  const extracted = replies.filter({
    hasText: "Additional note: delivery is delayed.",
  });
  const unextracted = replies.filter({
    hasText: "We will send further details next week.",
  });
  await expect(extracted.locator("pre")).toHaveText(body);
  await expect(
    extracted.getByText("Unchanged confirmation", { exact: false }),
  ).toBeVisible();
  await expect(
    extracted.getByText("Changed value", { exact: false }),
  ).toBeVisible();
  await expect(
    extracted.getByText("New value", { exact: false }),
  ).toBeVisible();
  await expect(extracted.getByTestId("proposal-review")).toHaveCount(3);
  await expect(
    extracted.getByRole("link", { name: "energy.txt", exact: true }),
  ).toBeVisible();
  await expect(
    extracted.getByRole("button", { name: "Submit reply review", exact: true }),
  ).toBeEnabled();
  await expect(
    unextracted.getByText(/No extracted values are available/),
  ).toBeVisible();
  await expect(unextracted.getByTestId("missing-answer")).toHaveCount(1);
  await expect(unextracted.getByTestId("missing-answer")).toContainText("0%");
  const attachment = unextracted.getByRole("link", {
    name: "additional-notes.txt",
    exact: true,
  });
  await expect(attachment).toBeVisible();
  expect(
    await (
      await page.request.get(await attachment.getAttribute("href"))
    ).text(),
  ).toBe("Please call us about packaging.");
  await unextracted
    .getByRole("button", { name: "Complete reply review", exact: true })
    .click();
  await expect(
    unextracted.getByText("Reviewed", { exact: true }),
  ).toBeVisible();
  await expect(
    extracted
      .locator('[data-testid="proposal-review"][data-field-id="ALL-F2"]')
      .getByLabel("Received value"),
  ).toHaveAttribute("readonly", "");
  await page.screenshot({
    path: ".data/screenshots/all-supplier-inputs.png",
    fullPage: true,
  });
  // One browser submission applies all three fields, including the unchanged confirmation.
  await extracted
    .getByRole("button", { name: "Submit reply review", exact: true })
    .click();
  await expect(extracted.getByText("Reviewed", { exact: true })).toBeVisible();
  const detail = await (
    await request.get(`/api/cases/${caseId}`, { headers })
  ).json();
  expect(
    detail.fields.find((f) => f.id === "ALL-F2").data["Value submitted"],
  ).toBe("Reusable packaging");
  await expect
    .poll(
      async () =>
        (await (await request.get(`/api/cases/${caseId}`, { headers })).json())
          .status,
    )
    .toBe("closed");
  await expect(replies).toHaveCount(2);
});

test("mobile layout, filters and real empty operation state", async ({
  page,
}) => {
  await page.setViewportSize({ width: 390, height: 844 });
  await login(page);
  await page.getByRole("button", { name: "Filters", exact: false }).click();
  await page.getByLabel("Search requests").fill("nonexistent-supplier");
  await expect(
    page.getByText(/No requests match your filters|No supplier cases yet/),
  ).toBeVisible();
  await page.screenshot({
    path: ".data/screenshots/mobile-overview.png",
    fullPage: true,
    animations: "disabled",
  });
  expect(
    await page.evaluate(
      () => document.documentElement.scrollWidth <= window.innerWidth,
    ),
  ).toBe(true);
});

test("human describes an audience and prepares selected MDF requests", async ({
  page,
  request,
}) => {
  const apiHeaders = { Authorization: "Bearer ui-review-secret" };
  const records = [
    ["NL-A1", "APAC", "Automotive"],
    ["NL-A2", "APAC", "Automotive"],
    ["NL-E1", "EMEA", "Automotive"],
  ].map(([id, region, industry]) => {
    const record = [...row];
    record[0] = `${id}-F1`;
    record[1] = id;
    record[2] = `Natural Language ${id}`;
    record[3] = `${id}-ARTICLE`;
    return [...record, region, industry];
  });
  const imported = await request.post("/api/imports", {
    headers: apiHeaders,
    multipart: {
      file: {
        name: "audience.csv",
        mimeType: "text/csv",
        buffer: Buffer.from(
          [...columns, "Region", "Industry"].join(",") +
            "\n" +
            records.map((record) => record.join(",")).join("\n") +
            "\n",
        ),
      },
    },
  });
  expect(imported.status()).toBe(201);
  const batch = await imported.json();
  expect(
    (
      await request.post(`/api/imports/${batch.id}/approve`, {
        headers: apiHeaders,
        data: {
          contacts: {
            "NL-A1": "a1@example.com",
            "NL-A2": "a2@example.com",
            "NL-E1": "e1@example.com",
          },
        },
      })
    ).ok(),
  ).toBe(true);
  await login(page);
  await page.getByRole("button", { name: "Talk to NOVA", exact: true }).click();
  await page
    .getByLabel("Describe your supplier request")
    .fill(
      "For suppliers who are in region APAC and are in automotive industry, send the MDF request.",
    );
  await page.getByRole("button", { name: "Search", exact: true }).click();
  const audience = page.getByRole("region", {
    name: "Request questionnaires in natural language",
  });
  await expect(audience.getByRole("checkbox")).toHaveCount(0);
  await audience
    .getByRole("button", { name: "2 matching suppliers", exact: true })
    .click();
  await expect(audience.getByRole("checkbox")).toHaveCount(2);
  await expect(
    audience.getByText("Natural Language NL-E1", { exact: true }),
  ).toHaveCount(0);
  await audience.getByRole("checkbox").last().uncheck();
  await audience
    .getByRole("button", { name: "Prepare 1 request for review", exact: true })
    .click();
  await expect(
    audience.getByText("1 request prepared", { exact: true }),
  ).toBeVisible();
  const drafts = (
    await (await request.get("/api/drafts", { headers: apiHeaders })).json()
  ).filter((draft) =>
    draft.requested_fields.some((id) => id.startsWith("NL-")),
  );
  expect(drafts).toHaveLength(1);
  expect(drafts[0].status).toBe("pending");
  await audience
    .getByRole("button", { name: /Review Natural Language/ })
    .click();
  await expect(page.getByLabel("Email subject")).toHaveValue(
    "Your business partner has an information request",
  );
  await expect(
    page.getByRole("button", { name: "Approve email & send", exact: true }),
  ).toBeEnabled();
});

test("confidence prioritizes review and rejection sends supplier reasons immediately", async ({
  page,
  request,
}) => {
  const headers = { Authorization: "Bearer ui-review-secret" };
  const fields = [
    ["CONF-F1", "High confidence", "Freetext", "Yes"],
    ["CONF-F2", "Threshold answer", "Freetext", "No"],
    ["CONF-F3", "Unknown confidence", "Freetext", "Yes"],
    ["CONF-F4", "Certificate date", "Date", "Yes"],
  ];
  const rows = fields.map(([id, label, type, required]) => {
    const record = [...row];
    record[0] = id;
    record[1] = "CONF-SUP";
    record[2] = "Demo Confidence Supplier";
    record[3] = "CONF-ARTICLE";
    record[8] = label;
    record[9] = type;
    record[10] = required;
    return record;
  });
  const batch = await (
    await request.post("/api/imports", {
      headers,
      multipart: {
        file: {
          name: "confidence.csv",
          mimeType: "text/csv",
          buffer: Buffer.from(
            columns.join(",") + "\n" + rows.map((r) => r.join(",")).join("\n"),
          ),
        },
      },
    })
  ).json();
  const imported = await (
    await request.post(`/api/imports/${batch.id}/approve`, {
      headers,
      data: { contacts: { "CONF-SUP": "supplier@example.com" } },
    })
  ).json();
  const caseId = imported.case_ids[0];
  const draft = await (
    await request.post(`/api/cases/${caseId}/draft`, { headers })
  ).json();
  expect(draft.subject).not.toContain("NOVA:");
  expect(draft.body).not.toContain("Demo Confidence");
  await request.post(`/api/drafts/${draft.id}/approve`, {
    headers,
    data: { version: 1 },
  });
  await expect
    .poll(
      async () =>
        (
          await (
            await request.get(`/api/drafts?case_id=${caseId}`, { headers })
          ).json()
        )[0].status,
    )
    .toBe("simulated");
  await request.post(`/api/cases/${caseId}/messages`, {
    headers,
    multipart: {
      external_id: "confidence-reply",
      sender: "supplier@example.com",
      body: "CONF-F1=Confirmed\nCONF-F2=Ambiguous answer\nCONF-F3=Unclear answer\nCONF-F4=2028-13-40",
    },
  });
  await expect
    .poll(
      async () =>
        (
          await (
            await request.get(`/api/proposals?case_id=${caseId}`, { headers })
          ).json()
        ).length,
    )
    .toBe(4);
  // Exercise the UI boundary with controlled model scores while retaining the real review/send API.
  await page.route(`**/api/proposals?case_id=${caseId}`, async (route) => {
    const response = await route.fetch();
    const proposals = await response.json();
    const confidence = {
      "CONF-F1": 0.91,
      "CONF-F2": 0.9,
      "CONF-F3": null,
      "CONF-F4": 0.99,
    };
    await route.fulfill({
      response,
      json: proposals.map((p) => ({
        ...p,
        confidence: confidence[p.field_id],
      })),
    });
  });
  await login(page);
  await expect(
    page.getByRole("button", { name: "Import CSV", exact: true }),
  ).toHaveCount(0);
  await expect(
    page.getByRole("button", { name: "Sync inbox", exact: true }),
  ).toHaveCount(0);
  await expect(
    page.getByRole("button", { name: "Check due cases", exact: true }),
  ).toHaveCount(0);
  await expect(
    page.getByText("Backend connected", { exact: true }),
  ).toHaveCount(0);
  await page
    .locator(".stats")
    .getByRole("button", { name: /Review needed/ })
    .click();
  await page.getByRole("button").filter({ hasText: "CONF-ARTICLE" }).click();
  const rowsUI = page.getByTestId("proposal-review");
  await expect(rowsUI.first()).toContainText("Unknown confidence");
  await expect(rowsUI.nth(1)).toContainText("Threshold answer");
  await expect(
    page
      .locator('[data-testid="proposal-review"][data-field-id="CONF-F1"]')
      .getByLabel("Data point decision"),
  ).toHaveValue("approve");
  await expect(
    page
      .locator('[data-testid="proposal-review"][data-field-id="CONF-F2"]')
      .getByLabel("Data point decision"),
  ).toHaveValue("reject");
  await expect(
    page.locator('[data-testid="proposal-review"][data-field-id="CONF-F2"]'),
  ).toContainText("Optional · Freetext");
  await expect(
    page
      .locator('[data-testid="proposal-review"][data-field-id="CONF-F4"]')
      .getByLabel("Data point decision"),
  ).toHaveValue("reject");
  await expect(
    page
      .locator('[data-testid="proposal-review"][data-field-id="CONF-F4"]')
      .getByLabel("Rejection reason"),
  ).not.toHaveValue("");
  await expect(
    page.getByRole("columnheader", { name: /Accepted value/ }),
  ).toHaveCount(0);
  await expect(rowsUI.first().getByLabel("Received value")).toHaveAttribute(
    "readonly",
    "",
  );
  const submit = page.getByRole("button", {
    name: "Submit reply review",
    exact: true,
  });
  await expect(submit).toBeDisabled();
  await page
    .locator('[data-testid="proposal-review"][data-field-id="CONF-F2"]')
    .getByLabel("Rejection reason")
    .fill("Please clarify the material composition.");
  await page
    .locator('[data-testid="proposal-review"][data-field-id="CONF-F3"]')
    .getByLabel("Rejection reason")
    .fill("Please attach supporting evidence.");
  await page.getByRole("button", { name: /Agent confidence/ }).click();
  await expect(rowsUI.first()).toContainText("Certificate date");
  await rowsUI.first().scrollIntoViewIfNeeded();
  await page.screenshot({
    path: ".data/screenshots/confidence-review.png",
    fullPage: true,
  });
  await submit.click();
  await expect(
    page.getByText(
      "Reply review saved. Supplier correction email queued for immediate delivery.",
      { exact: true },
    ),
  ).toBeVisible();
  await expect
    .poll(
      async () =>
        (
          await (
            await request.get(`/api/drafts?case_id=${caseId}`, { headers })
          ).json()
        ).find((d) => d.kind === "rejection_followup")?.status,
    )
    .toBe("simulated");
  const drafts = await (
    await request.get(`/api/drafts?case_id=${caseId}`, { headers })
  ).json();
  const followups = drafts.filter((d) => d.kind === "rejection_followup");
  expect(followups).toHaveLength(1);
  expect(followups[0].body).toContain(
    "Please clarify the material composition.",
  );
  expect(followups[0].body).toContain("Please attach supporting evidence.");
  await page.getByRole("button", { name: "Close review", exact: true }).click();
  await page.getByRole("button", { name: /Reply evaluation agent/ }).click();
  await page.locator(".agent-history-row").first().click();
  await expect(
    page.getByRole("tab", { name: /Supplier review/ }),
  ).toHaveAttribute("aria-selected", "true");
});

test("request columns sort and the alerts button is removed", async ({
  page,
}) => {
  const base = {
    supplier_id: "STATUS-SUP",
    outstanding_count: 2,
    last_sent_at: "2026-01-01T00:00:00",
    last_reply_at: null,
  };
  await page.route("**/api/cases?offset=0&limit=500", (route) =>
    route.fulfill({
      json: [
        {
          ...base,
          id: "status-a",
          nart: "A1",
          supplier_name: "Zeta Supplier",
          status: "email_review",
          next_action_at: null,
        },
        {
          ...base,
          id: "status-b",
          nart: "B1",
          supplier_name: "Alpha Supplier",
          status: "awaiting_reply",
          next_action_at: "2020-01-01T00:00:00",
        },
        {
          ...base,
          id: "status-c",
          nart: "C1",
          supplier_name: "Beta Supplier",
          status: "data_review",
          next_action_at: null,
        },
      ],
    }),
  );
  await page.route("**/api/jobs", (route) => route.fulfill({ json: [] }));
  await login(page);
  await page
    .getByRole("button", { name: "Sort by Supplier", exact: true })
    .click();
  await expect(page.locator(".table-row .supplier-name")).toHaveText([
    "Alpha Supplier",
    "Beta Supplier",
    "Zeta Supplier",
  ]);
  await page
    .getByRole("button", { name: "Sort by Supplier", exact: true })
    .click();
  await expect(page.locator(".table-row .supplier-name")).toHaveText([
    "Zeta Supplier",
    "Beta Supplier",
    "Alpha Supplier",
  ]);
  await expect(page.getByRole("button", { name: /Alerts/ })).toHaveCount(0);
});

test("two compact agent cards open paginated supplier histories without internal IDs", async ({
  page,
}) => {
  await page.route("**/api/agents", (route) =>
    route.fulfill({
      json: [
        {
          id: "email",
          name: "Email agent",
          total: 52,
          suppliers: 10,
          completed: 50,
          active: 2,
        },
        {
          id: "evaluation",
          name: "Reply evaluation agent",
          total: 12,
          suppliers: 7,
          completed: 11,
          active: 1,
        },
      ],
    }),
  );
  await page.route("**/api/agents/email/activity?*", (route) => {
    const older = route.request().url().includes("offset=50");
    return route.fulfill({
      json: {
        agent: "email",
        name: "Email agent",
        total: 52,
        items: [
          {
            id: "internal-work-id",
            case_id: "internal-case-id",
            supplier_name: older ? "Earlier Supplier" : "Most Recent Supplier",
            article: "Article A",
            status: "sent",
            work: "Information request",
            last_touched_at: older
              ? "2020-01-01T00:00:00"
              : "2025-01-01T00:00:00",
            automatically_accepted: 0,
          },
        ],
      },
    });
  });
  await login(page);
  await expect(page.locator(".stats .stat-card")).toHaveCount(5);
  await expect(
    page
      .getByRole("navigation")
      .getByRole("button", { name: /Alerts|Active agents/ }),
  ).toHaveCount(0);
  await expect(
    page.locator(".hero-actions").getByRole("button", { name: /Alerts/ }),
  ).toHaveCount(0);
  await expect(page.locator(".stats .stat-card .stat-note")).toHaveCount(0);
  await page.getByRole("button", { name: /History E-mail agent/ }).click();
  await expect(
    page.getByRole("heading", { name: "Email agent", exact: true }),
  ).toBeVisible();
  await expect(page.locator(".agent-history-row")).toContainText(
    "Most Recent Supplier",
  );
  await expect(page.locator(".agent-history-row")).not.toContainText(
    "internal-",
  );
  await expect(
    page.getByText("52 emails · 10 suppliers", { exact: true }),
  ).toBeVisible();
  await page
    .getByRole("button", { name: "Older activity", exact: true })
    .click();
  await expect(page.locator(".agent-history-row")).toContainText(
    "Earlier Supplier",
  );
  await page
    .getByRole("button", { name: "Newer activity", exact: true })
    .click();
  await expect(page.locator(".agent-history-row")).toContainText(
    "Most Recent Supplier",
  );
  await page.getByRole("button", { name: "My Dashboard", exact: true }).click();
  await expect(
    page.getByRole("heading", { name: "My Dashboard", exact: true }),
  ).toBeVisible();
  await page.screenshot({
    path: ".data/screenshots/two-agent-dashboard.png",
    fullPage: false,
  });
});
