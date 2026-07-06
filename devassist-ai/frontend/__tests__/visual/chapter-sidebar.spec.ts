import { test, expect } from '@playwright/test';

test('chapter sidebar visual regression', async ({ page }) => {
  await page.goto('/reviews/1');
  // Wait for chapters to load
  await page.waitForSelector('aside h3:has-text("Chapters")');
  
  // Assert visual screenshot of sidebar
  const sidebar = page.locator('aside').first();
  await expect(sidebar).toHaveScreenshot('chapter-sidebar.png');
});
