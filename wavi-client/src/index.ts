/**
 * wavi-client — typed HTTP client for the wavi WhatsApp automation server.
 *
 * Quickstart:
 *   const wavi = new WaviClient({ baseUrl: "http://127.0.0.1:8900" });
 *   const { bubbles } = await wavi.get({ contact: "Juan Pérez" });
 *   await wavi.send({ contact: "Juan Pérez", message: "Hola!" });
 */

// ── Types ─────────────────────────────────────────────────────────────────────

export interface Bubble {
  id: number;
  screen_id: number;
  sender: "me" | "other";
  msg_type: "text" | "audio" | "file" | "media";
  timestamp: string | null;
  text: string;
  bbox: { x: number; y: number; w: number; h: number };
  dom_id: string | null;
  transcript?: string;
  audio_path?: string;
}

export interface GetOptions {
  session?: string;
  contact: string;
  assets_dir?: string;
  max_iter?: number;
  from_date?: string;
  newest?: boolean;
  grow?: boolean;
}

export interface GetResult {
  contact: string;
  session: string;
  count: number;
  bubbles: Bubble[];
}

export interface SendOptions {
  session?: string;
  contact: string;
  message: string;
}

export interface SendResult {
  ok: boolean;
  contact: string;
  input_coords: { x: number; y: number; found: boolean; selector: string };
}

export interface CheckUpdatesOptions {
  session?: string;
  reset?: boolean;
}

export interface InboundChat {
  name: string;
  last_message: string;
  timestamp: string;
}

export interface CheckUpdatesResult {
  status: "no_updates" | "updates" | "first_run";
  new_inbound: InboundChat[];
  checked_at: string;
}

export interface StatusResult {
  session: string;
  daemon: boolean;
  authenticated: boolean;
  error?: string;
}

export interface QueueResult {
  session: string;
  status: "idle" | "busy";
  operation?: string;
  contact?: string;
  pid?: number;
  started_at?: string;
}

export interface WaviClientOptions {
  /** Base URL of the wavi server. Default: http://127.0.0.1:8900 */
  baseUrl?: string;
  /** Default session name. Default: "default" */
  defaultSession?: string;
  /** Fetch timeout in milliseconds. Default: 120_000 (2 min) */
  timeoutMs?: number;
}

// ── Client ────────────────────────────────────────────────────────────────────

export class WaviClient {
  private readonly baseUrl: string;
  private readonly defaultSession: string;
  private readonly timeoutMs: number;

  constructor(opts: WaviClientOptions = {}) {
    this.baseUrl = (opts.baseUrl ?? "http://127.0.0.1:8900").replace(/\/$/, "");
    this.defaultSession = opts.defaultSession ?? "default";
    this.timeoutMs = opts.timeoutMs ?? 120_000;
  }

  private async _fetch<T>(path: string, init?: RequestInit): Promise<T> {
    const controller = new AbortController();
    const timer = setTimeout(() => controller.abort(), this.timeoutMs);
    try {
      const res = await fetch(`${this.baseUrl}${path}`, {
        ...init,
        signal: controller.signal,
      });
      if (!res.ok) {
        const body = await res.text();
        let detail: string;
        try {
          detail = JSON.parse(body).detail ?? body;
        } catch {
          detail = body;
        }
        throw new WaviError(res.status, detail);
      }
      return res.json() as Promise<T>;
    } finally {
      clearTimeout(timer);
    }
  }

  private _post<T>(path: string, body: unknown): Promise<T> {
    return this._fetch<T>(path, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(body),
    });
  }

  /** Check server liveness. */
  health(): Promise<{ status: string; version: string }> {
    return this._fetch("/health");
  }

  /** Get daemon + auth status for a session. */
  status(session?: string): Promise<StatusResult> {
    return this._fetch(`/status/${session ?? this.defaultSession}`);
  }

  /** Get queue status (idle vs. busy) for a session. */
  queue(session?: string): Promise<QueueResult> {
    return this._fetch(`/queue/${session ?? this.defaultSession}`);
  }

  /**
   * Capture full message history from a contact's chat.
   * Equivalent to `wavi get <session> <contact>`.
   */
  get(opts: GetOptions): Promise<GetResult> {
    return this._post<GetResult>("/get", {
      session: opts.session ?? this.defaultSession,
      ...opts,
    });
  }

  /**
   * Send a message to a contact.
   * Equivalent to `wavi send <session> <contact> <message>`.
   */
  send(opts: SendOptions): Promise<SendResult> {
    return this._post<SendResult>("/send", {
      session: opts.session ?? this.defaultSession,
      ...opts,
    });
  }

  /**
   * Check sidebar for new inbound messages.
   * Equivalent to `wavi check-updates`.
   */
  checkUpdates(opts: CheckUpdatesOptions = {}): Promise<CheckUpdatesResult> {
    return this._post<CheckUpdatesResult>("/check-updates", {
      session: opts.session ?? this.defaultSession,
      reset: opts.reset ?? false,
    });
  }

  /**
   * List all contacts from the New Chat panel.
   * Equivalent to `wavi list-contacts`.
   */
  listContacts(session?: string): Promise<{ contacts: Array<{ name: string; subtitle?: string }> }> {
    return this._post("/list-contacts", { session: session ?? this.defaultSession });
  }
}

// ── Error ─────────────────────────────────────────────────────────────────────

export class WaviError extends Error {
  constructor(
    public readonly status: number,
    public readonly detail: string,
  ) {
    super(`wavi API error ${status}: ${detail}`);
    this.name = "WaviError";
  }
}

export default WaviClient;
