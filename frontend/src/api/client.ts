/** Minimal typed API client. Expands into a full REST + WebSocket layer in later stages. */

export interface Health {
  status: string;
  version: string;
  database: string;
}

const BASE = import.meta.env.VITE_API_BASE ?? "";

export async function getHealth(): Promise<Health> {
  const resp = await fetch(`${BASE}/health`);
  if (!resp.ok) throw new Error(`health check failed: ${resp.status}`);
  return (await resp.json()) as Health;
}
