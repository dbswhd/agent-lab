/**
 * Agent Lab hybrid relay — Cloudflare Worker (예시)
 *
 * 로컬 PC가 꺼져 있을 때 agent-lab이 POST하는 이벤트를 받아 Telegram으로 push합니다.
 * 배포·Secrets 설정: docs/HYBRID-RELAY-WORKER.md
 */

const HANDLED_EVENTS = new Set([
  "inbox_pending",
  "merge_ready",
  "schedule_tick",
  "gate_blocked",
  "auto_merge_blocked",
  "test_ping",
]);

export default {
  async fetch(request, env) {
    if (request.method !== "POST") {
      return json({ ok: false, error: "POST only" }, 405);
    }

    const rawBody = await request.text();
    const secret = (env.RELAY_SECRET || "").trim();
    if (secret) {
      const sig = request.headers.get("X-Agent-Lab-Signature") || "";
      const ok = await verifySignature(secret, rawBody, sig);
      if (!ok) {
        return json({ ok: false, error: "invalid signature" }, 401);
      }
    }

    let envelope;
    try {
      envelope = JSON.parse(rawBody);
    } catch {
      return json({ ok: false, error: "invalid json" }, 400);
    }

    const event = String(envelope.event || "");
    if (!HANDLED_EVENTS.has(event)) {
      return json({ ok: true, skipped: true, reason: "unknown_event", event });
    }

    const text = formatMessage(event, envelope);
    const wake = await maybeWakePc(envelope, env);
    const results = await pushTelegram(text, env);
    const slack = await pushSlack(text, env);
    return json({ ok: results.every((r) => r.ok), event, wake, telegram: results, slack });
  },
};

function json(body, status = 200) {
  return new Response(JSON.stringify(body), {
    status,
    headers: { "Content-Type": "application/json" },
  });
}

async function verifySignature(secret, body, header) {
  const expected = header.trim();
  if (!expected.startsWith("sha256=")) {
    return false;
  }
  const digestHex = expected.slice("sha256=".length);
  const key = await crypto.subtle.importKey(
    "raw",
    new TextEncoder().encode(secret),
    { name: "HMAC", hash: "SHA-256" },
    false,
    ["sign"],
  );
  const sig = await crypto.subtle.sign("HMAC", key, new TextEncoder().encode(body));
  const actual = [...new Uint8Array(sig)].map((b) => b.toString(16).padStart(2, "0")).join("");
  return timingSafeEqual(actual, digestHex);
}

function timingSafeEqual(a, b) {
  if (a.length !== b.length) {
    return false;
  }
  let out = 0;
  for (let i = 0; i < a.length; i += 1) {
    out |= a.charCodeAt(i) ^ b.charCodeAt(i);
  }
  return out === 0;
}

function formatMessage(event, envelope) {
  const payload = envelope.payload || {};
  const sessionId = payload.session_id || "(no session)";
  const ts = envelope.ts || "";

  if (event === "test_ping") {
    return `[agent-lab] test ping\n${payload.message || "ok"}`;
  }

  if (event === "inbox_pending") {
    const item = payload.item || {};
    const kind = item.kind || "item";
    const prompt = item.prompt || item.summary || item.id || "";
    const itemId = item.id || "";
    return (
      `[${sessionId}] inbox ${kind}\n` +
      `${String(prompt).slice(0, 500)}\n\n` +
      (itemId ? `/resolve ${itemId} <answer>` : "")
    );
  }

  if (event === "merge_ready") {
    const execId = payload.execution_id || payload.pending_execution_id || "";
    return `[${sessionId}] merge ready\nexecution: ${execId}\nOpen Console or /approve merge`;
  }

  if (event === "schedule_tick") {
    const scheduleId = payload.schedule_id || "";
    return `[${sessionId}] schedule tick\n${scheduleId}`;
  }

  if (event === "gate_blocked") {
    const reason = payload.reason || payload.block_reason || "blocked";
    return `[${sessionId}] gate blocked\n${reason}`;
  }

  if (event === "auto_merge_blocked") {
    const execId = payload.execution_id || "";
    const reason = payload.reason || "auto_merge_not_eligible";
    return (
      `[${sessionId}] auto-merge blocked\n` +
      `execution: ${execId}\n` +
      `reason: ${String(reason).slice(0, 240)}\n` +
      `/approve merge`
    );
  }

  return `[${sessionId}] ${event}\n${ts}`;
}

