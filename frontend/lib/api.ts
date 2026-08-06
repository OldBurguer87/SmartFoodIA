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
