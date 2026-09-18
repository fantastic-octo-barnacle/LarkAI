export class ApiError extends Error {
  constructor(
    public status: number,
    message: string,
  ) {
    super(message);
  }
}
let csrf = "";
export function setCsrf(token: string) {
  csrf = token;
}
export async function api<T>(
  path: string,
  options: RequestInit = {},
): Promise<T> {
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
export function formatDate(value: string) {
  if (!value) return "No date";
  const date = new Date(value);
  return Number.isNaN(date.valueOf())
    ? value
    : date.toLocaleString([], { dateStyle: "medium", timeStyle: "short" });
}
export function safeUrl(value: string) {
  try {
    const url = new URL(value);
    return ["https:", "http:"].includes(url.protocol) ? url.href : undefined;
  } catch {
    return undefined;
  }
}
