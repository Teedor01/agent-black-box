const API_URL = process.env.NEXT_PUBLIC_API_URL;

async function callApi(body) {
  if (!API_URL) {
    throw new Error("NEXT_PUBLIC_API_URL is not set -- copy .env.local.example to .env.local first.");
  }
  const res = await fetch(API_URL, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(body),
  });
  const data = await res.json().catch(() => ({}));
  if (!res.ok) {
    throw new Error(data.error || `Request failed (${res.status})`);
  }
  return data;
}

export function runEpisode(project, query) {
  return callApi({ action: "run_episode", project, query });
}

export function getMemoryTrace(project) {
  return callApi({ action: "memory_trace", project });
}
