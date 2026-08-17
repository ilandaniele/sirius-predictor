import { expect, test } from "@playwright/test";

test("renders the professional dashboard shell", async ({ page }) => {
  await page.goto("/");
  await expect(page.getByRole("heading", { name: /Mundial 2030/i })).toBeVisible();
  await expect(page.getByRole("button", { name: "ACTUALIZAR MUNDIAL 2030" })).toBeVisible();
  await expect(page.getByRole("navigation", { name: "Secciones" })).toBeVisible();
});
