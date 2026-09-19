import type { Task } from "./types";
export const parents = (task: Task) => task.parent_ids ?? [];
export const dependencies = (task: Task) => task.dependency_ids ?? [];
export function reachable(
  start: string,
  links: Map<string, string[]>,
): Set<string> {
  const visited = new Set<string>();
  const pending = [...(links.get(start) ?? [])];
  while (pending.length) {
    const id = pending.pop()!;
    if (visited.has(id)) continue;
    visited.add(id);
    pending.push(...(links.get(id) ?? []));
  }
  return visited;
}
export function graphIndex(tasks: Task[]) {
  const byId = new Map(tasks.map((task) => [task.id, task]));
  const upstream = new Map(tasks.map((task) => [task.id, dependencies(task)]));
  const downstream = new Map<string, string[]>();
  const children = new Map<string, string[]>();
  for (const task of tasks) {
    for (const id of dependencies(task))
      downstream.set(id, [...(downstream.get(id) ?? []), task.id]);
    for (const id of parents(task))
      children.set(id, [...(children.get(id) ?? []), task.id]);
  }
  const hierarchy = new Map(tasks.map((task) => [task.id, parents(task)]));
  const cycles = new Set(
    tasks
      .filter((task) => reachable(task.id, upstream).has(task.id))
      .map((task) => task.id),
  );
  const hierarchyCycles = new Set(
    tasks
      .filter((task) => reachable(task.id, hierarchy).has(task.id))
      .map((task) => task.id),
  );
  return { byId, upstream, downstream, children, cycles, hierarchyCycles };
}
export function isBlocked(task: Task, byId: Map<string, Task>) {
  return (
    !["completed", "cancelled"].includes(task.status) &&
    dependencies(task).some((id) => byId.get(id)?.status !== "completed")
  );
}
export function graphScope(
  tasks: Task[],
  selected: string,
  upstream: boolean,
  downstream: boolean,
  all: boolean,
  showHierarchy = false,
) {
  const index = graphIndex(tasks);
  if (all)
    return new Set([
      ...tasks.map((t) => t.id),
      ...tasks.flatMap(dependencies),
      ...(showHierarchy ? tasks.flatMap(parents) : []),
    ]);
  const scope = new Set(
    [
      selected,
      ...(upstream
        ? reachable(selected, index.upstream)
        : (index.upstream.get(selected) ?? [])),
      ...(downstream
        ? reachable(selected, index.downstream)
        : (index.downstream.get(selected) ?? [])),
    ].filter(Boolean),
  );
  if (showHierarchy) {
    // Include the selected task's subtasks and the ancestors of visible tasks.
    for (const id of reachable(selected, index.children)) scope.add(id);
    const pending = [...scope];
    while (pending.length) {
      for (const id of index.byId.get(pending.pop()!)?.parent_ids ?? []) {
        if (!scope.has(id)) {
          scope.add(id);
          pending.push(id);
        }
      }
    }
  }
  return scope;
}
// Layer the acyclic portion left-to-right. Imported cycles remain visible in a
// separate final column, avoiding recursive layout failures or hidden records.
export function graphLayout(
  tasks: Task[],
  scope: Set<string>,
  showHierarchy = false,
) {
  const incoming = new Map([...scope].map((id) => [id, 0]));
  const outgoing = new Map<string, string[]>();
  const edges: {
    from: string;
    to: string;
    kind: "dependency" | "hierarchy";
  }[] = [];
  for (const task of tasks)
    if (scope.has(task.id)) {
      for (const from of dependencies(task))
        if (scope.has(from)) {
          edges.push({ from, to: task.id, kind: "dependency" });
          incoming.set(task.id, incoming.get(task.id)! + 1);
          outgoing.set(from, [...(outgoing.get(from) ?? []), task.id]);
        }
    }
  if (showHierarchy)
    for (const task of tasks)
      if (scope.has(task.id)) {
        for (const from of parents(task))
          if (scope.has(from)) {
            edges.push({ from, to: task.id, kind: "hierarchy" });
            // Mixed relationship types may form loops without either graph being
            // cyclic. Draw every edge, but only use safe hierarchy edges for ranking.
            if (from !== task.id && !reachable(task.id, outgoing).has(from)) {
              incoming.set(task.id, incoming.get(task.id)! + 1);
              outgoing.set(from, [...(outgoing.get(from) ?? []), task.id]);
            }
          }
      }
  const queue = [...scope].filter((id) => incoming.get(id) === 0);
  const rank = new Map(queue.map((id) => [id, 0]));
  for (let cursor = 0; cursor < queue.length; cursor++) {
    const id = queue[cursor];
    for (const next of outgoing.get(id) ?? []) {
      rank.set(next, Math.max(rank.get(next) ?? 0, rank.get(id)! + 1));
      incoming.set(next, incoming.get(next)! - 1);
      if (incoming.get(next) === 0) queue.push(next);
    }
  }
  const fallback = Math.max(0, ...rank.values()) + 1;
  const columns = new Map<number, string[]>();
  for (const id of scope) {
    const column = incoming.get(id)! > 0 ? fallback : (rank.get(id) ?? 0);
    columns.set(column, [...(columns.get(column) ?? []), id]);
  }
  const height = Math.max(
    360,
    ...[...columns.values()].map((ids) => ids.length * 126 + 48),
  );
  const nodes = [...columns].flatMap(([column, ids]) =>
    ids.map((id, row) => ({
      id,
      x: 28 + column * 290,
      y: (height - ids.length * 126) / 2 + row * 126,
    })),
  );
  return {
    nodes,
    edges,
    width: Math.max(580, (Math.max(0, ...columns.keys()) + 1) * 290 + 28),
    height,
  };
}
