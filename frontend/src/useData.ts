import { useState, useEffect } from "react";
import { api } from "./api";

export function useData<T>(path: string | undefined, revision = 0) {
  const [data, setData] = useState<T>();
  const [error, setError] = useState<Error>();
  useEffect(() => {
    if (path === undefined) return;
    const controller = new AbortController();
    setError(undefined);
    setData(undefined);
    api<T>(path, { signal: controller.signal })
      .then(setData)
      .catch((e) => {
        if (!controller.signal.aborted) setError(e);
      });
    return () => controller.abort();
  }, [path, revision]);
  return { data, error };
}
