import { expect, test } from "@playwright/test";

test("renders the professional dashboard shell", async ({ page }) => {
  await page.goto("/");
  await expect(page.getByRole("heading", { name: /Mundial 2030/i })).toBeVisible();
  await expect(page.getByRole("button", { name: "SIMULAR EN MI PC" })).toBeVisible();
  await expect(page.getByRole("navigation", { name: "Secciones" })).toBeVisible();
});

test("exposes the guarded Sirius human review workflow", async ({ page }) => {
  await page.goto("/");
  await page.getByRole("button", { name: "Sirius", exact: true }).click();
  await expect(
    page.getByRole("heading", { name: "Candidatos del archivo → evidencia estructurada" })
  ).toBeVisible();
  await expect(page.getByLabel("API key de revisión")).toHaveAttribute("type", "password");
  await expect(page.getByRole("button", { name: "Sincronizar archivo" })).toBeVisible();
});
