// Enabling the automation interface in the settings publishes automation.json;
// disabling it removes the file again.

import { existsSync } from 'node:fs';
import path from 'node:path';

import { expect, test } from '@playwright/test';

import { launchApp } from './support/app';

test('the settings switch starts and stops the automation interface', async () => {
  const { app, page } = await launchApp();
  try {
    const userData = await app.evaluate(({ app: electronApp }) => electronApp.getPath('userData'));
    const info = path.join(userData, 'automation.json');
    await page.keyboard.press('Control+,');
    const toggle = page.getByTestId('settings-automation');
    await expect(toggle).toBeVisible();
    await toggle.click();
    await expect(toggle).toBeVisible();
    await expect(toggle).toBeChecked();
    await expect.poll(() => existsSync(info)).toBe(true);
    await toggle.click();
    await expect.poll(() => existsSync(info)).toBe(false);
  } finally {
    await app.close();
  }
});
