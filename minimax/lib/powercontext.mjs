const baseUrl = (process.env.POWERCONTEXT_URL ?? "http://127.0.0.1:8000").replace(/\/$/, "");
const token = process.env.POWERCONTEXT_TOKEN ?? "";

export async function powerContextPost(path, payload) {
  const response = await fetch(`${baseUrl}${path}`, {
    method: "POST",
    headers: {
      "content-type": "application/json",
      ...(token ? { authorization: `Bearer ${token}` } : {}),
    },
    body: JSON.stringify(payload),
  });
  const text = await response.text();
  let body;
  try {
    body = text ? JSON.parse(text) : {};
  } catch {
    body = { raw: text };
  }
  if (!response.ok) {
    throw new Error(`PowerContext ${path} failed: HTTP ${response.status} ${text}`);
  }
  return body;
}

export function powerContextUrl() {
  return baseUrl;
}
