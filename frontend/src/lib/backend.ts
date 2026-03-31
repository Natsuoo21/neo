/**
 * Backend health check and lifecycle management.
 */

import { getBaseUrl } from "./rpc";

/** Check if the Neo backend server is reachable. */
export async function checkBackendHealth(): Promise<boolean> {
  try {
    const res = await fetch(`${getBaseUrl()}/health`, {
      signal: AbortSignal.timeout(3000),
    });
    if (!res.ok) return false;
    const data = await res.json();
    return data.status === "ok";
  } catch {
    return false;
  }
}

/**
 * Poll until backend is healthy (or timeout).
 * Useful during startup when waiting for sidecar.
 */
export async function waitForBackend(
  timeoutMs = 15000,
  intervalMs = 500,
): Promise<boolean> {
  const deadline = Date.now() + timeoutMs;
  while (Date.now() < deadline) {
    if (await checkBackendHealth()) return true;
    await new Promise((r) => setTimeout(r, intervalMs));
  }
  return false;
}

/** Detect if running in development mode. */
export function isDevMode(): boolean {
  return import.meta.env.DEV;
}
