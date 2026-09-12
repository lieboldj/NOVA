import { test, expect } from "@playwright/test";
import { readFileSync } from "node:fs";

async function login(page) {
  await page.goto("/");
  await page.getByLabel("Reviewer access key").fill("ui-review-secret");
  await page.getByRole("button", { name: "Sign in", exact: true }).click();
  await expect(
    page.getByRole("heading", { name: "Request operations" }),
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
  await page
    .getByRole("button", { name: "Start process", exact: true })
    .click();
  await expect(
    page.getByText(/No supplier data has been imported yet/),
  ).toBeVisible();
  await page
    .getByRole("button", { name: "Import supplier CSV", exact: true })
    .click();
  await page.getByLabel("Supplier CSV", { exact: true }).setInputFiles({
    name: "supplier.csv",
    mimeType: "text/csv",
    buffer: Buffer.from(columns.join(",") + "\n" + row.join(",") + "\n"),
  });
  await page
    .getByRole("button", { name: "Preview import", exact: true })
    .click();
  await expect(page.getByText("1 fields · 1 suppliers")).toBeVisible();
  await page
    .getByRole("button", { name: "Approve import into database", exact: true })
    .click();
  const starter = page.getByRole("dialog", {
    name: "Start a supplier process",
    exact: true,
  });
  await expect(starter).toBeVisible();
  await starter.getByLabel("Find a supplier or article").fill("UI-ARTICLE");
  await starter
    .getByRole("button")
    .filter({ hasText: "Fictional UI Supplier" })
    .click();
  await expect(
    page.getByRole("button", {
      name: "Prepare request for review",
      exact: true,
    }),
  ).toBeDisabled();
  await page.getByLabel("Process recipient").fill("supplier@example.com");
  await page
    .getByRole("button", { name: "Approve supplier contact", exact: true })
    .click();
  await page
    .getByRole("button", { name: "Prepare request for review", exact: true })
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
  await expect(page.getByText(/Version 2 ·/)).toBeVisible();
  await page.getByRole("button", { name: "Close review", exact: true }).click();
  await page
    .getByRole("button", { name: "Start process", exact: true })
    .click();
  await page
    .getByRole("dialog", { name: "Start a supplier process", exact: true })
    .getByRole("button")
    .filter({ hasText: "Fictional UI Supplier" })
    .click();
  await page
    .getByRole("button", { name: "Review existing email", exact: true })
    .click();
  await expect(page.getByText(/Version 2 ·/)).toBeVisible();
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
  await expect(proposal.getByLabel("Proposed value")).toHaveValue(
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
    .getByRole("button", { name: "Approve data change", exact: true })
    .click();
  await expect(
    page.getByText("Approved value written to the database.", { exact: true }),
  ).toBeVisible();
  detail = await (
    await request.get(`/api/cases/${caseId}`, { headers: apiHeaders })
  ).json();
  expect(detail.fields[0].data["Value submitted"]).toBe(
    "Verified recycled content",
  );
  expect(detail.status).toBe("data_review");
  await page
    .getByRole("button", { name: "Complete reply review", exact: true })
    .click();
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
    extracted.getByText("Unchanged confirmation", { exact: true }),
  ).toBeVisible();
  await expect(
    extracted.getByText("Changed value", { exact: true }),
  ).toBeVisible();
  await expect(extracted.getByText("New value", { exact: true })).toBeVisible();
  await expect(extracted.getByTestId("proposal-review")).toHaveCount(3);
  await expect(
    extracted.getByRole("link", { name: "energy.txt", exact: true }),
  ).toBeVisible();
  await expect(
    extracted.getByRole("button", {
      name: "Complete reply review",
      exact: true,
    }),
  ).toBeDisabled();
  await expect(
    unextracted.getByText(/No extracted values are available/),
  ).toBeVisible();
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
  await extracted
    .getByRole("button", { name: "Approve confirmation", exact: true })
    .click();
  await extracted
    .getByRole("button", { name: "Approve data change", exact: true })
    .first()
    .click();
  await expect(
    extracted.getByRole("button", { name: "Approve data change", exact: true }),
  ).toHaveCount(1);
  await extracted
    .getByRole("button", { name: "Approve data change", exact: true })
    .click();
  await expect(
    extracted.getByRole("button", {
      name: "Complete reply review",
      exact: true,
    }),
  ).toBeEnabled();
  await page.screenshot({
    path: ".data/screenshots/all-supplier-inputs.png",
    fullPage: true,
  });
  expect(
    (await (await request.get(`/api/cases/${caseId}`, { headers })).json())
      .status,
  ).toBe("data_review");
  await extracted
    .getByRole("button", { name: "Complete reply review", exact: true })
    .click();
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
  await page
    .getByRole("button", { name: "Start process", exact: true })
    .click();
  await page
    .getByLabel("Describe your supplier request")
    .fill(
      "For suppliers who are in region APAC and are in automotive industry, send the MDF request.",
    );
  await page
    .getByRole("button", { name: "Preview matching suppliers", exact: true })
    .click();
  const audience = page.getByRole("region", {
    name: "Request questionnaires in natural language",
  });
  await expect(
    audience.getByText("2 suppliers · 2 article cases", { exact: true }),
  ).toBeVisible();
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
    /MDF Information request/,
  );
  await expect(
    page.getByRole("button", { name: "Approve email & send", exact: true }),
  ).toBeEnabled();
});
