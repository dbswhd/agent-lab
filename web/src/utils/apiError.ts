/** Parse FastAPI-style error bodies from failed `fetch` responses. */
export function parseApiErrorDetail(text: string): string {
  const raw = text.trim();
  if (!raw) return "요청 실패";
  try {
    const body = JSON.parse(raw) as {
      detail?: string | { message?: string; reason?: string };
    };
    const detail = body.detail;
    if (typeof detail === "string") return detail;
    if (detail && typeof detail === "object") {
      if (typeof detail.message === "string") return detail.message;
      if (typeof detail.reason === "string") return detail.reason;
    }
  } catch {
    /* plain text */
  }
  return raw;
}
