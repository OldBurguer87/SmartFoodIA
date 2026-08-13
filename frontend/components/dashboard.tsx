"use client";

import { FormEvent, useEffect, useMemo, useState } from "react";
import { getOperationalOverview, OperationalOverview } from "@/lib/api";
import { LogoMark, RefreshIcon } from "@/components/icons";
import { ConversationsConsole } from "@/components/conversations-console";
import { CommercialRulesPanel } from "@/components/commercial-rules-panel";

const currency = new Intl.NumberFormat("pt-BR", {
  style: "currency",
  currency: "BRL",
});

const number = new Intl.NumberFormat("pt-BR");

type DashboardProps = {
  initialStoreId?: string;
};

export function Dashboard({ initialStoreId = "" }: DashboardProps) {
  const [storeId, setStoreId] = useState(initialStoreId);
  const [draftStoreId, setDraftStoreId] = useState(initialStoreId);
  const [hours, setHours] = useState(24);
  const [overview, setOverview] = useState<OperationalOverview | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  async function loadOverview(nextStoreId = storeId) {
    if (!nextStoreId.trim()) {
      setOverview(null);
      return;
    }

    setLoading(true);
    setError(null);
    try {
      const result = await getOperationalOverview(nextStoreId.trim(), hours);
      setOverview(result);
      localStorage.setItem("smartfoodia.storeId", nextStoreId.trim());
    } catch (requestError) {
      setError(
        requestError instanceof Error
          ? requestError.message
          : "Não foi possível carregar os dados.",
      );
    } finally {
      setLoading(false);
    }
  }

  useEffect(() => {
    const saved = localStorage.getItem("smartfoodia.storeId");
    if (saved && !storeId) {
      setStoreId(saved);
      setDraftStoreId(saved);
    }
  }, [storeId]);

  useEffect(() => {
    if (storeId) {
      void loadOverview(storeId);
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [storeId, hours]);

  function submitStore(event: FormEvent) {
    event.preventDefault();
    const normalized = draftStoreId.trim();
    setStoreId(normalized);
    if (normalized === storeId) {
      void loadOverview(normalized);
    }
  }

  const queueProblems = useMemo(() => {
    if (!overview) return 0;
    return (
      overview.queue.events_retry +
      overview.queue.events_dead +
      overview.queue.outbound_retry +
      overview.queue.outbound_dead
    );
  }, [overview]);

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
          <a className="navItem active" href="#regras-comerciais">Regras comerciais</a>
          <a className="navItem" href="#visao-geral">Visão geral</a>
          <a className="navItem" href="#conversas">Conversas</a>
          <a className="navItem" href="#pedidos">Pedidos</a>
          <a className="navItem" href="#tickets">Tickets</a>
          <a className="navItem" href="#conhecimento">Conhecimento</a>
          <a className="navItem" href="#sistema">Sistema</a>
        </nav>

        <div className="sidebarFoot">
          <div className="statusDot" />
          <div>
            <strong>Olívia em operação</strong>
            <span>Monitoramento do piloto</span>
          </div>
        </div>
      </aside>

      <main className="main">
        <header className="topbar">
          <div>
            <p className="eyebrow">OLD BURGUER 87</p>
            <h1>Painel operacional</h1>
            <p className="subtitle">
              Acompanhe atendimento, pedidos e saúde do sistema.
            </p>
          </div>
          <button
            className="refreshButton"
            onClick={() => void loadOverview()}
            disabled={loading || !storeId}
          >
            <RefreshIcon />
            {loading ? "Atualizando..." : "Atualizar"}
          </button>
        </header>

        <section className="connectionPanel">
          <form onSubmit={submitStore}>
            <label htmlFor="storeId">ID da loja</label>
            <div className="storeInputRow">
              <input
                id="storeId"
                value={draftStoreId}
                onChange={(event) => setDraftStoreId(event.target.value)}
                placeholder="Cole aqui o UUID da Old Burguer 87"
              />
              <select
                value={hours}
                onChange={(event) => setHours(Number(event.target.value))}
                aria-label="Período do painel"
              >
                <option value={24}>Últimas 24 horas</option>
                <option value={168}>Últimos 7 dias</option>
                <option value={720}>Últimos 30 dias</option>
              </select>
              <button type="submit">Carregar</button>
            </div>
          </form>
        </section>

        {!storeId && (
          <section className="emptyState">
            <LogoMark size={52} />
            <h2>Conecte a loja ao painel</h2>
            <p>
              Informe o UUID da Old Burguer 87. O navegador guardará esse dado
              neste computador para os próximos acessos.
            </p>
          </section>
        )}

        {error && (
          <section className="errorBox">
            <strong>Não foi possível carregar o painel.</strong>
            <span>{error}</span>
          </section>
        )}

        {overview && (
          <>
            <CommercialRulesPanel storeId={storeId} />

            <section className="metricsGrid" id="visao-geral">
              <Metric
                label="Conversas ativas"
                value={overview.conversations.open + overview.conversations.human}
                detail={`${overview.conversations.human} com atendente`}
              />
              <Metric
                label="Pedidos"
                value={overview.orders.total}
                detail={`No período de ${overview.period_hours}h`}
              />
              <Metric
                label="Receita"
                value={currency.format(overview.orders.revenue)}
                detail="Pedidos registrados"
              />
              <Metric
                label="Tickets ativos"
                value={overview.tickets.open + overview.tickets.in_progress}
                detail={`${overview.tickets.urgent_active} urgentes`}
                critical={overview.tickets.urgent_active > 0}
              />
            </section>

            <section className="dashboardGrid">
              <article className="panel wide" id="conversas">
                <PanelHeader
                  title="Atendimento"
                  description="Distribuição das conversas no período"
                />
                <div className="progressList">
                  <Progress
                    label="Olívia"
                    value={overview.conversations.open}
                    total={Math.max(overview.conversations.total, 1)}
                  />
                  <Progress
                    label="Atendimento humano"
                    value={overview.conversations.human}
                    total={Math.max(overview.conversations.total, 1)}
                  />
                  <Progress
                    label="Encerradas"
                    value={overview.conversations.closed}
                    total={Math.max(overview.conversations.total, 1)}
                  />
                </div>
              </article>

              <article className="panel" id="pedidos">
                <PanelHeader title="Pedidos" description="Status atuais" />
                <div className="statusList">
                  {Object.entries(overview.orders.by_status).length ? (
                    Object.entries(overview.orders.by_status).map(
                      ([status, count]) => (
                        <div className="statusRow" key={status}>
                          <span>{formatStatus(status)}</span>
                          <strong>{number.format(count)}</strong>
                        </div>
                      ),
                    )
                  ) : (
                    <p className="muted">Nenhum pedido no período.</p>
                  )}
                </div>
              </article>

              <article className="panel" id="tickets">
                <PanelHeader title="Tickets" description="Suporte da operação" />
                <div className="miniGrid">
                  <MiniValue label="Abertos" value={overview.tickets.open} />
                  <MiniValue
                    label="Em andamento"
                    value={overview.tickets.in_progress}
                  />
                  <MiniValue
                    label="Resolvidos"
                    value={overview.tickets.resolved}
                  />
                  <MiniValue
                    label="Urgentes"
                    value={overview.tickets.urgent_active}
                    critical={overview.tickets.urgent_active > 0}
                  />
                </div>
              </article>

              <article className="panel wide" id="sistema">
                <PanelHeader
                  title="Saúde do sistema"
                  description="IA, filas e mensagens"
                />
                <div className="healthGrid">
                  <HealthItem
                    label="Tempo médio da IA"
                    value={`${number.format(overview.ai.average_duration_ms)} ms`}
                    state={overview.ai.errors ? "warning" : "good"}
                  />
                  <HealthItem
                    label="Erros da IA"
                    value={number.format(overview.ai.errors)}
                    state={overview.ai.errors ? "warning" : "good"}
                  />
                  <HealthItem
                    label="Fila com atenção"
                    value={number.format(queueProblems)}
                    state={queueProblems ? "warning" : "good"}
                  />
                  <HealthItem
                    label="Mensagens enviadas"
                    value={number.format(overview.queue.outbound_sent)}
                    state="good"
                  />
                </div>
              </article>

              <article className="panel" id="conhecimento">
                <PanelHeader
                  title="Conhecimento"
                  description="Dúvidas ainda sem resposta aprovada"
                />
                <div className="knowledgeNumber">
                  {number.format(overview.knowledge.open_gaps)}
                </div>
                <p className="muted">
                  lacunas aguardando análise da equipe
                </p>
              </article>

              <article className="panel alertsPanel">
                <PanelHeader
                  title="Alertas"
                  description="Itens que merecem atenção"
                />
                <div className="alertsList">
                  {overview.alerts.length ? (
                    overview.alerts.map((alert) => (
                      <div
                        className={`alertItem ${alert.severity.toLowerCase()}`}
                        key={alert.code}
                      >
                        <span className="alertMarker" />
                        <div>
                          <strong>{alertTitle(alert.severity)}</strong>
                          <p>{alert.message}</p>
                        </div>
                      </div>
                    ))
                  ) : (
                    <div className="allGood">
                      <span>✓</span>
                      <div>
                        <strong>Operação normal</strong>
                        <p>Nenhum alerta ativo neste momento.</p>
                      </div>
                    </div>
                  )}
                </div>
              </article>
            </section>

            <ConversationsConsole storeId={storeId} />

            <footer className="footer">
              Atualizado em{" "}
              {new Date(overview.generated_at).toLocaleString("pt-BR")}
            </footer>
          </>
        )}
      </main>
    </div>
  );
}

function Metric({
  label,
  value,
  detail,
  critical = false,
}: {
  label: string;
  value: number | string;
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

function PanelHeader({
  title,
  description,
}: {
  title: string;
  description: string;
}) {
  return (
    <header className="panelHeader">
      <div>
        <h2>{title}</h2>
        <p>{description}</p>
      </div>
    </header>
  );
}

function Progress({
  label,
  value,
  total,
}: {
  label: string;
  value: number;
  total: number;
}) {
  const width = Math.min(100, Math.round((value / total) * 100));
  return (
    <div className="progressItem">
      <div>
        <span>{label}</span>
        <strong>{number.format(value)}</strong>
      </div>
      <div className="progressTrack">
        <span style={{ width: `${width}%` }} />
      </div>
    </div>
  );
}

function MiniValue({
  label,
  value,
  critical = false,
}: {
  label: string;
  value: number;
  critical?: boolean;
}) {
  return (
    <div className={`miniValue ${critical ? "criticalText" : ""}`}>
      <strong>{number.format(value)}</strong>
      <span>{label}</span>
    </div>
  );
}

function HealthItem({
  label,
  value,
  state,
}: {
  label: string;
  value: string;
  state: "good" | "warning";
}) {
  return (
    <div className="healthItem">
      <span className={`healthDot ${state}`} />
      <div>
        <span>{label}</span>
        <strong>{value}</strong>
      </div>
    </div>
  );
}

function formatStatus(status: string) {
  const labels: Record<string, string> = {
    PLACED: "Novo",
    CONFIRMED: "Confirmado",
    READY: "Pronto",
    DISPATCHED: "Saiu para entrega",
    CONCLUDED: "Finalizado",
    CANCELLED: "Cancelado",
  };
  return labels[status] ?? status.replaceAll("_", " ");
}

function alertTitle(severity: string) {
  if (severity === "CRITICAL") return "Ação imediata";
  if (severity === "WARNING") return "Atenção";
  return "Informação";
}
