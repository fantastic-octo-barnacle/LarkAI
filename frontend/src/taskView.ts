import type { Task } from "./types";
import { isBlocked } from "./taskGraph";

export const activeTask = (task: Task) =>
  !["completed", "cancelled"].includes(task.status);
export const overdueTask = (task: Task, now = Date.now()) =>
  activeTask(task) && !!task.due && Date.parse(task.due) < now;
export function needsAttention(
  task: Task,
  filter: string,
  byId: Map<string, Task>,
  now = Date.now(),
) {
  if (!filter) return true;
  if (filter === "overdue") return overdueTask(task, now);
  if (filter === "blocked") return isBlocked(task, byId);
  if (filter === "unassigned") return activeTask(task) && !task.owners.length;
  if (filter === "upcoming")
    return (
      activeTask(task) &&
      Date.parse(task.due) >= now &&
      Date.parse(task.due) <= now + 7 * 86400000
    );
  return true;
}
export function taskOrder(a: Task, b: Task) {
  return (
    Number(activeTask(b)) - Number(activeTask(a)) ||
    (Date.parse(a.due) || Infinity) - (Date.parse(b.due) || Infinity) ||
    a.title.localeCompare(b.title)
  );
}
