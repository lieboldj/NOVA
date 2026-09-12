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
