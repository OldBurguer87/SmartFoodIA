"use client";

import {
  useEffect,
  useState,
} from "react";

import {
  getShiftClosing,
  ShiftClosingReport,
} from "@/lib/api";

const currency = new Intl.NumberFormat("pt-BR", {
  style: "currency",
  currency: "BRL",
});

const number = new Intl.NumberFormat("pt-BR");

function todayInputValue() {
  const now = new Date();
  const offset = now.getTimezoneOffset();
  const local = new Date(
    now.getTime() - offset * 60_000,
  );
  return local.toISOString().slice(0, 10);
}

function paymentLabel(method: string) {
  const labels: Record<string, string> = {
    PIX: "PIX",
    CASH: "Dinheiro",
    DEBIT: "Cartão de débito",
    CREDIT: "Cartão de crédito",
  };

  return labels[method] ?? method;
}

export function ShiftClosingPanel({
  storeId,
}: {
  storeId: string;
}) {
  const [shiftDate, setShiftDate] =
    useState(todayInputValue);

  const [report, setReport] =
    useState<ShiftClosingReport | null>(null);

  const [loading, setLoading] =
    useState(false);

  const [error, setError] =
    useState<string | null>(null);

  useEffect(() => {
    let cancelled = false;

    async function load() {
      if (!storeId || !shiftDate) {
        setReport(null);
        return;
      }

      setLoading(true);
      setError(null);

      try {
        const result = await getShiftClosing(
          storeId,
          shiftDate,
        );

        if (!cancelled) {
          setReport(result);
        }
      } catch (requestError) {
        if (!cancelled) {
          setReport(null);
          setError(
            requestError instanceof Error
              ? requestError.message
              : "Não foi possível carregar o fechamento.",
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
  }, [storeId, shiftDate]);

  return (
    <section
      className="analyticsSection"
      id="fechamento-turno"
    >
      <div className="analyticsHeader">
        <div>
          <p className="eyebrow">
            FECHAMENTO DE TURNO
          </p>
          <h2>Resultado do turno</h2>
          <p>
            Pedidos, faturamento, pagamentos e
            conferência PIX.
          </p>
        </div>

        <div className="analyticsPeriod">
          <label htmlFor="shift-closing-date">
            Data do turno
          </label>

          <input
            id="shift-closing-date"
            type="date"
            value={shiftDate}
            onChange={(event) =>
              setShiftDate(event.target.value)
            }
            disabled={loading}
          />
        </div>
      </div>

      {error && (
        <div className="errorBox">{error}</div>
      )}

      {loading && (
        <div className="analyticsLoading">
          Carregando fechamento...
        </div>
      )}

      {!loading && report && !report.configured && (
        <div className="analyticsEmpty">
          Não há turno configurado para esta data.
        </div>
      )}

      {!loading && report?.configured && (
        <div className="analyticsMetrics">
          <article className="analyticsMetric">
            <span>Faturamento</span>
            <strong>
              {currency.format(report.financial.revenue)}
            </strong>
          </article>

          <article className="analyticsMetric">
            <span>Ticket médio</span>
            <strong>
              {currency.format(report.financial.average_ticket)}
            </strong>
          </article>

          <article className="analyticsMetric">
            <span>Pedidos válidos</span>
            <strong>{number.format(report.orders.valid)}</strong>
          </article>

          <article className="analyticsMetric">
            <span>Cancelados</span>
            <strong>{number.format(report.orders.cancelled)}</strong>
          </article>

          <article className="analyticsMetric">
            <span>Total recebido</span>
            <strong>
              {currency.format(report.financial.payment_total)}
            </strong>
          </article>

          <article className="analyticsMetric">
            <span>Conferência</span>
            <strong>
              {Math.abs(report.financial.difference) < 0.01
                ? "OK"
                : currency.format(report.financial.difference)}
            </strong>
          </article>
        </div>
      )}

      {!loading && report?.configured && (
        <div className="analyticsGrid shiftClosingGrid">
          <article className="analyticsCard shiftClosingCard">
            <h3>Formas de pagamento</h3>

            <div className="analyticsRanking">
              {report.financial.payment_methods.map((item) => (
                <div
                  className="analyticsRankingRow shiftClosingRow"
                  key={item.method}
                >
                  <div>
                    <strong>{paymentLabel(item.method)}</strong>
                    <span>
                      {number.format(item.orders)} pedido(s)
                    </span>
                  </div>

                  <strong>{currency.format(item.amount)}</strong>
                </div>
              ))}
            </div>
          </article>

          <article className="analyticsCard shiftClosingCard">
            <h3>Conferência PIX</h3>

            <div className="analyticsRanking">
              <div className="analyticsRankingRow shiftClosingRow">
                <span>Pedidos em PIX</span>
                <strong>{number.format(report.pix.orders)}</strong>
              </div>

              <div className="analyticsRankingRow shiftClosingRow">
                <span>Total em PIX</span>
                <strong>{currency.format(report.pix.amount)}</strong>
              </div>

              <div className="analyticsRankingRow shiftClosingRow">
                <span>PIX confirmados</span>
                <strong>
                  {number.format(report.pix.confirmed_orders)}
                </strong>
              </div>

              <div className="analyticsRankingRow shiftClosingRow">
                <span>Valor confirmado</span>
                <strong>
                  {currency.format(report.pix.confirmed_amount)}
                </strong>
              </div>
              <div className="analyticsRankingRow shiftClosingRow">
                <span>Confirmação automática</span>
                <strong>
                  {number.format(report.pix.auto_confirmed)}
                </strong>
              </div>
              <div className="analyticsRankingRow shiftClosingRow">
                <span>Confirmado pela equipe</span>
                <strong>
                  {number.format(report.pix.human_confirmed)}
                </strong>
              </div>

              <div className="analyticsRankingRow shiftClosingRow">
                <span>Pendentes de revisão</span>
                <strong>
                  {number.format(report.pix.pending_review)}
                </strong>
              </div>

              <div className="analyticsRankingRow shiftClosingRow">
                <span>Sem comprovante</span>
                <strong>
                  {number.format(report.pix.without_receipt)}
                </strong>
              </div>
            </div>
          </article>

          <article className="analyticsCard shiftClosingCard">
            <h3>Status dos pedidos</h3>

            <div className="analyticsRanking">
              {Object.entries(report.orders.by_status).map(
                ([status, count]) => (
                  <div
                    className="analyticsRankingRow shiftClosingRow"
                    key={status}
                  >
                    <span>
                        {status === "CANCELLED"
                          ? "Cancelados"
                          : status === "CONCLUDED"
                            ? "Concluídos"
                            : status}
                      </span>
                    <strong>{number.format(count)}</strong>
                  </div>
                ),
              )}
            </div>
          </article>
        </div>
      )}

      {!loading && report?.configured && (
        <div className="analyticsFoot">
          <span>
            {report.store_name} • turno de{" "}
            {report.started_at?.slice(11, 16)} até{" "}
            {report.ends_at?.slice(11, 16)}
          </span>
          {report.pix.fallback_values > 0 && (
            <span>
              PIX com valor conciliado pelo pedido:{" "}
              {number.format(report.pix.fallback_values)}
            </span>
          )}
        </div>
      )}
    </section>
  );
}
