"use client";

import { useEffect, useState } from "react";
import {
  ClientSummary,
  getPlatformOverview,
  PlatformOverview,
  ServiceStatus,
} from "@/lib/api";
import { LogoMark, RefreshIcon } from "@/components/icons";

const currency = new Intl.NumberFormat("pt-BR", {
  style: "currency",
  currency: "BRL",
});
const number = new Intl.NumberFormat("pt-BR");

export function PlatformDashboard() {
  const [hours, setHours] = useState(24);
  const [overview, setOverview] = useState<PlatformOverview | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  async function load() {
    setLoading(true);
    setError(null);
    try {
      setOverview(await getPlatformOverview(hours));
    } catch (requestError) {
      setError(
        requestError instanceof Error
          ? requestError.message
          : "Não foi possível carregar o painel.",
      );
    } finally {
      setLoading(false);
    }
  }

  useEffect(() => {
    void load();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [hours]);

  return (
    <div className="shell">
      <aside className="sidebar">
        <div className="brand">
          <LogoMark />
          <div>
            <strong>SmartFoodIA</strong>
            <span>Central operacional</span>
          </div>
        </div>

        <nav aria-label="Navegação principal">
          <a className="navItem active" href="#plataforma">Visão geral</a>
          <a className="navItem" href="#clientes">Clientes</a>
          <a className="navItem" href="#saude">Saúde da plataforma</a>
        </nav>

        <div className="sidebarFoot">
          <div className="statusDot" />
          <div>
            <strong>SmartFoodIA</strong>
            <span>Monitoramento central</span>
          </div>
        </div>
      </aside>

      <main className="main">
        <header className="topbar" id="plataforma">
          <div>
            <p className="eyebrow">SMARTFOODIA</p>
            <h1>Central de operações</h1>
            <p className="subtitle">
              Saúde da plataforma e operação de todos os clientes.
            </p>
          </div>
          <div style={{ display: "flex", gap: 10, alignItems: "center" }}>
            <select
              value={hours}
              onChange={(event) => setHours(Number(event.target.value))}
              aria-label="Período do painel"
              style={{ minHeight: 44, borderRadius: 10, padding: "0 12px" }}
            >
              <option value={24}>Últimas 24 horas</option>
              <option value={168}>Últimos 7 dias</option>
              <option value={720}>Últimos 30 dias</option>
            </select>
            <button className="refreshButton" onClick={() => void load()} disabled={loading}>
              <RefreshIcon />
              {loading ? "Atualizando..." : "Atualizar"}
            </button>
          </div>
        </header>

        {error && (
          <section className="errorBox">
            <strong>Não foi possível carregar a central.</strong>
            <span>{error}</span>
          </section>
        )}

        {overview && (
          <>
            <section className="metricsGrid">
              <Metric label="Clientes" value={overview.summary.clients_total} detail="Ativos na plataforma" />
              <Metric
                label="Clientes com atenção"
                value={overview.summary.clients_attention}
                detail="Integração ou operação"
                critical={overview.summary.clients_attention > 0}
              />
              <Metric label="Pedidos" value={overview.summary.orders_total} detail={`No período de ${overview.period_hours}h`} />
              <Metric label="Receita total" value={currency.format(overview.summary.revenue_total)} detail="Somatório dos clientes" />
            </section>

            <section className="panel wide" id="saude" style={{ marginBottom: 20 }}>
              <header className="panelHeader">
                <div>
                  <h2>SmartFoodIA</h2>
                  <p>Saúde atual da plataforma</p>
                </div>
                <StatusBadge status={overview.smartfoodia.status} />
              </header>
              <div className="healthGrid">
                <ServiceHealth label="API / VPS" status={overview.smartfoodia.api} />
                <ServiceHealth label="OpenAI" status={overview.smartfoodia.openai} />
                <ServiceHealth label="WhatsApp / Meta" status={overview.smartfoodia.whatsapp} />
                <ServiceHealth label="Fila" status={overview.smartfoodia.queue} />
              </div>
              <p className="muted" style={{ marginTop: 14 }}>
                {number.format(overview.smartfoodia.messages_sent)} mensagens enviadas no período.
              </p>
            </section>

            <section id="clientes">
              <header className="panelHeader" style={{ marginBottom: 12 }}>
                <div>
                  <h2>Clientes</h2>
                  <p>Cada operação é monitorada separadamente.</p>
                </div>
              </header>
              <div className="dashboardGrid">
                {overview.clients.map((client) => (
                  <ClientCard key={client.store_id} client={client} />
                ))}
              </div>
            </section>

            <footer className="footer">
              Atualizado em {new Date(overview.generated_at).toLocaleString("pt-BR")}
            </footer>
          </>
        )}
      </main>
    </div>
  );
}

function ClientCard({ client }: { client: ClientSummary }) {
  return (
    <article className="panel wide">
      <header className="panelHeader">
        <div>
          <p className="eyebrow">CLIENTE</p>
          <h2>{client.name}</h2>
          <p>{client.city} - {client.state}</p>
        </div>
        <StatusBadge status={client.status} />
      </header>

      <div className="miniGrid">
        <Mini label="Pedidos" value={number.format(client.orders)} />
        <Mini label="Receita" value={currency.format(client.revenue)} />
        <Mini label="Conversas ativas" value={number.format(client.active_conversations)} />
        <Mini label="Tickets urgentes" value={number.format(client.urgent_tickets)} critical={client.urgent_tickets > 0} />
      </div>

      <div style={{ marginTop: 16 }}>
        <strong style={{ display: "block", marginBottom: 8 }}>Integrações</strong>
        {client.integrations.length ? client.integrations.map((integration) => (
          <div className="statusRow" key={integration.provider}>
            <div>
              <strong>{integration.provider}</strong>
              <div className="muted" style={{ marginTop: 3 }}>{integration.detail}</div>
            </div>
            <StatusBadge status={integration.status} compact />
          </div>
        )) : (
          <p className="muted">Nenhuma integração externa configurada.</p>
        )}
      </div>
    </article>
  );
}

function Metric({ label, value, detail, critical = false }: {
  label: string;
  value: string | number;
  detail: string;
  critical?: boolean;
}) {
  return (
    <article className={`metricCard ${critical ? "critical" : ""}`}>
      <span>{label}</span>
      <strong>{typeof value === "number" ? number.format(value) : value}</strong>
      <small>{detail}</small>
    </article>
  );
}

function Mini({ label, value, critical = false }: { label: string; value: string; critical?: boolean }) {
  return (
    <div className={`miniValue ${critical ? "criticalText" : ""}`}>
      <strong>{value}</strong>
      <span>{label}</span>
    </div>
  );
}

function ServiceHealth({ label, status }: { label: string; status: ServiceStatus }) {
  const state = status === "OPERATIONAL" ? "good" : "warning";
  return (
    <div className="healthItem">
      <span className={`healthDot ${state}`} />
      <div>
        <span>{label}</span>
        <strong>{statusLabel(status)}</strong>
      </div>
    </div>
  );
}

function StatusBadge({ status, compact = false }: { status: ServiceStatus; compact?: boolean }) {
  const good = status === "OPERATIONAL";
  const warning = status === "WARNING";
  return (
    <span
      style={{
        display: "inline-flex",
        alignItems: "center",
        gap: 7,
        padding: compact ? "5px 9px" : "7px 11px",
        borderRadius: 999,
        background: good ? "#e9f6ed" : warning ? "#fff5dc" : "#fff0ee",
        color: good ? "#22633b" : warning ? "#89600d" : "#a8332d",
        fontWeight: 700,
        fontSize: 12,
        whiteSpace: "nowrap",
      }}
    >
      <span style={{ width: 7, height: 7, borderRadius: "50%", background: "currentColor" }} />
      {statusLabel(status)}
    </span>
  );
}

function statusLabel(status: ServiceStatus) {
  if (status === "OPERATIONAL") return "Operacional";
  if (status === "WARNING") return "Atenção";
  return "Com problema";
}
