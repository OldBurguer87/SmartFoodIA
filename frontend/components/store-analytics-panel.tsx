"use client";

import {
  useEffect,
  useMemo,
  useState,
} from "react";
import {
  getStoreAnalytics,
  StoreAnalytics,
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

export function StoreAnalyticsPanel({
  storeId,
}: {
  storeId: string;
}) {
  const [hours, setHours] = useState(720);
  const [analytics, setAnalytics] =
    useState<StoreAnalytics | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] =
    useState<string | null>(null);

  useEffect(() => {
    let cancelled = false;

    async function load() {
      if (!storeId) {
        setAnalytics(null);
        return;
      }

      setLoading(true);
      setError(null);

      try {
        const result = await getStoreAnalytics(
          storeId,
          hours,
        );

        if (!cancelled) {
          setAnalytics(result);
        }
      } catch (requestError) {
        if (!cancelled) {
          setError(
            requestError instanceof Error
              ? requestError.message
              : "Não foi possível carregar o Analytics.",
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
  }, [storeId, hours]);

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

  if (error) {
    return (
      <section
        className="analyticsSection"
        id="analytics"
      >
        <div className="analyticsHeader">
          <div>
            <p className="eyebrow">
              INTELIGÊNCIA COMERCIAL
            </p>
            <h2>Analytics da loja</h2>
          </div>
        </div>

        <div className="errorBox">
          <strong>
            Não foi possível carregar o Analytics.
          </strong>
          <span>{error}</span>
        </div>
      </section>
    );
  }

  return (
    <section
      className="analyticsSection"
      id="analytics"
    >
      <div className="analyticsHeader">
        <div>
          <p className="eyebrow">
            INTELIGÊNCIA COMERCIAL
          </p>
          <h2>Analytics da loja</h2>
          <p>
            Vendas, clientes e comportamento dos
            pedidos.
          </p>
        </div>

        <div className="analyticsPeriod">
          <label htmlFor="analytics-period">
            Período
          </label>
          <select
            id="analytics-period"
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

      {loading && !analytics ? (
        <div className="analyticsLoading">
          Carregando indicadores...
        </div>
      ) : analytics ? (
        <>
          <div className="analyticsMetrics">
            <AnalyticsMetric
              label="Vendas geradas"
              value={currency.format(
                analytics.summary.revenue,
              )}
              detail={`${number.format(
                analytics.summary.orders_valid,
              )} pedidos válidos`}
            />

            <AnalyticsMetric
              label="Ticket médio"
              value={currency.format(
                analytics.summary.average_ticket,
              )}
              detail="por pedido válido"
            />

            <AnalyticsMetric
              label="Clientes únicos"
              value={number.format(
                analytics.summary.unique_customers,
              )}
              detail="no período selecionado"
            />

            <AnalyticsMetric
              label="Clientes novos"
              value={number.format(
                analytics.summary.new_customers,
              )}
              detail="primeira compra na loja"
            />

            <AnalyticsMetric
              label="Clientes recorrentes"
              value={number.format(
                analytics.summary.returning_customers,
              )}
              detail="já compraram anteriormente"
            />

            <AnalyticsMetric
              label="Cancelamentos"
              value={number.format(
                analytics.summary.orders_cancelled,
              )}
              detail={`${number.format(
                analytics.summary.orders_total,
              )} pedidos registrados`}
              critical={
                analytics.summary.orders_cancelled > 0
              }
            />
          </div>

          <div className="analyticsGrid">
            <AnalyticsCard
              title="Modalidade dos pedidos"
              description="Delivery e retirada"
            >
              <RankingList
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
            </AnalyticsCard>

            <AnalyticsCard
              title="Formas de pagamento"
              description="Preferência dos clientes"
            >
              <RankingList
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
            </AnalyticsCard>

            <AnalyticsCard
              title="Produtos mais vendidos"
              description="Ranking por quantidade"
              wide
            >
              <RankingList
                items={analytics.top_products.map(
                  (item) => ({
                    key:
                      item.product_id ??
                      item.external_code ??
                      item.name,
                    label: item.name,
                    value: `${number.format(
                      item.quantity,
                    )} un.`,
                    secondary: currency.format(
                      item.revenue,
                    ),
                  }),
                )}
                empty="Ainda não há produtos vendidos neste período."
              />
            </AnalyticsCard>

            <AnalyticsCard
              title="Complementos mais vendidos"
              description="Adicionais escolhidos pelos clientes"
            >
              <RankingList
                items={analytics.top_modifiers.map(
                  (item) => ({
                    key:
                      item.modifier_id ??
                      item.external_code ??
                      item.name,
                    label: item.name,
                    value: `${number.format(
                      item.quantity,
                    )} un.`,
                    secondary: currency.format(
                      item.revenue,
                    ),
                  }),
                )}
                empty="Nenhum complemento vendido no período."
              />
            </AnalyticsCard>

            <AnalyticsCard
              title="Bairros com mais pedidos"
              description="Somente pedidos delivery"
            >
              <RankingList
                items={analytics.top_neighborhoods.map(
                  (item) => ({
                    key: item.neighborhood,
                    label: item.neighborhood,
                    value: `${number.format(
                      item.orders,
                    )} pedidos`,
                    secondary: currency.format(
                      item.revenue,
                    ),
                  }),
                )}
                empty="Nenhum bairro com pedidos no período."
              />
            </AnalyticsCard>

            <AnalyticsCard
              title="Pedidos por dia da semana"
              description="Horário local da loja"
              wide
            >
              <WeekdayChart
                data={analytics.orders_by_weekday}
              />
            </AnalyticsCard>

            <AnalyticsCard
              title="Horários de maior movimento"
              description="Top 5 faixas por número de pedidos"
            >
              <RankingList
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
                empty="Ainda não há horários com pedidos."
              />
            </AnalyticsCard>

            <AnalyticsCard
              title="Movimento ao longo do dia"
              description="Distribuição das 24 horas"
              wide
            >
              <HourlyChart
                data={analytics.orders_by_hour}
              />
            </AnalyticsCard>
          </div>

          <div className="analyticsFoot">
            <span>
              Fuso horário: {analytics.timezone}
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

function AnalyticsMetric({
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

function AnalyticsCard({
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

function RankingList({
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
  data: StoreAnalytics["orders_by_weekday"];
}) {
  const maxOrders = Math.max(
    ...data.map((item) => item.orders),
    1,
  );

  return (
    <div className="weekdayChart">
      {data.map((item) => {
        const width =
          (item.orders / maxOrders) * 100;

        return (
          <div
            className="weekdayRow"
            key={item.weekday}
          >
            <span>{shortWeekday(item.label)}</span>

            <div className="weekdayTrack">
              <div
                className="weekdayFill"
                style={{
                  width: `${width}%`,
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
        );
      })}
    </div>
  );
}

function HourlyChart({
  data,
}: {
  data: StoreAnalytics["orders_by_hour"];
}) {
  const maxOrders = Math.max(
    ...data.map((item) => item.orders),
    1,
  );

  return (
    <div className="hourlyChart">
      {data.map((item) => {
        const height =
          (item.orders / maxOrders) * 100;

        return (
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
                  height: `${height}%`,
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
        );
      })}
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
