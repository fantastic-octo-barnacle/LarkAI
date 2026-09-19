import { test, expect } from "@playwright/test";
test("mock workspace supports login, task lifecycle, workload and notifications", async ({
  page,
}) => {
  const errors: string[] = [];
  page.on("pageerror", (e) => errors.push(e.message));
  await page.goto("/tasks");
  await expect(page.getByText("Sign in to continue")).toBeVisible();
  await page.getByRole("link", { name: "Continue", exact: false }).click();
  await expect(page.getByText("Demo Driver", { exact: true })).toBeVisible();
  await page.getByRole("button", { name: "New task" }).click();
  await page
    .getByLabel("Title", { exact: true })
    .fill("Validate drivetrain firmware");
  await page
    .getByLabel("Description", { exact: true })
    .fill("Run the bench test before assembly.");
  await page.getByLabel("Due date").fill("2030-01-01T12:00");
  await page.getByLabel("Priority", { exact: true }).selectOption("HIGH");
  await page.getByRole("button", { name: "Create task", exact: true }).click();
  await expect(
    page.getByRole("heading", { name: "Validate drivetrain firmware" }),
  ).toBeVisible();
  await page.getByRole("link", { name: "Workload", exact: true }).click();
  await expect(page.getByText("1 active", { exact: true })).toBeVisible();
  await page.getByRole("link", { name: "Tasks", exact: true }).click();
  await page.getByRole("button", { name: "Complete", exact: true }).click();
  await expect(
    page.getByRole("heading", { name: "completed 1" }),
  ).toBeVisible();
  await page.getByRole("link", { name: "Notifications", exact: true }).click();
  await expect(
    page.getByText(/Task completed: Validate drivetrain firmware/),
  ).toBeVisible();
  await page.getByRole("link", { name: "Tasks", exact: true }).click();
  await page
    .getByRole("button", { name: "Delete Validate drivetrain firmware" })
    .click();
  await page
    .getByRole("button", { name: "Confirm delete", exact: true })
    .click();
  await expect(
    page.getByText("No tasks match.", { exact: false }),
  ).toBeVisible();
  await page.getByRole("link", { name: "Overview", exact: true }).click();
  await expect(
    page.getByRole("heading", { name: "Team overview" }),
  ).toBeVisible();
  await page.screenshot({
    path: "test-results/overview.png",
    fullPage: true,
    animations: "disabled",
  });
  await page.setViewportSize({ width: 390, height: 844 });
  await expect(
    page.getByRole("heading", { name: "Team overview" }),
  ).toBeVisible();
  expect(
    await page.evaluate(
      () => document.documentElement.scrollWidth <= window.innerWidth,
    ),
  ).toBe(true);
  await expect(page.locator(".sidebar")).toHaveCSS(
    "transform",
    "matrix(1, 0, 0, 1, -210, 0)",
  );
  await page.screenshot({
    path: "test-results/mobile.png",
    fullPage: true,
    animations: "disabled",
  });
  expect(errors).toEqual([]);
});

test("startup bundles session and page data without loading unopened task form options", async ({
  page,
}) => {
  const requests: string[] = [];
  page.on("request", (r) => {
    if (new URL(r.url()).pathname.startsWith("/api/"))
      requests.push(new URL(r.url()).pathname);
  });
  await page.goto("/auth/feishu?next=/tasks");
  await expect(page.getByRole("button", { name: "New task" })).toBeVisible();
  await expect(
    page.getByText("No tasks match.", { exact: false }),
  ).toBeVisible();
  expect(requests).toEqual(["/api/bootstrap"]);
  requests.length = 0;
  await page.reload();
  await expect(
    page.getByText("No tasks match.", { exact: false }),
  ).toBeVisible();
  expect(requests).toEqual(["/api/bootstrap"]);
});

test("theme and language persist while task drafts and API values stay intact", async ({
  page,
}) => {
  await page.emulateMedia({ colorScheme: "light" });
  await page.goto("/auth/feishu?next=/tasks");
  await page.getByRole("button", { name: "New task" }).click();
  await page.getByLabel("Title", { exact: true }).fill("Bilingual draft");
  await page.getByRole("button", { name: "Switch to dark mode" }).click();
  await expect(page.locator("html")).toHaveAttribute("data-theme", "dark");
  await expect(page.locator(".topbar")).toHaveCSS(
    "background-color",
    "rgb(28, 38, 55)",
  );
  await page.getByLabel("Language", { exact: true }).selectOption("zh");
  await expect(page.locator("html")).toHaveAttribute("lang", "zh-CN");
  await expect(page.getByRole("heading", { name: "任务看板" })).toBeVisible();
  await expect(page.getByLabel("标题", { exact: true })).toHaveValue(
    "Bilingual draft",
  );
  await page.getByLabel("优先级", { exact: true }).selectOption("HIGH");
  await expect(page.getByLabel("优先级", { exact: true })).toHaveValue("HIGH");
  await page.getByLabel("筛选状态").selectOption("in_progress");
  await expect(page.getByLabel("筛选状态")).toHaveValue("in_progress");
  await page.reload();
  await expect(page.locator("html")).toHaveAttribute("data-theme", "dark");
  await expect(page.getByRole("heading", { name: "任务看板" })).toBeVisible();
  await page.getByRole("link", { name: "概览", exact: true }).click();
  await expect(page.getByRole("heading", { name: "团队概览" })).toBeVisible();
  await page.setViewportSize({ width: 390, height: 844 });
  await expect(page.getByLabel("语言", { exact: true })).toBeVisible();
  expect(
    await page.evaluate(
      () => document.documentElement.scrollWidth <= innerWidth,
    ),
  ).toBe(true);
  await page.screenshot({
    path: "test-results/dark-chinese-mobile.png",
    animations: "disabled",
    fullPage: true,
  });
  await page.getByRole("button", { name: "切换至浅色模式" }).click();
  await page.getByLabel("语言", { exact: true }).selectOption("en");
  await expect(
    page.getByRole("heading", { name: "Team overview" }),
  ).toBeVisible();
  await expect(page.locator("html")).toHaveAttribute("data-theme", "light");
});

test("system dark mode works when browser storage is unavailable", async ({
  page,
}) => {
  await page.emulateMedia({ colorScheme: "dark" });
  await page.addInitScript(() => {
    Storage.prototype.getItem = () => {
      throw new Error("Storage unavailable");
    };
    Storage.prototype.setItem = () => {
      throw new Error("Storage unavailable");
    };
  });
  await page.goto("/");
  await expect(
    page.getByRole("heading", { name: "Team overview" }),
  ).toBeVisible();
  await expect(page.locator("html")).toHaveAttribute("data-theme", "dark");
  await page.getByRole("button", { name: "Switch to light mode" }).click();
  await page.getByLabel("Language", { exact: true }).selectOption("zh");
  await expect(page.getByRole("heading", { name: "团队概览" })).toBeVisible();
  await expect(page.locator("html")).toHaveAttribute("data-theme", "light");
});
