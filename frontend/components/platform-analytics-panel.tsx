"use client";

import {
  useEffect,
  useMemo,
  useState,
} from "react";

import {
  getPlatformAnalytics,
  PlatformAnalytics,
} from "@/lib/api";

const currency = new Intl.NumberFormat("pt-BR", {
  style: "currency",
  currency: "BRL",
});

const number = new Intl.NumberFormat("pt-BR");

const PERIODS = [
  { hours: 24, label: "24 horas" },
  { hours: 168, label: "7 dias" },
  { hours: 720, label: "30 dias" },
  { hours: 2160, label: "90 dias" },
  { hours: 8760, label: "1 ano" },
];

export function PlatformAnalyticsPanel() {
  const [hours, setHours] = useState(720);

  const [analytics, setAnalytics] =
    useState<PlatformAnalytics | null>(null);

  const [loading, setLoading] =
    useState(false);

  const [error, setError] =
    useState<string | null>(null);

  useEffect(() => {
    let cancelled = false;

    async function load() {
      setLoading(true);
      setError(null);

      try {
        const result =
          await getPlatformAnalytics(hours);

        if (!cancelled) {
          setAnalytics(result);
        }
      } catch (requestError) {
        if (!cancelled) {
          setError(
            requestError instanceof Error
              ? requestError.message
              : "Não foi possível carregar o Analytics global.",
          );
        }
      } finally {
        if (!cancelled) {
          setLoading(false);
        }
      }
    }

    void load();

    return () => {
      cancelled = true;
    };
  }, [hours]);

  const busiestHours = useMemo(() => {
    if (!analytics) {
      return [];
    }

    return [...analytics.orders_by_hour]
      .filter((item) => item.orders > 0)
      .sort((a, b) => {
        if (b.orders !== a.orders) {
          return b.orders - a.orders;
        }

        return b.revenue - a.revenue;
      })
      .slice(0, 5);
  }, [analytics]);

  return (
    <section
      className="analyticsSection"
      id="analytics-global"
    >
      <div className="analyticsHeader">
        <div>
          <p className="eyebrow">
            INTELIGÊNCIA DA PLATAFORMA
          </p>

          <h2>Analytics Global</h2>

          <p>
            Visão agregada das empresas e lojas
            conectadas à SmartFoodIA.
          </p>
        </div>

        <div className="analyticsPeriod">
          <label htmlFor="platform-analytics-period">
            Período
          </label>

          <select
            id="platform-analytics-period"
            value={hours}
            onChange={(event) =>
              setHours(Number(event.target.value))
            }
            disabled={loading}
          >
            {PERIODS.map((period) => (
              <option
                key={period.hours}
                value={period.hours}
              >
                {period.label}
              </option>
            ))}
          </select>
        </div>
      </div>

      {error && (
        <div className="errorBox">
          <strong>
            Não foi possível carregar o Analytics global.
          </strong>
          <span>{error}</span>
        </div>
      )}

      {loading && !analytics ? (
        <div className="analyticsLoading">
          Carregando inteligência da plataforma...
        </div>
      ) : analytics ? (
        <>
          <div className="analyticsMetrics">
            <Metric
              label="Faturamento gerado"
              value={currency.format(
                analytics.summary.revenue,
              )}
              detail={`${number.format(
                analytics.summary.orders_valid,
              )} pedidos válidos`}
            />

            <Metric
              label="Ticket médio"
              value={currency.format(
                analytics.summary.average_ticket,
              )}
              detail="média global por pedido"
            />

            <Metric
              label="Empresas ativas"
              value={number.format(
                analytics.summary.companies_active,
              )}
              detail={`${number.format(
                analytics.summary.companies_total,
              )} cadastradas`}
            />

            <Metric
              label="Empresas vendendo"
              value={number.format(
                analytics.summary.companies_with_orders,
              )}
              detail="com pedidos no período"
            />

            <Metric
              label="Lojas ativas"
              value={number.format(
                analytics.summary.stores_active,
              )}
              detail={`${number.format(
                analytics.summary.stores_total,
              )} cadastradas`}
            />

            <Metric
              label="Lojas com pedidos"
              value={number.format(
                analytics.summary.stores_with_orders,
              )}
              detail="com vendas no período"
            />

            <Metric
              label="Pedidos registrados"
              value={number.format(
                analytics.summary.orders_total,
              )}
              detail={`${number.format(
                analytics.summary.orders_valid,
              )} válidos`}
            />

            <Metric
              label="Cancelamentos"
              value={number.format(
                analytics.summary.orders_cancelled,
              )}
              detail="pedidos cancelados"
              critical={
                analytics.summary.orders_cancelled > 0
              }
            />
          </div>

          <div className="analyticsGrid">
            <Card
              title="Modalidade dos pedidos"
              description="Perfil global de atendimento"
            >
              <Ranking
                items={analytics.service_modes.map(
                  (item) => ({
                    key: item.service_mode,
                    label: serviceModeLabel(
                      item.service_mode,
                    ),
                    value: `${number.format(
                      item.orders,
                    )} pedidos`,
                    secondary: currency.format(
                      item.revenue,
                    ),
                  }),
                )}
              />
            </Card>

            <Card
              title="Formas de pagamento"
              description="Preferência de pagamento na plataforma"
            >
              <Ranking
                items={analytics.payment_methods.map(
                  (item) => ({
                    key: item.payment_method,
                    label: paymentLabel(
                      item.payment_method,
                    ),
                    value: `${number.format(
                      item.orders,
                    )} pedidos`,
                    secondary: currency.format(
                      item.revenue,
                    ),
                  }),
                )}
              />
            </Card>

            <Card
              title="Estados"
              description="Distribuição geográfica das vendas"
            >
              <Ranking
                items={analytics.states.map(
                  (item) => ({
                    key: item.state,
                    label: item.state || "Não informado",
                    value: `${number.format(
                      item.orders,
                    )} pedidos`,
                    secondary:
                      `${number.format(
                        item.stores,
                      )} lojas • ${currency.format(
                        item.revenue,
                      )}`,
                  }),
                )}
                empty="Ainda não existem estados com vendas."
              />
            </Card>

            <Card
              title="Cidades"
              description="Mercados com maior movimento"
            >
              <Ranking
                items={analytics.cities.map(
                  (item) => ({
                    key: `${item.state}-${item.city}`,
                    label: `${item.city} - ${item.state}`,
                    value: `${number.format(
                      item.orders,
                    )} pedidos`,
                    secondary:
                      `${number.format(
                        item.stores,
                      )} lojas • ${currency.format(
                        item.revenue,
                      )}`,
                  }),
                )}
                empty="Ainda não existem cidades com vendas."
              />
            </Card>

            <Card
              title="Produtos mais vendidos"
              description="Ranking agregado da plataforma"
              wide
            >
              <Ranking
                items={analytics.top_products.map(
                  (item, index) => ({
                    key: `${item.name}-${index}`,
                    label: item.name,
                    value: `${number.format(
                      item.quantity,
                    )} un.`,
                    secondary:
                      `${number.format(
                        item.stores,
                      )} lojas • ${currency.format(
                        item.revenue,
                      )}`,
                  }),
                )}
                empty="Nenhum produto vendido no período."
              />
            </Card>

            <Card
              title="Complementos mais vendidos"
              description="Adicionais com maior procura"
              wide
            >
              <Ranking
                items={analytics.top_modifiers.map(
                  (item, index) => ({
                    key: `${item.name}-${index}`,
                    label: item.name,
                    value: `${number.format(
                      item.quantity,
                    )} un.`,
                    secondary:
                      `${number.format(
                        item.stores,
                      )} lojas • ${currency.format(
                        item.revenue,
                      )}`,
                  }),
                )}
                empty="Nenhum complemento vendido no período."
              />
            </Card>

            <Card
              title="Pedidos por dia da semana"
              description="Horário local de cada loja"
              wide
            >
              <WeekdayChart
                data={analytics.orders_by_weekday}
              />
            </Card>

            <Card
              title="Horários de maior movimento"
              description="Top 5 horários da plataforma"
            >
              <Ranking
                items={busiestHours.map((item) => ({
                  key: String(item.hour),
                  label: `${String(
                    item.hour,
                  ).padStart(2, "0")}:00`,
                  value: `${number.format(
                    item.orders,
                  )} pedidos`,
                  secondary: currency.format(
                    item.revenue,
                  ),
                }))}
                empty="Nenhum horário com pedidos."
              />
            </Card>

            <Card
              title="Movimento ao longo do dia"
              description="Distribuição global das 24 horas"
              wide
            >
              <HourlyChart
                data={analytics.orders_by_hour}
              />
            </Card>
          </div>

          <div className="analyticsFoot">
            <span>
              Dados agregados da plataforma
            </span>

            <span>
              Atualizado em{" "}
              {new Date(
                analytics.generated_at,
              ).toLocaleString("pt-BR")}
            </span>
          </div>
        </>
      ) : null}
    </section>
  );
}

