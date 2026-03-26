/**
 * Debug-mode logger (session 44899c). Dual: ingest + Metro console for physical devices.
 */
export function agentLog(payload: {
  hypothesisId: string;
  location: string;
  message: string;
  data?: Record<string, unknown>;
  runId?: string;
}): void {
  const body = {
    sessionId: "44899c",
    timestamp: Date.now(),
    ...payload,
  };
  // #region agent log
  fetch("http://127.0.0.1:7516/ingest/09556cc8-c029-4ebf-954c-1ce7fd3bdcc8", {
    method: "POST",
    headers: {
      "Content-Type": "application/json",
      "X-Debug-Session-Id": "44899c",
    },
    body: JSON.stringify(body),
  }).catch(() => {});
  if (__DEV__) {
    console.warn("[debug-44899c]", JSON.stringify(body));
  }
  // #endregion
}
