import { expect, test } from "vitest";
import type { Task } from "./types";
import { needsAttention, taskOrder } from "./taskView";
const task = (id: string, fields: Partial<Task> = {}) =>
  ({
    id,
    title: id,
    status: "pending",
    due: "",
    owners: [],
    ...fields,
  }) as Task;
test("attention excludes finished work, preserves missing blockers, and bounds upcoming dates", () => {
  const now = Date.parse("2026-09-19T12:00:00Z");
  const done = task("done", { status: "completed", due: "2026-01-01" });
  const blocked = task("blocked", { dependency_ids: ["missing"] });
  const soon = task("soon", { due: "2026-09-20T12:00:00Z" });
  const later = task("later", { due: "2026-10-20T12:00:00Z" });
  const byId = new Map([done, blocked, soon, later].map((t) => [t.id, t]));
  expect(needsAttention(done, "overdue", byId, now)).toBe(false);
  expect(needsAttention(done, "unassigned", byId, now)).toBe(false);
  expect(needsAttention(blocked, "blocked", byId, now)).toBe(true);
  expect(needsAttention(soon, "upcoming", byId, now)).toBe(true);
  expect(needsAttention(later, "upcoming", byId, now)).toBe(false);
  expect([done, blocked, later, soon].sort(taskOrder).map((t) => t.id)).toEqual(
    ["soon", "later", "blocked", "done"],
  );
});