function Metric({
  label,
  value,
  detail,
  critical = false,
}: {
  label: string;
  value: string;
  detail: string;
  critical?: boolean;
}) {
  return (
    <article
      className={`analyticsMetric ${
        critical ? "critical" : ""
      }`}
    >
      <span>{label}</span>
      <strong>{value}</strong>
      <small>{detail}</small>
    </article>
  );
}

function Card({
  title,
  description,
  children,
  wide = false,
}: {
  title: string;
  description: string;
  children: React.ReactNode;
  wide?: boolean;
}) {
  return (
    <article
      className={`analyticsCard ${
        wide ? "wide" : ""
      }`}
    >
      <header>
        <h3>{title}</h3>
        <p>{description}</p>
      </header>

      {children}
    </article>
  );
}

function Ranking({
  items,
  empty = "Nenhum dado disponível.",
}: {
  items: Array<{
    key: string;
    label: string;
    value: string;
    secondary: string;
  }>;
  empty?: string;
}) {
  if (!items.length) {
    return (
      <p className="analyticsEmpty">
        {empty}
      </p>
    );
  }

  return (
    <div className="analyticsRanking">
      {items.map((item, index) => (
        <div
          className="analyticsRankingRow"
          key={item.key}
        >
          <span className="analyticsRank">
            {index + 1}
          </span>

          <div>
            <strong>{item.label}</strong>
            <small>{item.secondary}</small>
          </div>

          <b>{item.value}</b>
        </div>
      ))}
    </div>
  );
}

