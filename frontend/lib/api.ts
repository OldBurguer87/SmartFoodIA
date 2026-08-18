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
    waiting_human: number;
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

export type ServiceStatus = "OPERATIONAL" | "WARNING" | "ATTENTION";

export type ClientIntegrationSummary = {
  provider: string;
  merchant_name: string;
  status: ServiceStatus;
  detail: string;
  last_activity_at: string;
};

export type ClientSummary = {
  store_id: string;
  name: string;
  slug: string;
  city: string;
  state: string;
  status: ServiceStatus;
  orders: number;
  revenue: number;
  active_conversations: number;
  urgent_tickets: number;
  integrations: ClientIntegrationSummary[];
};

export type PlatformOverview = {
  generated_at: string;
  period_hours: number;
  smartfoodia: {
    status: ServiceStatus;
    api: ServiceStatus;
    openai: ServiceStatus;
    whatsapp: ServiceStatus;
    queue: ServiceStatus;
    messages_sent: number;
    active_alerts: string[];
  };
  summary: {
    clients_total: number;
    clients_attention: number;
    orders_total: number;
    revenue_total: number;
    active_conversations: number;
  };
  clients: ClientSummary[];
};


const API_URL =
  process.env.NEXT_PUBLIC_API_URL?.replace(/\/$/, "") ??
  "http://localhost:8000";

export async function apiFetch(
  input: RequestInfo | URL,
  init: RequestInit = {},
) {
  return fetch(input, {
    ...init,
    credentials: "include",
  });
}

export type AuthStore = {
  id: string;
  name: string;
  slug: string;
  city: string;
  state: string;
  timezone: string;
};

export type AuthCompany = {
  id: string;
  name: string;
  role: string;
  stores: AuthStore[];
};

export type AuthUser = {
  id: string;
  name: string;
  email: string;
  is_platform_admin: boolean;
};

export type AuthState = {
  authenticated: true;
  user: AuthUser;
  companies: AuthCompany[];
};

async function authError(
  response: Response,
  fallback: string,
): Promise<string> {
  try {
    const payload = await response.json();
    if (
      payload &&
      typeof payload.detail === "string"
    ) {
      return payload.detail;
    }
  } catch {
    // Resposta sem JSON.
  }

  return fallback;
}

export async function getCurrentAuth(): Promise<AuthState | null> {
  const response = await apiFetch(
    `${API_URL}/api/v1/auth/me`,
    { cache: "no-store" },
  );

  if (response.status === 401) {
    return null;
  }

  if (!response.ok) {
    throw new Error(
      await authError(
        response,
        "Não foi possível verificar sua sessão.",
      ),
    );
  }

  return response.json() as Promise<AuthState>;
}

export async function login(
  email: string,
  password: string,
): Promise<AuthState> {
  const response = await apiFetch(
    `${API_URL}/api/v1/auth/login`,
    {
      method: "POST",
      headers: {
        "Content-Type": "application/json",
      },
      body: JSON.stringify({
        email,
        password,
      }),
    },
  );

  if (!response.ok) {
    throw new Error(
      await authError(
        response,
        "Não foi possível entrar.",
      ),
    );
  }

  return response.json() as Promise<AuthState>;
}

export async function logout(): Promise<void> {
  const response = await apiFetch(
    `${API_URL}/api/v1/auth/logout`,
    {
      method: "POST",
    },
  );

  if (!response.ok) {
    throw new Error(
      "Não foi possível encerrar a sessão.",
    );
  }
}

export async function getPlatformOverview(hours: number): Promise<PlatformOverview> {
  const response = await apiFetch(
    `${API_URL}/api/v1/operations/overview?hours=${hours}`,
    { cache: "no-store" },
  );
  if (!response.ok) {
    const body = await response.text();
    throw new Error(body || `Não foi possível carregar a visão geral (${response.status}).`);
  }
  return response.json() as Promise<PlatformOverview>;
}

