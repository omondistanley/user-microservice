/**
 * FastAPI often returns `detail` as a string, or as an array of { loc, msg } objects.
 * Using String(detail) on objects yields "[object Object]".
 */
export function formatApiDetail(detail: unknown, fallback: string): string {
  if (detail === undefined || detail === null) return fallback;
  if (typeof detail === "string") {
    const t = detail.trim();
    return t || fallback;
  }
  if (Array.isArray(detail)) {
    const parts = detail.map((e) => {
      if (e && typeof e === "object") {
        const o = e as { loc?: unknown[]; msg?: string; message?: string };
        const loc = Array.isArray(o.loc) ? o.loc.slice(1).join(".") : "";
        const msg = o.msg ?? o.message ?? "";
        return loc ? `${loc}: ${msg}` : String(msg || JSON.stringify(e));
      }
      return JSON.stringify(e);
    });
    const s = parts.join("; ").trim();
    return s || fallback;
  }
  if (typeof detail === "object") {
    const o = detail as { msg?: string };
    if (typeof o.msg === "string" && o.msg.trim()) return o.msg.trim();
    try {
      return JSON.stringify(detail);
    } catch {
      return fallback;
    }
  }
  return String(detail);
}
