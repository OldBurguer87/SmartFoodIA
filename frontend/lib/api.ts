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
  unread_count: number;
  last_message_at: string;
  last_message: { sender_type: string; content: string; created_at: string } | null;
};

export type ConversationDetail = ConversationSummary & { messages: ConversationMessage[] };

export type StoreOperationModeValue =
  | "OLIVIA"
  | "HUMAN_ONLY";

export type StoreOperationMode = {
  configured_mode: StoreOperationModeValue;
  effective_mode: StoreOperationModeValue;
  server_forced_human: boolean;
  can_change: boolean;
};

export async function getStoreOperationMode(
  storeId: string,
): Promise<StoreOperationMode> {
  const response = await apiFetch(
    `${API_URL}/api/v1/operations/stores/${storeId}/operation-mode`,
    { cache: "no-store" },
  );

  const data = await response.json().catch(() => null);

  if (!response.ok) {
    throw new Error(
      data?.detail || "Não foi possível carregar o modo de atendimento.",
    );
  }

  return data as StoreOperationMode;
}

export async function updateStoreOperationMode(
  storeId: string,
  operationMode: StoreOperationModeValue,
): Promise<StoreOperationMode> {
  const response = await apiFetch(
    `${API_URL}/api/v1/operations/stores/${storeId}/operation-mode`,
    {
      method: "PUT",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ operation_mode: operationMode }),
    },
  );

  const data = await response.json().catch(() => null);

  if (!response.ok) {
    throw new Error(
      data?.detail || "Não foi possível alterar o modo de atendimento.",
    );
  }

  return data as StoreOperationMode;
}

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

export async function markConversationRead(
  conversationId: string,
): Promise<{ id: string; unread_count: number }> {
  const response = await apiFetch(
    `${API_URL}/api/v1/operations/conversations/${conversationId}/read`,
    { method: "POST" },
  );

  if (!response.ok) {
    throw new Error("Não foi possível marcar a conversa como lida.");
  }

  return response.json();
}


export async function getConversationMessageMediaBlob(
  conversationId: string,
  messageId: string,
): Promise<Blob> {
  const response = await apiFetch(
    `${API_URL}/api/v1/operations/conversations/${conversationId}/messages/${messageId}/media`,
    { cache: "no-store" },
  );

  if (!response.ok) {
    throw new Error(
      "Não foi possível carregar a mídia da conversa.",
    );
  }

  return response.blob();
}


async function postConversationAction(conversationId: string, action: "takeover" | "release" | "close", body: Record<string, unknown>): Promise<ConversationSummary> {
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

export function closeConversation(conversationId: string, assignedTo: string) {
  return postConversationAction(conversationId, "close", { assigned_to: assignedTo });
}

export async function sendHumanReply(conversationId: string, assignedTo: string, content: string) {
  const response = await apiFetch(`${API_URL}/api/v1/operations/conversations/${conversationId}/reply`, {
    method: "POST", headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ assigned_to: assignedTo, content }),
  });
  if (!response.ok) throw new Error((await response.text()) || "Não foi possível enviar a mensagem.");
  return response.json();
}


export type HumanMediaReplyResult = {
  message_id: string;
  outbound_id: string;
  status: string;
  content_type: string;
  filename: string;
  mime_type: string;
  file_size: number;
};

