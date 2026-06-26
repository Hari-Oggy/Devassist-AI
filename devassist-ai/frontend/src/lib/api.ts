export async function readJson<T>(response: Response): Promise<T> {
  const contentType = response.headers.get("content-type") || "";
  const text = await response.text();

  if (!contentType.includes("application/json")) {
    const preview = text.trim().slice(0, 140) || response.statusText;
    throw new Error(
      `Expected JSON from ${response.url || "API"}, got ${contentType || "unknown"} (${response.status}). ${preview}`,
    );
  }

  const data = JSON.parse(text) as T;

  if (!response.ok) {
    const detail =
      typeof data === "object" &&
      data !== null &&
      "detail" in data &&
      typeof (data as Record<string, unknown>).detail === "string"
        ? (data as Record<string, unknown>).detail as string
        : `Request failed with status ${response.status}`;
    throw new Error(detail);
  }

  return data;
}

/**
 * The API base URL. Leave blank to use relative paths (recommended in dev
 * — Next.js rewrites `/api/v3/*` → `http://127.0.0.1:8000/api/v3/*`).
 * Set NEXT_PUBLIC_API_URL in .env for production deployments.
 */
export const API_BASE = process.env.NEXT_PUBLIC_API_URL ?? "";

/**
 * Central fetch wrapper with:
 * - Automatic base URL
 * - JSON-only enforcement
 * - Timeout (10 s by default)
 * - Friendly NetworkError messages
 */
export async function apiFetch<T>(
  path: string,
  options?: RequestInit & { timeoutMs?: number },
): Promise<T> {
  const { timeoutMs = 10_000, ...fetchOptions } = options ?? {};
  const controller = new AbortController();
  const timer = setTimeout(() => controller.abort(), timeoutMs);

  const url = `${API_BASE}${path}`;

  try {
    const res = await fetch(url, {
      ...fetchOptions,
      signal: controller.signal,
    });
    return await readJson<T>(res);
  } catch (err) {
    if (err instanceof DOMException && err.name === "AbortError") {
      throw new Error(`Request to ${path} timed out after ${timeoutMs / 1000}s`);
    }
    // TypeError: Failed to fetch / NetworkError
    if (err instanceof TypeError) {
      throw new Error(
        `Cannot reach backend at ${url}. Make sure the API server is running on port 8000.`,
      );
    }
    throw err;
  } finally {
    clearTimeout(timer);
  }
}
