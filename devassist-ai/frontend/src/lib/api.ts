export async function readJson<T>(response: Response): Promise<T> {
  const contentType = response.headers.get("content-type") || "";
  const text = await response.text();

  if (!contentType.includes("application/json")) {
    const preview = text.trim().slice(0, 140) || response.statusText;
    throw new Error(
      `Expected JSON from ${response.url || "API"}, got ${contentType || "unknown content type"} (${response.status}). ${preview}`,
    );
  }

  const data = JSON.parse(text) as T;

  if (!response.ok) {
    const detail =
      typeof data === "object" &&
      data !== null &&
      "detail" in data &&
      typeof data.detail === "string"
        ? data.detail
        : `Request failed with ${response.status}`;

    throw new Error(detail);
  }

  return data;
}
