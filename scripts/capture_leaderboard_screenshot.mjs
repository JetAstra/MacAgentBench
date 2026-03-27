import { mkdir } from "node:fs/promises";
import path from "node:path";
import { fileURLToPath } from "node:url";
import { chromium } from "playwright";

const __filename = fileURLToPath(import.meta.url);
const __dirname = path.dirname(__filename);
const repoRoot = path.resolve(__dirname, "..");

const LEADERBOARD_URL =
  process.env.LEADERBOARD_URL || "https://jetastra.github.io/MacAgentBench/";
const OUTPUT_PATH =
  process.env.LEADERBOARD_SCREENSHOT_PATH ||
  path.join(repoRoot, "assets", "leaderboard.png");

async function main() {
  await mkdir(path.dirname(OUTPUT_PATH), { recursive: true });

  const browser = await chromium.launch({ headless: true });

  try {
    const page = await browser.newPage({
      viewport: { width: 1600, height: 1400 },
      deviceScaleFactor: 2,
    });

    await page.goto(LEADERBOARD_URL, {
      waitUntil: "networkidle",
      timeout: 120000,
    });

    await page.locator("#leaderboard-root .leaderboard-table").waitFor({
      state: "visible",
      timeout: 120000,
    });

    const rankingsSection = page.locator("#rankings");
    await rankingsSection.screenshot({
      path: OUTPUT_PATH,
      type: "png",
    });
  } finally {
    await browser.close();
  }
}

main().catch((error) => {
  console.error(error);
  process.exitCode = 1;
});