async function pushTelegram(text, env) {
  const token = (env.TELEGRAM_BOT_TOKEN || "").trim();
  const chatIds = parseChatIds(env.TELEGRAM_CHAT_IDS || "");
  if (!token || chatIds.length === 0) {
    return [{ ok: false, error: "telegram_not_configured" }];
  }

  const results = [];
  for (const chatId of chatIds) {
    const resp = await fetch(`https://api.telegram.org/bot${token}/sendMessage`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        chat_id: chatId,
        text: text.slice(0, 4000),
        disable_web_page_preview: true,
      }),
    });
    const data = await resp.json().catch(() => ({}));
    results.push({ chat_id: chatId, ok: resp.ok && data.ok !== false, status: resp.status });
  }
  return results;
}

async function pushSlack(text, env) {
  const url = (env.SLACK_WEBHOOK_URL || "").trim();
  if (!url) {
    return [{ ok: false, error: "slack_not_configured" }];
  }
  const resp = await fetch(url, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ text: text.slice(0, 3000) }),
  });
  return [{ ok: resp.ok, status: resp.status }];
}

function parseChatIds(raw) {
  return String(raw)
    .split(",")
    .map((s) => s.trim())
    .filter(Boolean)
    .map((s) => (/^-?\d+$/.test(s) ? Number(s) : s));
}

/**
 * When PC daemon is offline, Agent Lab includes envelope.wake with tunnel URL.
 * Worker POSTs wake_url → local /api/hooks/mission-wake or scheduler tick.
 */
async function maybeWakePc(envelope, env) {
  const hint = envelope.wake;
  if (!hint || hint.attempt !== true) {
    return { ok: true, skipped: true, reason: "no_wake_hint" };
  }
  if (envelope.daemon_online === true) {
    return { ok: true, skipped: true, reason: "daemon_online" };
  }

  const url = String(hint.url || env.WAKE_URL || "").trim();
  if (!url) {
    return { ok: false, skipped: true, reason: "no_wake_url" };
  }

  const headers = {
    "Content-Type": "application/json",
    "User-Agent": "agent-lab-hybrid-wake/1",
  };
  const token = (env.WAKE_TOKEN || env.SCHEDULER_HOOK_TOKEN || "").trim();
  if (token) {
    headers["X-Agent-Lab-Scheduler-Token"] = token;
  } else {
    const secret = (env.WAKE_SECRET || env.RELAY_SECRET || "").trim();
    if (secret) {
      const body = "{}";
      headers["X-Agent-Lab-Signature"] = await hmacSha256Hex(secret, body);
    }
  }

  try {
    const resp = await fetch(url, { method: "POST", headers, body: "{}" });
    let parsed = null;
    const raw = await resp.text();
    if (raw.trim()) {
      try {
        parsed = JSON.parse(raw);
      } catch {
        parsed = null;
      }
    }
    return {
      ok: resp.ok,
      status: resp.status,
      url,
      event: hint.event || envelope.event,
      body: parsed,
    };
  } catch (err) {
    return { ok: false, error: String(err), url, event: hint.event || envelope.event };
  }
}

async function hmacSha256Hex(secret, body) {
  const key = await crypto.subtle.importKey(
    "raw",
    new TextEncoder().encode(secret),
    { name: "HMAC", hash: "SHA-256" },
    false,
    ["sign"],
  );
  const sig = await crypto.subtle.sign("HMAC", key, new TextEncoder().encode(body));
  const hex = [...new Uint8Array(sig)].map((b) => b.toString(16).padStart(2, "0")).join("");
  return `sha256=${hex}`;
}
