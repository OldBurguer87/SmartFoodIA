export type AlertItem = {
  severity: "CRITICAL" | "WARNING" | "INFO";
  code: string;
  message: string;
};

export type OperationalOverview = {
  store_id: string;
  period_hours: number;
  generated_at: string;
  conversations: {
    total: number;
    open: number;
    human: number;
    closed: number;
  };
  tickets: {
    total: number;
    open: number;
    in_progress: number;
    resolved: number;
    urgent_active: number;
  };
  orders: {
    total: number;
    revenue: number;
    by_status: Record<string, number>;
  };
  ai: {
    events: number;
    errors: number;
    average_duration_ms: number;
  };
  queue: {
    events_received: number;
    events_retry: number;
    events_dead: number;
    events_processed: number;
    outbound_pending: number;
    outbound_retry: number;
    outbound_dead: number;
    outbound_sent: number;
  };
  knowledge: {
    open_gaps: number;
  };
  alerts: AlertItem[];
};

const API_URL =
  process.env.NEXT_PUBLIC_API_URL?.replace(/\/$/, "") ??
  "http://localhost:8000";

export async function getOperationalOverview(
  storeId: string,
  hours: number,
): Promise<OperationalOverview> {
  const response = await fetch(
    `${API_URL}/api/v1/operations/stores/${storeId}/overview?hours=${hours}`,
    { cache: "no-store" },
  );

  if (!response.ok) {
    const body = await response.text();
    throw new Error(
      body || `Não foi possível carregar o painel (${response.status}).`,
    );
  }

  return response.json() as Promise<OperationalOverview>;
}


export type ConversationMessage = {
  id: string;
  direction: "INBOUND" | "OUTBOUND";
  sender_type: "CUSTOMER" | "OLIVIA" | "HUMAN" | "SYSTEM";
  content_type: string;
  content: string;
  metadata_json: Record<string, unknown> | null;
  created_at: string;
};

export type ConversationSummary = {
  id: string;
  store_id: string;
  customer_id: string | null;
  channel: string;
  external_conversation_id: string | null;
  status: "OPEN" | "HUMAN" | "CLOSED";
  last_message_at: string;
  last_message: { sender_type: string; content: string; created_at: string } | null;
};

export type ConversationDetail = ConversationSummary & { messages: ConversationMessage[] };

export async function listConversations(storeId: string, status?: string): Promise<ConversationSummary[]> {
  const params = status ? `?status=${encodeURIComponent(status)}` : "";
  const response = await fetch(`${API_URL}/api/v1/operations/stores/${storeId}/conversations${params}`, { cache: "no-store" });
  if (!response.ok) throw new Error("Não foi possível carregar as conversas.");
  return response.json();
}

export async function getConversation(conversationId: string): Promise<ConversationDetail> {
  const response = await fetch(`${API_URL}/api/v1/operations/conversations/${conversationId}`, { cache: "no-store" });
  if (!response.ok) throw new Error("Não foi possível carregar a conversa.");
  return response.json();
}

async function postConversationAction(conversationId: string, action: "takeover" | "release", body: Record<string, unknown>): Promise<ConversationSummary> {
  const response = await fetch(`${API_URL}/api/v1/operations/conversations/${conversationId}/${action}`, {
    method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(body),
  });
  if (!response.ok) throw new Error((await response.text()) || "Não foi possível alterar o atendimento.");
  return response.json();
}

export function takeOverConversation(conversationId: string, assignedTo: string) {
  return postConversationAction(conversationId, "takeover", { assigned_to: assignedTo });
}

export function releaseConversation(conversationId: string, assignedTo: string) {
  return postConversationAction(conversationId, "release", { assigned_to: assignedTo });
}

export async function sendHumanReply(conversationId: string, assignedTo: string, content: string) {
  const response = await fetch(`${API_URL}/api/v1/operations/conversations/${conversationId}/reply`, {
    method: "POST", headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ assigned_to: assignedTo, content }),
  });
  if (!response.ok) throw new Error((await response.text()) || "Não foi possível enviar a mensagem.");
  return response.json();
}