export async function sendHumanMedia(
  conversationId: string,
  assignedTo: string,
  file: File,
  caption = "",
): Promise<HumanMediaReplyResult> {
  const form = new FormData();

  form.append("file", file);
  form.append("assigned_to", assignedTo);
  form.append("caption", caption);

  const response = await apiFetch(
    `${API_URL}/api/v1/operations/conversations/${conversationId}/media`,
    {
      method: "POST",
      body: form,
    },
  );

  if (!response.ok) {
    throw new Error(
      await authError(
        response,
        "Não foi possível enviar o arquivo.",
      ),
    );
  }

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
  pix_confirmed: boolean;
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



export type CustomerConversationResult = {
  conversation_id: string;
  customer_id: string;
  status: string;
  external_conversation_id: string;
};

export async function openCustomerConversation(
  storeId: string,
  customerId: string,
  assignedTo: string,
): Promise<CustomerConversationResult> {
  const response = await apiFetch(
    `${API_URL}/api/v1/operations/stores/${storeId}/customers/${customerId}/conversation`,
    {
      method: "POST",
      headers: {
        "Content-Type": "application/json",
      },
      body: JSON.stringify({
        assigned_to: assignedTo,
      }),
    },
  );

  if (!response.ok) {
    throw new Error(
      await authError(
        response,
        "Não foi possível abrir a conversa do cliente.",
      ),
    );
  }

  return response.json() as Promise<CustomerConversationResult>;
}


export type HumanOrderServiceMode = "DELIVERY" | "TAKEOUT";
export type HumanOrderPaymentMethod =
  | "PIX"
  | "CREDIT"
  | "DEBIT"
  | "CASH";

export type HumanOrderModifierSelection = {
  external_code: string;
  quantity: number;
};

export type HumanOrderCartItem = {
  id: string;
  product_external_code: string;
  product_name: string;
  quantity: number;
  unit_price: number | string;
  observations: string | null;
  modifiers: Array<{
    id: string;
    external_code: string;
    name: string;
    quantity: number;
    unit_price: number | string;
    total: number | string;
  }>;
  total: number | string;
};

export type HumanOrderCart = {
  id: string;
  store_id: string;
  customer_id: string;
  status: string;
  service_mode: HumanOrderServiceMode;
  items: HumanOrderCartItem[];
  subtotal: number | string;
};


export type HumanOrderCatalogModifier = {
  id: string;
  external_code: string;
  name: string;
  description: string | null;
  price: number | string;
  min_quantity: number;
  max_quantity: number;
  default_quantity: number;
  display_order: number;
};

export type HumanOrderCatalogGroup = {
  id: string;
  name: string;
  description: string | null;
  min_select: number;
  max_select: number;
  allow_repeat: boolean;
  display_order: number;
  modifiers: HumanOrderCatalogModifier[];
};

export type HumanOrderCatalogProduct = {
  id: string;
  store_id: string;
  external_code: string;
  name: string;
  description: string | null;
  price: number | string;
  category: string | null;
  available_for_delivery: boolean;
  available_for_takeout: boolean;
  modifier_groups: HumanOrderCatalogGroup[];
};


export async function listHumanOrderProducts(
  storeId: string,
  serviceMode: HumanOrderServiceMode,
): Promise<HumanOrderCatalogProduct[]> {
  const params = new URLSearchParams({
    store_id: storeId,
  });

  if (serviceMode === "DELIVERY") {
    params.set("delivery", "true");
  } else {
    params.set("takeout", "true");
  }

  const response = await apiFetch(
    `${API_URL}/api/v1/products?${params}`,
    { cache: "no-store" },
  );

  if (!response.ok) {
    throw new Error(
      await authError(
        response,
        "Não foi possível carregar o cardápio.",
      ),
    );
  }

  return response.json();
}


export async function createHumanOrderCart(
  storeId: string,
  customerId: string,
  serviceMode: HumanOrderServiceMode,
): Promise<HumanOrderCart> {
  const response = await apiFetch(
    `${API_URL}/api/v1/carts`,
    {
      method: "POST",
      headers: {
        "Content-Type": "application/json",
      },
      body: JSON.stringify({
        store_id: storeId,
        customer_id: customerId,
        service_mode: serviceMode,
      }),
    },
  );

  if (!response.ok) {
    throw new Error(
      await authError(
        response,
        "Não foi possível iniciar o pedido.",
      ),
    );
  }

  return response.json();
}


export async function addHumanOrderItem(
  cartId: string,
  payload: {
    product_external_code: string;
    quantity: number;
    observations?: string | null;
    modifiers?: HumanOrderModifierSelection[];
  },
): Promise<HumanOrderCart> {
  const response = await apiFetch(
    `${API_URL}/api/v1/carts/${cartId}/items`,
    {
      method: "POST",
      headers: {
        "Content-Type": "application/json",
      },
      body: JSON.stringify(payload),
    },
  );

  if (!response.ok) {
    throw new Error(
      await authError(
        response,
        "Não foi possível adicionar o produto.",
      ),
    );
  }

  return response.json();
}


export async function updateHumanOrderItem(
  cartId: string,
  itemId: string,
  payload: {
    quantity: number;
    observations?: string | null;
  },
): Promise<HumanOrderCart> {
  const response = await apiFetch(
    `${API_URL}/api/v1/carts/${cartId}/items/${itemId}`,
    {
      method: "PATCH",
      headers: {
        "Content-Type": "application/json",
      },
      body: JSON.stringify(payload),
    },
  );

  if (!response.ok) {
    throw new Error(
      await authError(
        response,
        "Não foi possível alterar o item.",
      ),
    );
  }

  return response.json();
}

export async function removeHumanOrderItem(
  cartId: string,
  itemId: string,
): Promise<HumanOrderCart> {
  const response = await apiFetch(
    `${API_URL}/api/v1/carts/${cartId}/items/${itemId}`,
    {
      method: "DELETE",
    },
  );

  if (!response.ok) {
    throw new Error(
      await authError(
        response,
        "Não foi possível remover o item.",
      ),
    );
  }

  return response.json();
}


export async function clearHumanOrderCart(
  cartId: string,
): Promise<HumanOrderCart> {
  const response = await apiFetch(
    `${API_URL}/api/v1/carts/${cartId}/items`,
    {
      method: "DELETE",
    },
  );

  if (!response.ok) {
    throw new Error(
      await authError(
        response,
        "Não foi possível limpar o pedido.",
      ),
    );
  }

  return response.json();
}

export async function checkoutHumanOrder(
  cartId: string,
  payload: {
    address_id?: string | null;
    payment_method: HumanOrderPaymentMethod;
    change_for?: number | null;
    discount?: number;
  },
) {
  const response = await apiFetch(
    `${API_URL}/api/v1/orders/checkout/${cartId}`,
    {
      method: "POST",
      headers: {
        "Content-Type": "application/json",
      },
      body: JSON.stringify({
        address_id: payload.address_id ?? null,
        payment_method: payload.payment_method,
        change_for: payload.change_for ?? null,
        discount: payload.discount ?? 0,
      }),
    },
  );

  if (!response.ok) {
    throw new Error(
      await authError(
        response,
        "Não foi possível confirmar o pedido.",
      ),
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
  pix_confirmed: boolean;
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


export type PlatformAnalytics = {
  scope: "platform";
  period_hours: number;
  generated_at: string;
  summary: {
    companies_total: number;
    companies_active: number;
    companies_with_orders: number;
    stores_total: number;
    stores_active: number;
    stores_with_orders: number;
    orders_total: number;
    orders_valid: number;
    orders_cancelled: number;
    revenue: number;
    average_ticket: number;
  };
  ai_costs: {
    calls: number;
    unpriced_calls: number;
    input_tokens: number;
    cached_input_tokens: number;
    output_tokens: number;
    reasoning_tokens: number;
    total_tokens: number;
    conversations: number;
    estimated_cost_usd: number;
    olivia: {
      calls: number;
      estimated_cost_usd: number;
    };
    pix_analysis: {
      calls: number;
      estimated_cost_usd: number;
    };
    cost_per_conversation_usd: number;
    cost_per_order_usd: number;
  };
  service_modes: Array<{
    service_mode: string;
    orders: number;
    revenue: number;
  }>;
  payment_methods: Array<{
    payment_method: string;
  pix_confirmed: boolean;
    orders: number;
    revenue: number;
  }>;
  states: Array<{
    state: string;
    stores: number;
    orders: number;
    revenue: number;
  }>;
  cities: Array<{
    state: string;
    city: string;
    stores: number;
    orders: number;
    revenue: number;
  }>;
  top_products: Array<{
    name: string;
    stores: number;
    quantity: number;
    revenue: number;
  }>;
  top_modifiers: Array<{
    name: string;
    stores: number;
    quantity: number;
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


export async function getPlatformAnalytics(
  hours: number,
): Promise<PlatformAnalytics> {
  const response = await apiFetch(
    `${API_URL}/api/v1/operations/platform/analytics?hours=${hours}`,
    {
      cache: "no-store",
    },
  );

  if (!response.ok) {
    throw new Error(
      await authError(
        response,
        "Não foi possível carregar o Analytics global.",
      ),
    );
  }

  return response.json() as Promise<PlatformAnalytics>;
}

export type HumanPixConfirmationResult = {
  receipt_id: string;
  order_id: string;
  display_id: string;
  status: string;
  message_id: string;
  already_confirmed: boolean;
};

export async function confirmHumanPix(
  conversationId: string,
  orderId: string,
  messageId: string,
  assignedTo: string,
): Promise<HumanPixConfirmationResult> {
  const form = new FormData();
  form.append("message_id", messageId);
  form.append("assigned_to", assignedTo);

  const url =
    `${API_URL}/api/v1/operations/conversations/${conversationId}` +
    `/orders/${orderId}/pix/confirm`;

  const response = await apiFetch(url, {
    method: "POST",
    body: form,
  });

  if (!response.ok) {
    throw new Error(
      await authError(
        response,
        "Não foi possível confirmar o PIX.",
      ),
    );
  }

  return response.json();
}


// HUMAN_ORDER_MANAGEMENT_HOTFIX
export type HumanCustomerAddressPayload = {
  label: string;
  street: string;
  number: string;
  neighborhood: string;
  city: string;
  state: string;
  postal_code?: string | null;
  complement?: string | null;
  reference?: string | null;
  is_default: boolean;
};

export async function createHumanCustomerAddress(
  conversationId: string,
  payload: HumanCustomerAddressPayload,
): Promise<CustomerAddress> {
  const response = await apiFetch(
    `${API_URL}/api/v1/operations/conversations/${conversationId}/customer/addresses`,
    {
      method: "POST",
      headers: {
        "Content-Type": "application/json",
      },
      body: JSON.stringify(payload),
    },
  );

  if (!response.ok) {
    throw new Error(
      await authError(
        response,
        "Não foi possível cadastrar o endereço.",
      ),
    );
  }

  return response.json();
}

export async function updateHumanCustomerAddress(
  conversationId: string,
  addressId: string,
  payload: HumanCustomerAddressPayload,
): Promise<CustomerAddress> {
  const response = await apiFetch(
    `${API_URL}/api/v1/operations/conversations/${conversationId}/customer/addresses/${addressId}`,
    {
      method: "PATCH",
      headers: {
        "Content-Type": "application/json",
      },
      body: JSON.stringify(payload),
    },
  );

  if (!response.ok) {
    throw new Error(
      await authError(
        response,
        "Não foi possível editar o endereço.",
      ),
    );
  }

  return response.json();
}

export async function cancelHumanPendingOrder(
  conversationId: string,
  orderId: string,
): Promise<{
  id: string;
  display_id: string;
  status: string;
}> {
  const response = await apiFetch(
    `${API_URL}/api/v1/operations/conversations/${conversationId}/orders/${orderId}/cancel`,
    {
      method: "POST",
    },
  );

  if (!response.ok) {
    throw new Error(
      await authError(
        response,
        "Não foi possível cancelar o pedido.",
      ),
    );
  }

  return response.json();
}
