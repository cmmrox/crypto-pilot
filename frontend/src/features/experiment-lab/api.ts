import { ApiError, apiRequest } from "../../api/client";
import type { Study, StudyConfig, Strategy } from "./types";

const root = "/api/experiment-lab";

async function startIteration(
  id: string,
  mode: string,
  parameters: Record<string, string>,
  source?: string,
) {
  const storageKey = `cp-lab-pending-${id}`;
  const body = JSON.stringify({
    mode,
    parameters: mode === "MANUAL" ? parameters : {},
    source_iteration_id: source ?? null,
  });
  const saved = sessionStorage.getItem(storageKey);
  const command: { key: string; body: string } = saved
    ? JSON.parse(saved)
    : { key: crypto.randomUUID(), body };
  if (command.body !== body) {
    throw new Error(
      "The previous start is unconfirmed. Retry its unchanged inputs before starting a different run.",
    );
  }
  sessionStorage.setItem(storageKey, JSON.stringify(command));
  try {
    const result = await apiRequest(`${root}/studies/${id}/iterations`, {
      method: "POST",
      headers: { "Idempotency-Key": command.key },
      body: command.body,
    });
    sessionStorage.removeItem(storageKey);
    return result;
  } catch (error) {
    // A timeout/5xx can follow a committed command. Keep its key through reloads.
    if (error instanceof ApiError && error.status >= 400 && error.status < 500) {
      sessionStorage.removeItem(storageKey);
    }
    throw error;
  }
}

export const labApi = {
  strategies: () => apiRequest<Strategy[]>(`${root}/strategies`),
  studies: (beforeId?: string) =>
    apiRequest<Study[]>(`${root}/studies?limit=50${beforeId ? `&before_id=${beforeId}` : ""}`),
  study: (id: string, before?: number) =>
    apiRequest<Study>(`${root}/studies/${id}?limit=20${before ? `&before=${before}` : ""}`),
  create: (config: StudyConfig) =>
    apiRequest<Study>(`${root}/studies`, { method: "POST", body: JSON.stringify(config) }),
  run: startIteration,
  cancel: (id: string) => apiRequest(`${root}/iterations/${id}/cancel`, { method: "POST" }),
  retryReview: (id: string) =>
    apiRequest(`${root}/iterations/${id}/retry-review`, { method: "POST" }),
  candidate: (id: string) => apiRequest<unknown>(`${root}/iterations/${id}/candidate`),
  artifact: (id: string) =>
    apiRequest<{ equity: { dt: string; equity: string; kind?: string }[] }>(
      `${root}/iterations/${id}/artifact`,
    ),
  skill: (id: string) => apiRequest<{ markdown: string }>(`${root}/studies/${id}/skill`),
};