export async function getOperationalOverview(
  storeId: string,
  hours: number,
): Promise<OperationalOverview> {
  const response = await apiFetch(
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
  status: "OPEN" | "WAITING_HUMAN" | "HUMAN" | "CLOSED";
  last_message_at: string;
  last_message: { sender_type: string; content: string; created_at: string } | null;
};

export type ConversationDetail = ConversationSummary & { messages: ConversationMessage[] };

export async function listConversations(storeId: string, status?: string): Promise<ConversationSummary[]> {
  const params = status ? `?status=${encodeURIComponent(status)}` : "";
  const response = await apiFetch(`${API_URL}/api/v1/operations/stores/${storeId}/conversations${params}`, { cache: "no-store" });
  if (!response.ok) throw new Error("Não foi possível carregar as conversas.");
  return response.json();
}

export async function getConversation(conversationId: string): Promise<ConversationDetail> {
  const response = await apiFetch(`${API_URL}/api/v1/operations/conversations/${conversationId}`, { cache: "no-store" });
  if (!response.ok) throw new Error("Não foi possível carregar a conversa.");
  return response.json();
}

async function postConversationAction(conversationId: string, action: "takeover" | "release", body: Record<string, unknown>): Promise<ConversationSummary> {
  const response = await apiFetch(`${API_URL}/api/v1/operations/conversations/${conversationId}/${action}`, {
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
  const response = await apiFetch(`${API_URL}/api/v1/operations/conversations/${conversationId}/reply`, {
    method: "POST", headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ assigned_to: assignedTo, content }),
  });
  if (!response.ok) throw new Error((await response.text()) || "Não foi possível enviar a mensagem.");
  return response.json();
}


export type CustomerSummary = {
  id: string;
  store_id: string;
  name: string;
  phone: string;
  active: boolean;
  addresses_count: number;
  created_at: string;
  updated_at: string;
};

export type CustomerAddress = {
  id: string;
  label: string;
  street: string;
  number: string;
  neighborhood: string;
  city: string;
  state: string;
  postal_code: string | null;
  complement: string | null;
  reference: string | null;
  is_default: boolean;
  active: boolean;
};

export type CustomerOrder = {
  id: string;
  display_id: string;
  status: string;
  service_mode: string;
  payment_method: string;
  total: number | string;
  scheduled_for: string | null;
  created_at: string;
};

export type CustomerDetail = CustomerSummary & {
  addresses: CustomerAddress[];
  orders: CustomerOrder[];
};

export type CustomerListResponse = {
  store_id: string;
  total: number;
  limit: number;
  offset: number;
  customers: CustomerSummary[];
};

export async function listCustomers(
  storeId: string,
  search = "",
): Promise<CustomerListResponse> {
  const params = new URLSearchParams({
    limit: "100",
    offset: "0",
  });

  if (search.trim()) {
    params.set("search", search.trim());
  }

  const response = await apiFetch(
    `${API_URL}/api/v1/operations/stores/${storeId}/customers?${params}`,
    { cache: "no-store" },
  );

  if (!response.ok) {
    throw new Error(
      "Não foi possível carregar a carteira de clientes.",
    );
  }

  return response.json();
}

export async function getCustomerDetail(
  storeId: string,
  customerId: string,
): Promise<CustomerDetail> {
  const response = await apiFetch(
    `${API_URL}/api/v1/operations/stores/${storeId}/customers/${customerId}`,
    { cache: "no-store" },
  );

  if (!response.ok) {
    throw new Error(
      "Não foi possível carregar a ficha do cliente.",
    );
  }

  return response.json();
}


export type StoreAnalytics = {
  store_id: string;
  period_hours: number;
  timezone: string;
  generated_at: string;
  summary: {
    orders_total: number;
    orders_valid: number;
    orders_cancelled: number;
    revenue: number;
    average_ticket: number;
    unique_customers: number;
    new_customers: number;
    returning_customers: number;
  };
  service_modes: Array<{
    service_mode: string;
    orders: number;
    revenue: number;
  }>;
  payment_methods: Array<{
    payment_method: string;
    orders: number;
    revenue: number;
  }>;
  top_products: Array<{
    product_id: string;
    external_code: string | null;
    name: string;
    quantity: number;
    revenue: number;
  }>;
  top_modifiers: Array<{
    modifier_id: string;
    external_code: string | null;
    name: string;
    quantity: number;
    revenue: number;
  }>;
  top_neighborhoods: Array<{
    neighborhood: string;
    orders: number;
    revenue: number;
  }>;
  orders_by_weekday: Array<{
    weekday: number;
    label: string;
    orders: number;
    revenue: number;
  }>;
  orders_by_hour: Array<{
    hour: number;
    orders: number;
    revenue: number;
  }>;
};


export async function getStoreAnalytics(
  storeId: string,
  hours: number,
): Promise<StoreAnalytics> {
  const response = await apiFetch(
    `${API_URL}/api/v1/operations/stores/${storeId}/analytics?hours=${hours}`,
    {
      cache: "no-store",
    },
  );

  if (!response.ok) {
    throw new Error(
      await authError(
        response,
        "Não foi possível carregar o Analytics da loja.",
      ),
    );
  }

  return response.json() as Promise<StoreAnalytics>;
}