function WeekdayChart({
  data,
}: {
  data: PlatformAnalytics["orders_by_weekday"];
}) {
  const maxOrders = Math.max(
    ...data.map((item) => item.orders),
    1,
  );

  return (
    <div className="weekdayChart">
      {data.map((item) => (
        <div
          className="weekdayRow"
          key={item.weekday}
        >
          <span>
            {shortWeekday(item.label)}
          </span>

          <div className="weekdayTrack">
            <div
              className="weekdayFill"
              style={{
                width: `${
                  (item.orders / maxOrders) * 100
                }%`,
              }}
            />
          </div>

          <strong>
            {number.format(item.orders)}
          </strong>

          <small>
            {currency.format(item.revenue)}
          </small>
        </div>
      ))}
    </div>
  );
}

function HourlyChart({
  data,
}: {
  data: PlatformAnalytics["orders_by_hour"];
}) {
  const maxOrders = Math.max(
    ...data.map((item) => item.orders),
    1,
  );

  return (
    <div className="hourlyChart">
      {data.map((item) => (
        <div
          className="hourlyColumn"
          key={item.hour}
          title={`${String(
            item.hour,
          ).padStart(2, "0")}:00 — ${
            item.orders
          } pedidos — ${currency.format(
            item.revenue,
          )}`}
        >
          <div className="hourlyBarArea">
            <div
              className="hourlyBar"
              style={{
                height: `${
                  (item.orders / maxOrders) * 100
                }%`,
              }}
            />
          </div>

          <span>
            {String(item.hour).padStart(
              2,
              "0",
            )}
          </span>
        </div>
      ))}
    </div>
  );
}

function shortWeekday(label: string) {
  const labels: Record<string, string> = {
    "Segunda-feira": "Seg",
    "Terça-feira": "Ter",
    "Quarta-feira": "Qua",
    "Quinta-feira": "Qui",
    "Sexta-feira": "Sex",
    Sábado: "Sáb",
    Domingo: "Dom",
  };

  return labels[label] ?? label;
}

function serviceModeLabel(mode: string) {
  const labels: Record<string, string> = {
    DELIVERY: "Delivery",
    TAKEOUT: "Retirada",
  };

  return labels[mode] ?? mode;
}

function paymentLabel(method: string) {
  const labels: Record<string, string> = {
    PIX: "PIX",
    CASH: "Dinheiro",
    CREDIT_CARD: "Cartão de crédito",
    DEBIT_CARD: "Cartão de débito",
    CARD: "Cartão",
  };

  return (
    labels[method] ??
    method.replaceAll("_", " ")
  );
}
