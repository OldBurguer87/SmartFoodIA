import { apiFetch } from "@/lib/api";

export type CommercialRules = {
  manual_paused: boolean;
  pause_reason: string | null;
  delivery_enabled: boolean;
  takeout_enabled: boolean;
  minimum_delivery_subtotal: number;
  delivery_fee_mode: "FIXED" | "ZONE";
  fixed_delivery_fee: number;
  accepts_pix: boolean;
  pix_receiver_name: string | null;
  pix_receiver_document: string | null;
  pix_key: string | null;
  pix_receiver_institution: string | null;
  pix_auto_verify_enabled: boolean;
  pix_receipt_max_age_minutes: number;
  pix_amount_tolerance: number;

  accepts_credit: boolean;
  accepts_debit: boolean;
  accepts_cash: boolean;
  allow_change: boolean;

  average_prep_minutes: number | null;

  allow_scheduled_orders: boolean;
  allow_scheduled_when_closed: boolean;
  scheduled_min_notice_minutes: number | null;
  scheduled_max_days_ahead: number | null;

  general_notes: string | null;
};

export type BusinessHour = {
  weekday: number;
  closed: boolean;
  open_time: string | null;
  close_time: string | null;
  delivery_until: string | null;
  takeout_until: string | null;
};

export type DeliveryZone = {
  id: string;
  name: string;
  fee: number;
  delivery_allowed: boolean;
  active: boolean;
};

export type CommercialResponse = {
  store_id: string;
  current_status: {
    open: boolean;
    reason: string;
    local_time: string;
  };
  rules: CommercialRules;
  hours: BusinessHour[];
  zones: DeliveryZone[];
};

const API =
  process.env.NEXT_PUBLIC_API_URL?.replace(/\/$/, "") ??
  "http://localhost:8000";

async function result(response: Response): Promise<CommercialResponse> {
  if (!response.ok) {
    throw new Error(
      (await response.text()) || `Erro HTTP ${response.status}`,
    );
  }
  return response.json();
}

export function getCommercialRules(storeId: string) {
  return apiFetch(
    `${API}/api/v1/operations/stores/${storeId}/commercial-rules`,
    { cache: "no-store" },
  ).then(result);
}

export function saveCommercialRules(
  storeId: string,
  rules: CommercialRules,
) {
  return apiFetch(
    `${API}/api/v1/operations/stores/${storeId}/commercial-rules`,
    {
      method: "PUT",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(rules),
    },
  ).then(result);
}

export function saveBusinessHour(
  storeId: string,
  weekday: number,
  hour: Omit<BusinessHour, "weekday">,
) {
  return apiFetch(
    `${API}/api/v1/operations/stores/${storeId}/commercial-rules/hours/${weekday}`,
    {
      method: "PUT",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(hour),
    },
  ).then(result);
}

export function saveDeliveryZone(
  storeId: string,
  payload: {
    name: string;
    fee: number;
    delivery_allowed: boolean;
    active: boolean;
  },
) {
  return apiFetch(
    `${API}/api/v1/operations/stores/${storeId}/commercial-rules/zones`,
    {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(payload),
    },
  ).then(result);
}

export function removeDeliveryZone(
  storeId: string,
  zoneId: string,
) {
  return apiFetch(
    `${API}/api/v1/operations/stores/${storeId}/commercial-rules/zones/${zoneId}`,
    { method: "DELETE" },
  ).then(result);
}
