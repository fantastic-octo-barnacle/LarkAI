export class ApiError extends Error {
  constructor(
    public status: number,
    message: string,
  ) {
    super(message);
  }
}
type InitialResult = { data?: unknown; error?: string; status?: number };
const initialData = new Map<string, InitialResult>();
export function primeInitialData(data: Record<string, InitialResult>) {
  initialData.clear();
  for (const [path, result] of Object.entries(data))
    initialData.set(path, result);
}
let csrf = "";
export function setCsrf(token: string) {
  csrf = token;
}
export async function api<T>(
  path: string,
  options: RequestInit = {},
): Promise<T> {
  if (!options.method || options.method === "GET") {
    const initial = initialData.get(path);
    if (initial) {
      initialData.delete(path);
      if (initial.error)
        throw new ApiError(initial.status || 500, initial.error);
      return initial.data as T;
    }
  } else {
    initialData.clear();
  }
  const response = await fetch(`/api${path}`, {
    ...options,
    headers: {
      "Content-Type": "application/json",
      "X-CSRF-Token": csrf,
      ...options.headers,
    },
  });
  const body = await response
    .json()
    .catch(() => ({ error: "The server returned an unexpected response." }));
  if (!response.ok)
    throw new ApiError(
      response.status,
      body.error || `Request failed (${response.status})`,
    );
  return body as T;
}
export function formatDate(value: string, locale = "en") {
  if (!value) return locale.startsWith("zh") ? "无日期" : "No date";
  const date = new Date(value);
  return Number.isNaN(date.valueOf())
    ? value
    : date.toLocaleString(locale, { dateStyle: "medium", timeStyle: "short" });
}
export function safeUrl(value: string) {
  try {
    const url = new URL(value);
    return ["https:", "http:"].includes(url.protocol) ? url.href : undefined;
  } catch {
    return undefined;
  }
}
