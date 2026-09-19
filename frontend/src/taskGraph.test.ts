import { expect, it } from "vitest";
import type { Task } from "./types";
import { graphIndex, graphLayout, graphScope, isBlocked } from "./taskGraph";
function task(
  id: string,
  deps: string[] = [],
  parent: string[] = [],
  status = "pending",
): Task {
  return {
    id,
    title: id,
    dependency_ids: deps,
    parent_ids: parent,
    status,
    remote_id: id,
    source: "mock",
    table_id: "",
    description: "",
    due: "",
    priority: "NORMAL",
    owners: [],
    divisions: [],
    category: "",
    url: "",
    updated_at: "",
  };
}
it("keeps hierarchy separate from execution edges and includes cross-parent dependencies", () => {
  const tasks = [
    task("parent"),
    task("a", [], ["parent"], "completed"),
    task("b", ["a"], ["parent"]),
    task("c", ["b"]),
    task("d", ["c"]),
  ];
  const index = graphIndex(tasks);
  expect(index.downstream.get("a")).toEqual(["b"]);
  expect(index.children.get("parent")).toEqual(["a", "b"]);
  expect(isBlocked(tasks[2], index.byId)).toBe(false);
  expect(isBlocked(tasks[3], index.byId)).toBe(true);
  expect(graphScope(tasks, "b", false, false, false)).toEqual(
    new Set(["a", "b", "c"]),
  );
  expect(graphScope(tasks, "b", false, true, false)).toEqual(
    new Set(["a", "b", "c", "d"]),
  );
  const layout = graphLayout(tasks, new Set(tasks.map((t) => t.id)));
  const x = (id: string) => layout.nodes.find((n) => n.id === id)!.x;
  expect(x("a")).toBeLessThan(x("b"));
  expect(x("b")).toBeLessThan(x("c"));
  expect(layout.edges).not.toContainEqual({
    from: "parent",
    to: "a",
    kind: "dependency",
  });
});
it("terminates on imported cycles and retains unavailable dependencies", () => {
  const tasks = [
    task("a", ["b"]),
    task("b", ["a"]),
    task("c", ["b", "missing"]),
  ];
  const index = graphIndex(tasks);
  expect(index.cycles).toEqual(new Set(["a", "b"]));
  const scope = graphScope(tasks, "c", true, true, false);
  expect(scope).toEqual(new Set(["a", "b", "c", "missing"]));
  const layout = graphLayout(tasks, scope);
  expect(layout.nodes).toHaveLength(4);
  expect(
    layout.nodes.every(
      (node) => Number.isFinite(node.x) && Number.isFinite(node.y),
    ),
  ).toBe(true);
  expect(isBlocked(tasks[2], index.byId)).toBe(true);
});
it("cancelled prerequisites remain blocking and terminal tasks aren't blocked", () => {
  const tasks = [
    task("a", [], [], "cancelled"),
    task("b", ["a"]),
    task("c", ["a"], [], "completed"),
  ];
  const index = graphIndex(tasks);
  expect(isBlocked(tasks[1], index.byId)).toBe(true);
  expect(isBlocked(tasks[2], index.byId)).toBe(false);
});

it("shows hierarchy links without treating them as blockers, including mixed-type loops", () => {
  const tasks = [
    task("parent", ["child"]),
    task("child", [], ["parent"]),
    task("leaf", [], ["child"]),
  ];
  const scope = graphScope(tasks, "parent", false, false, false, true);
  expect(scope).toEqual(new Set(["parent", "child", "leaf"]));
  const layout = graphLayout(tasks, scope, true);
  expect(layout.edges).toContainEqual({
    from: "parent",
    to: "child",
    kind: "hierarchy",
  });
  expect(layout.edges).toContainEqual({
    from: "child",
    to: "parent",
    kind: "dependency",
  });
  expect(layout.edges).toHaveLength(3);
  expect(new Set(layout.nodes.map((n) => `${n.x}:${n.y}`)).size).toBe(3);
  expect(graphIndex(tasks).cycles.size).toBe(0);
  expect(isBlocked(tasks[1], graphIndex(tasks).byId)).toBe(false);
  expect(graphLayout(tasks, scope, false).edges).toHaveLength(1);
});
