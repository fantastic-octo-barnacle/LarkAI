import { afterEach, expect, it, vi } from "vitest";
import { api, ApiError, setCsrf, safeUrl } from "./api";
afterEach(() => vi.unstubAllGlobals());
it("sends mutations with the server-issued CSRF token", async () => {
  const fetcher = vi.fn().mockResolvedValue(
    new Response('{"ok":true}', {
      headers: { "Content-Type": "application/json" },
    }),
  );
  vi.stubGlobal("fetch", fetcher);
  setCsrf("server-token");
  await api("/tasks", { method: "POST", body: '{"title":"Test"}' });
  expect(fetcher).toHaveBeenCalledWith(
    "/api/tasks",
    expect.objectContaining({
      method: "POST",
      headers: expect.objectContaining({ "X-CSRF-Token": "server-token" }),
    }),
  );
});
it("preserves connection-required errors for the reconnect UI", async () => {
  vi.stubGlobal(
    "fetch",
    vi
      .fn()
      .mockResolvedValue(
        new Response('{"error":"feishu_connection_required"}', { status: 428 }),
      ),
  );
  await expect(api("/tasks")).rejects.toEqual(
    new ApiError(428, "feishu_connection_required"),
  );
});
it("never allows executable links from remote content", () => {
  expect(safeUrl("javascript:alert(1)")).toBeUndefined();
  expect(safeUrl("data:text/html,test")).toBeUndefined();
  expect(safeUrl("https://feishu.cn/task/1")).toBe("https://feishu.cn/task/1");
});
