import { expect, test, type Page, type Route, type TestInfo } from "@playwright/test";

interface PlanRecommendation {
  sku_id: string;
  recommended_qty: number;
  required_cash_rp: number;
}

interface PlanResponse {
  run_id: string;
  budget_allocated_rp: number;
  expected_nov_contribution_rp: number;
  recommendations: PlanRecommendation[];
}

async function chooseDemo(page: Page) {
  await page.goto("/");
  await page.getByRole("button", { name: "Pilih Data Demo" }).click();
  await expect(page.getByRole("heading", { name: "Laporan Kesiapan Data" })).toBeVisible();
  await page.getByRole("button", { name: "Lanjutkan" }).click();
  await expect(page).toHaveURL(/\/atur$/);
  await expect(page.getByRole("button", { name: "Buat Rencana Restock" })).toBeEnabled();
}

async function createPlan(page: Page, budget: number): Promise<PlanResponse> {
  await chooseDemo(page);
  await page.getByLabel("Modal restock tersedia").fill(String(budget));

  const responsePromise = page.waitForResponse(
    (response) =>
      response.request().method() === "POST" && response.url().endsWith("/api/v2/decision-runs"),
  );
  await page.getByRole("button", { name: "Buat Rencana Restock" }).click();
  const response = await responsePromise;
  expect(response.status()).toBe(200);
  return (await response.json()) as PlanResponse;
}

async function capture(page: Page, testInfo: TestInfo, name: string) {
  await page.screenshot({
    path: testInfo.outputPath(name),
    fullPage: true,
  });
}

test("zero-budget produces a truthful empty plan", async ({ page }, testInfo) => {
  const plan = await createPlan(page, 0);

  await expect(page).toHaveURL(/\/rencana$/);
  await expect(page.getByRole("heading", { name: "Rencana kosong" })).toBeVisible();
  expect(plan.budget_allocated_rp).toBe(0);
  expect(plan.expected_nov_contribution_rp).toBe(0);
  expect(plan.recommendations).toHaveLength(31);
  expect(
    plan.recommendations.every(
      (recommendation) =>
        recommendation.recommended_qty === 0 && recommendation.required_cash_rp === 0,
    ),
  ).toBe(true);
  await capture(page, testInfo, "zero-budget-plan.png");
});

test("authoritative workflow survives races and failures without fake state", async ({
  page,
}, testInfo) => {
  const plan = await createPlan(page, 10_000_000);
  const positive = plan.recommendations.filter((item) => item.recommended_qty > 0);
  expect(positive.length).toBeGreaterThanOrEqual(2);

  await expect(page.getByText("SKU dengan qty rekomendasi > 0")).toBeVisible();
  const firstCard = page.locator("article").filter({ hasText: positive[0].sku_id });
  await firstCard.getByRole("button", { name: "Setujui", exact: true }).click();
  await expect(firstCard.getByRole("button", { name: "Disetujui", exact: true })).toBeVisible();

  await firstCard.getByRole("button", { name: "Edit", exact: true }).click();
  const quantity = firstCard.getByLabel("Jumlah unit");
  await quantity.fill("0");
  await quantity.press("Enter");
  await expect(
    firstCard.getByText("Jumlah SKU yang disetujui harus lebih dari 0 unit."),
  ).toBeVisible();
  await expect(firstCard.getByRole("button", { name: "Disetujui", exact: true })).toBeVisible();

  await firstCard.locator("button").first().click();
  await expect(page.getByText(/Perkiraan permintaan kumulatif H\+/)).toBeVisible();
  await page.getByRole("button", { name: "Tutup detail" }).click();

  await page.getByRole("link", { name: /Mode Evaluasi/ }).click();
  await expect(page.getByText(/Akurasi backtest .* tidak ditampilkan/)).toBeVisible();
  await capture(page, testInfo, "evaluation-truthfulness.png");
  await page.goBack();
  await expect(page).toHaveURL(/\/rencana$/);

  let releaseMutation: (() => void) | undefined;
  const delayedMutationPattern = "**/api/v2/decision-runs/*/recommendations/*";
  const delayedMutationHandler = async (route: Route) => {
    if (route.request().method() !== "PATCH") {
      await route.continue();
      return;
    }
    await new Promise<void>((resolve) => {
      releaseMutation = resolve;
    });
    await route.continue();
  };
  await page.route(delayedMutationPattern, delayedMutationHandler);

  const secondCard = page.locator("article").filter({ hasText: positive[1].sku_id });
  const secondApprove = secondCard.getByRole("button", { name: "Setujui", exact: true });
  await secondApprove.click();
  await expect.poll(() => Boolean(releaseMutation)).toBe(true);
  await expect(secondApprove).toBeDisabled();

  await page.getByRole("button", { name: "Konfirmasi & Ekspor" }).click();
  await expect(page.getByText(/Tunggu perubahan SKU selesai disimpan/)).toBeVisible();
  await expect(page.getByRole("button", { name: "Konfirmasi Pesanan" })).toBeDisabled();

  const mutationResponsePromise = page.waitForResponse(
    (response) =>
      response.request().method() === "PATCH" &&
      response.url().includes(`/api/v2/decision-runs/${plan.run_id}/recommendations/`),
  );
  releaseMutation?.();
  const mutationResponse = await mutationResponsePromise;
  expect(mutationResponse.ok()).toBe(true);
  await page.unroute(delayedMutationPattern, delayedMutationHandler);
  await expect(page.getByText(/Tunggu perubahan SKU selesai disimpan/)).not.toBeVisible();
  await expect(page.getByRole("button", { name: "Konfirmasi Pesanan" })).toBeEnabled();

  await page.route(`**/api/v2/decision-runs/${plan.run_id}/confirm`, async (route) => {
    await route.fulfill({
      status: 503,
      contentType: "application/json",
      body: JSON.stringify({ detail: "forced confirm failure" }),
    });
  });
  await page.getByRole("button", { name: "Konfirmasi Pesanan" }).click();
  await expect(page.getByText("forced confirm failure")).toBeVisible();
  await expect(page.getByRole("heading", { name: "Pesanan dikonfirmasi" })).not.toBeVisible();
  await capture(page, testInfo, "confirm-failure.png");

  const historyResponse = await page.request.get("/api/v2/decision-runs/history");
  expect(historyResponse.ok()).toBe(true);
  const history = (await historyResponse.json()) as Array<{ id: string }>;
  expect(history.some((row) => row.id === plan.run_id)).toBe(false);

  await page.getByRole("button", { name: "Atur Keputusan" }).click();
  await page.getByLabel("Modal restock tersedia").fill("9000000");
  await expect(page.getByRole("button", { name: "3 Rencana Restock", exact: true })).toBeDisabled();
});
