async function requestJson(url, options) {
  const response = await fetch(url, options);
  const data = await response.json().catch(() => ({}));
  if (!response.ok || data.ok === false) {
    throw new Error(data.error ?? `HTTP ${response.status}`);
  }
  return data;
}

export const api = {
  health: () => requestJson("/api/health"),
  stats: (kbId) => requestJson(`/api/kb/${encodeURIComponent(kbId)}/stats`),
  addDocuments: (kbId, documents) =>
    requestJson(`/api/kb/${encodeURIComponent(kbId)}/documents`, {
      method: "POST",
      headers: { "content-type": "application/json" },
      body: JSON.stringify({ documents }),
    }),
  search: (kbId, query, queryEmbedding, nResults = 5) =>
    requestJson(`/api/kb/${encodeURIComponent(kbId)}/search`, {
      method: "POST",
      headers: { "content-type": "application/json" },
      body: JSON.stringify({ query, queryEmbedding, nResults }),
    }),
};
