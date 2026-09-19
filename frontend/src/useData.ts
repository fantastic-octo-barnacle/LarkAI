import { useState, useEffect, useRef } from "react";
import { api } from "./api";

export function useData<T>(
  path: string | undefined,
  revision = 0,
  retainOnRefresh = false,
) {
  const previousPath = useRef(path);
  const [data, setData] = useState<T>();
  const [error, setError] = useState<Error>();
  useEffect(() => {
    if (path === undefined) return;
    const controller = new AbortController();
    setError(undefined);
    if (!retainOnRefresh || previousPath.current !== path) setData(undefined);
    previousPath.current = path;
    api<T>(path, { signal: controller.signal })
      .then(setData)
      .catch((e) => {
        if (!controller.signal.aborted) setError(e);
      });
    return () => controller.abort();
  }, [path, revision, retainOnRefresh]);
  return { data, error };
}
