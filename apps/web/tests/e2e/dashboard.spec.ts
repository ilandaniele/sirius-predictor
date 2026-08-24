import { expect, test } from "@playwright/test";

test("renders the professional dashboard shell", async ({ page }) => {
  await page.goto("/");
  await expect(page.getByRole("heading", { name: /Mundial 2030/i })).toBeVisible();
  await expect(page.getByRole("button", { name: "SIMULAR EN MI PC" })).toBeVisible();
  await expect(page.getByRole("navigation", { name: "Secciones" })).toBeVisible();
});

test("exposes the guarded Sirius and Astrología Argumental human review workflows", async ({
  page,
}) => {
  await page.goto("/");
  await page.getByRole("button", { name: "Astrología", exact: true }).click();

  const siriusQueue = page.locator("article.review-queue", { hasText: "SIRIUS" });
  await expect(
    siriusQueue.getByRole("heading", { name: "Candidatos del archivo → evidencia estructurada" })
  ).toBeVisible();
  await expect(siriusQueue.getByLabel("API key de revisión")).toHaveAttribute("type", "password");
  await expect(siriusQueue.getByRole("button", { name: "Sincronizar archivo" })).toBeVisible();

  const argumentalQueue = page.locator("article.review-queue", {
    hasText: "ASTROLOGÍA ARGUMENTAL",
  });
  await expect(
    argumentalQueue.getByRole("heading", {
      name: "Candidatos del archivo → evidencia estructurada",
    })
  ).toBeVisible();
});
