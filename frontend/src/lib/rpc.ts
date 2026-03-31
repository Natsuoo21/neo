/**
 * JSON-RPC 2.0 client for Neo backend communication.
 */

import type { RpcResponse } from "@/types/rpc";

const DEFAULT_BASE_URL = "http://localhost:9721";
const RPC_TIMEOUT_MS = 30_000;

let _baseUrl = DEFAULT_BASE_URL;
let _nextId = 1;

/** Custom error class for RPC errors with code + data. */
export class RpcError extends Error {
  code: number;
  data?: unknown;

  constructor(message: string, code: number, data?: unknown) {
    super(message);
    this.name = "RpcError";
    this.code = code;
    this.data = data;
  }
}

/** Configure the backend URL. */
export function setBaseUrl(url: string) {
  _baseUrl = url.replace(/\/$/, "");
}

/** Get the current base URL. */
export function getBaseUrl(): string {
  return _baseUrl;
}

/**
 * Call a JSON-RPC method on the Neo backend.
 *
 * @throws RpcError if the RPC returns an error.
 * @throws Error if the network request fails or times out.
 */
export async function rpc<T = unknown>(
  method: string,
  params?: Record<string, unknown>,
): Promise<T> {
  const id = _nextId++;
  const body = JSON.stringify({
    jsonrpc: "2.0",
    method,
    params: params ?? {},
    id,
  });

  const response = await fetch(`${_baseUrl}/rpc`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body,
    signal: AbortSignal.timeout(RPC_TIMEOUT_MS),
  });

  if (!response.ok) {
    throw new Error(`HTTP ${response.status}: ${response.statusText}`);
  }

  const data: RpcResponse<T> = await response.json();

  if (data.error) {
    throw new RpcError(data.error.message, data.error.code, data.error.data);
  }

  return data.result as T;
}

/**
 * Connect to SSE stream for real-time events.
 * Returns a cleanup function to close the connection.
 */
export function connectStream(
  onEvent: (event: string, data: unknown) => void,
  onError?: (error: Event) => void,
): () => void {
  const source = new EventSource(`${_baseUrl}/stream`);

  source.addEventListener("ping", (e) => {
    try {
      onEvent("ping", JSON.parse(e.data));
    } catch {
      onEvent("ping", e.data);
    }
  });

  source.addEventListener("message", (e) => {
    try {
      onEvent("message", JSON.parse(e.data));
    } catch {
      onEvent("message", e.data);
    }
  });

  source.onerror = (e) => {
    onError?.(e);
  };

  return () => source.close();
}
