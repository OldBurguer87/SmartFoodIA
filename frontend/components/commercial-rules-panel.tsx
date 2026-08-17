"use client";

import { useEffect, useState } from "react";
import {
  BusinessHour,
  CommercialResponse,
  CommercialRules,
  getCommercialRules,
  saveBusinessHour,
  saveCommercialRules,
  saveDeliveryZone,
} from "@/lib/commercial-api";

const DAYS = [
  "Segunda-feira",
  "Terça-feira",
  "Quarta-feira",
  "Quinta-feira",
  "Sexta-feira",
  "Sábado",
  "Domingo",
];

function timeValue(value: string | null) {
  return value ? value.slice(0, 5) : "";
}

export function CommercialRulesPanel({
  storeId,
}: {
  storeId: string;
}) {
  const [data, setData] = useState<CommercialResponse | null>(null);
  const [rules, setRules] = useState<CommercialRules | null>(null);
  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState(false);
  const [message, setMessage] = useState("");
  const [zoneName, setZoneName] = useState("");
  const [zoneFee, setZoneFee] = useState("");

  async function load() {
    setLoading(true);
    try {
      const result = await getCommercialRules(storeId);
      setData(result);
      setRules(result.rules);
    } catch (error) {
      setMessage(
        error instanceof Error ? error.message : "Erro ao carregar regras.",
      );
    } finally {
      setLoading(false);
    }
  }

  useEffect(() => {
    void load();
  }, [storeId]);

  async function saveRules() {
    if (!rules) return;

    setSaving(true);
    setMessage("");

    try {
      const result = await saveCommercialRules(storeId, rules);
      setData(result);
      setRules(result.rules);
      setMessage("Regras comerciais salvas.");
    } catch (error) {
      setMessage(
        error instanceof Error ? error.message : "Erro ao salvar regras.",
      );
    } finally {
      setSaving(false);
    }
  }

  async function saveHour(
    weekday: number,
    payload: Omit<BusinessHour, "weekday">,
  ) {
    setSaving(true);
    setMessage("");

    try {
      const result = await saveBusinessHour(storeId, weekday, payload);
      setData(result);
      setRules(result.rules);
      setMessage(`${DAYS[weekday]} atualizado.`);
    } catch (error) {
      setMessage(
        error instanceof Error ? error.message : "Erro ao salvar horário.",
      );
    } finally {
      setSaving(false);
    }
  }

  async function addZone() {
    if (!zoneName.trim() || !zoneFee.trim()) return;

    setSaving(true);
    try {
      const result = await saveDeliveryZone(storeId, {
        name: zoneName.trim(),
        fee: Number(zoneFee.replace(",", ".")),
        delivery_allowed: true,
        active: true,
      });
      setData(result);
      setRules(result.rules);
      setZoneName("");
      setZoneFee("");
      setMessage("Bairro/região salvo.");
    } catch (error) {
      setMessage(
        error instanceof Error ? error.message : "Erro ao salvar região.",
      );
    } finally {
      setSaving(false);
    }
  }

  if (loading) {
    return (
      <section className="panel wide" id="regras-comerciais">
        Carregando regras comerciais...
      </section>
    );
  }

  if (!data || !rules) {
    return (
      <section className="panel wide" id="regras-comerciais">
        Não foi possível carregar as regras comerciais.
      </section>
    );
  }

  const hourMap = new Map(
    data.hours.map((item) => [item.weekday, item]),
  );

  return (
    <section
      className="panel wide"
      id="regras-comerciais"
      style={{ gridColumn: "1 / -1" }}
    >
      <header className="panelHeader">
        <div>
          <p className="eyebrow">PRIMEIRA REGRA DA OLÍVIA</p>
          <h2>Regras comerciais</h2>
          <p>
            A Olívia consulta estas regras antes de atender e novamente antes
            de finalizar o pedido.
          </p>
        </div>

        <div
          style={{
            padding: "9px 14px",
            borderRadius: 999,
            fontWeight: 800,
            background: data.current_status.open ? "#e9f6ed" : "#fff0ee",
            color: data.current_status.open ? "#22633b" : "#a8332d",
          }}
        >
          {data.current_status.open ? "● ABERTO" : "● FECHADO"}
        </div>
      </header>

      <div
        style={{
          padding: 14,
          borderRadius: 12,
          background: "#f8f8f6",
          marginBottom: 20,
        }}
      >
        <strong>Status atual</strong>
        <p className="muted" style={{ marginTop: 5 }}>
          {data.current_status.reason}
        </p>
      </div>

      <h3>Operação</h3>

      <div className="miniGrid">
        <label className="miniValue">
          <span>Pedidos pausados manualmente</span>
          <input
            type="checkbox"
            checked={rules.manual_paused}
            onChange={(event) =>
              setRules({
                ...rules,
                manual_paused: event.target.checked,
              })
            }
          />
        </label>

        <label className="miniValue">
          <span>Entrega ativa</span>
          <input
            type="checkbox"
            checked={rules.delivery_enabled}
            onChange={(event) =>
              setRules({
                ...rules,
                delivery_enabled: event.target.checked,
              })
            }
          />
        </label>

        <label className="miniValue">
          <span>Retirada ativa</span>
          <input
            type="checkbox"
            checked={rules.takeout_enabled}
            onChange={(event) =>
              setRules({
                ...rules,
                takeout_enabled: event.target.checked,
              })
            }
          />
        </label>

        <label className="miniValue">
          <span>Tempo médio de preparo (min)</span>
          <input
            type="number"
            min="1"
            value={rules.average_prep_minutes ?? ""}
            onChange={(event) =>
              setRules({
                ...rules,
                average_prep_minutes: event.target.value
                  ? Number(event.target.value)
                  : null,
              })
            }
          />
        </label>
      </div>

      <div style={{ marginTop: 16 }}>
        <label>
          Motivo da pausa
          <input
            style={{ width: "100%", marginTop: 6, padding: 10 }}
            value={rules.pause_reason ?? ""}
            onChange={(event) =>
              setRules({
                ...rules,
                pause_reason: event.target.value || null,
              })
            }
            placeholder="Ex.: cozinha sobrecarregada"
          />
        </label>
      </div>

      <h3 style={{ marginTop: 28 }}>Entrega e valores</h3>

      <div className="miniGrid">
        <label className="miniValue">
          <span>Pedido mínimo para entrega</span>
          <input
            type="number"
            step="0.01"
            min="0"
            value={rules.minimum_delivery_subtotal}
            onChange={(event) =>
              setRules({
                ...rules,
                minimum_delivery_subtotal: Number(event.target.value),
              })
            }
          />
        </label>

        <label className="miniValue">
          <span>Tipo de taxa</span>
          <select
            value={rules.delivery_fee_mode}
            onChange={(event) =>
              setRules({
                ...rules,
                delivery_fee_mode: event.target.value as "FIXED" | "ZONE",
              })
            }
          >
            <option value="FIXED">Taxa fixa</option>
            <option value="ZONE">Por bairro/região</option>
          </select>
        </label>

        {rules.delivery_fee_mode === "FIXED" && (
          <label className="miniValue">
            <span>Taxa fixa de entrega</span>
            <input
              type="number"
              step="0.01"
              min="0"
              value={rules.fixed_delivery_fee}
              onChange={(event) =>
                setRules({
                  ...rules,
                  fixed_delivery_fee: Number(event.target.value),
                })
              }
            />
          </label>
        )}
      </div>

      {rules.delivery_fee_mode === "ZONE" && (
        <div style={{ marginTop: 18 }}>
          <strong>Taxas por bairro/região</strong>

          {data.zones.map((zone) => (
            <div className="statusRow" key={zone.id}>
              <span>{zone.name}</span>
              <strong>
                {zone.delivery_allowed
                  ? `R$ ${zone.fee.toFixed(2).replace(".", ",")}`
                  : "Não atende"}
              </strong>
            </div>
          ))}

          <div
            style={{
              display: "grid",
              gridTemplateColumns: "1fr 160px auto",
              gap: 8,
              marginTop: 12,
            }}
          >
            <input
              placeholder="Bairro ou região"
              value={zoneName}
              onChange={(event) => setZoneName(event.target.value)}
            />
            <input
              placeholder="Taxa"
              value={zoneFee}
              onChange={(event) => setZoneFee(event.target.value)}
            />
            <button
              className="refreshButton"
              type="button"
              onClick={() => void addZone()}
            >
              Adicionar
            </button>
          </div>
        </div>
      )}

      <h3 style={{ marginTop: 28 }}>Formas de pagamento</h3>

      <div className="miniGrid">
        {[
          ["accepts_pix", "PIX"],
          ["accepts_credit", "Crédito"],
          ["accepts_debit", "Débito"],
          ["accepts_cash", "Dinheiro"],
          ["allow_change", "Aceitar pedido de troco"],
        ].map(([key, label]) => (
          <label className="miniValue" key={key}>
            <span>{label}</span>
            <input
              type="checkbox"
              checked={Boolean(rules[key as keyof CommercialRules])}
              onChange={(event) =>
                setRules({
                  ...rules,
                  [key]: event.target.checked,
                })
              }
            />
          </label>
        ))}
      </div>

      {rules.accepts_pix && (
        <>
          <h3 style={{ marginTop: 28 }}>Configuração PIX</h3>

          <p className="muted" style={{ marginBottom: 14 }}>
            Dados oficiais usados pela Olívia para informar e validar
            pagamentos PIX desta empresa.
          </p>

          <div className="miniGrid">
            <label className="miniValue">
              <span>Nome do recebedor</span>
              <input
                value={rules.pix_receiver_name ?? ""}
                onChange={(event) =>
                  setRules({
                    ...rules,
                    pix_receiver_name: event.target.value || null,
                  })
                }
                placeholder="Nome oficial do recebedor"
              />
            </label>

            <label className="miniValue">
              <span>CPF/CNPJ do recebedor</span>
              <input
                value={rules.pix_receiver_document ?? ""}
                onChange={(event) =>
                  setRules({
                    ...rules,
                    pix_receiver_document: event.target.value || null,
                  })
                }
                placeholder="Somente números ou formato cadastrado"
              />
            </label>

            <label className="miniValue">
              <span>Chave PIX</span>
              <input
                value={rules.pix_key ?? ""}
                onChange={(event) =>
                  setRules({
                    ...rules,
                    pix_key: event.target.value || null,
                  })
                }
                placeholder="E-mail, telefone, CPF/CNPJ ou chave aleatória"
              />
            </label>

            <label className="miniValue">
              <span>Instituição recebedora</span>
              <input
                value={rules.pix_receiver_institution ?? ""}
                onChange={(event) =>
                  setRules({
                    ...rules,
                    pix_receiver_institution: event.target.value || null,
                  })
                }
                placeholder="Ex.: MERCADO PAGO IP LTDA"
              />
            </label>

            <label className="miniValue">
              <span>Verificação automática de comprovante</span>
              <input
                type="checkbox"
                checked={rules.pix_auto_verify_enabled}
                onChange={(event) =>
                  setRules({
                    ...rules,
                    pix_auto_verify_enabled: event.target.checked,
                  })
                }
              />
            </label>

            <label className="miniValue">
              <span>Validade máxima do comprovante (min)</span>
              <input
                type="number"
                min="1"
                max="10080"
                value={rules.pix_receipt_max_age_minutes}
                onChange={(event) =>
                  setRules({
                    ...rules,
                    pix_receipt_max_age_minutes: Number(event.target.value),
                  })
                }
              />
            </label>

            <label className="miniValue">
              <span>Tolerância de valor (R$)</span>
              <input
                type="number"
                step="0.01"
                min="0"
                max="100"
                value={rules.pix_amount_tolerance}
                onChange={(event) =>
                  setRules({
                    ...rules,
                    pix_amount_tolerance: Number(event.target.value),
                  })
                }
              />
            </label>
          </div>
        </>
      )}

      <h3 style={{ marginTop: 28 }}>Pedidos agendados</h3>

      <p className="muted" style={{ marginBottom: 14 }}>
        Defina como a empresa aceita pedidos programados para outro horário.
      </p>

      <div className="miniGrid">
        <label className="miniValue">
          <span>Aceitar pedidos agendados</span>
          <input
            type="checkbox"
            checked={rules.allow_scheduled_orders}
            onChange={(event) =>
              setRules({
                ...rules,
                allow_scheduled_orders: event.target.checked,
              })
            }
          />
        </label>

        <label className="miniValue">
          <span>Aceitar agendamento com a loja fechada</span>
          <input
            type="checkbox"
            disabled={!rules.allow_scheduled_orders}
            checked={rules.allow_scheduled_when_closed}
            onChange={(event) =>
              setRules({
                ...rules,
                allow_scheduled_when_closed: event.target.checked,
              })
            }
          />
        </label>

        <label className="miniValue">
          <span>Antecedência mínima (min)</span>
          <input
            type="number"
            min="0"
            max="10080"
            disabled={!rules.allow_scheduled_orders}
            value={rules.scheduled_min_notice_minutes ?? ""}
            onChange={(event) =>
              setRules({
                ...rules,
                scheduled_min_notice_minutes: event.target.value
                  ? Number(event.target.value)
                  : null,
              })
            }
            placeholder="Usar tempo de preparo"
          />
        </label>

        <label className="miniValue">
          <span>Máximo de dias para agendar</span>
          <input
            type="number"
            min="0"
            max="365"
            disabled={!rules.allow_scheduled_orders}
            value={rules.scheduled_max_days_ahead ?? ""}
            onChange={(event) =>
              setRules({
                ...rules,
                scheduled_max_days_ahead: event.target.value
                  ? Number(event.target.value)
                  : null,
              })
            }
            placeholder="Sem limite"
          />
        </label>
      </div>

      <p className="muted" style={{ marginTop: 10 }}>
        O horário escolhido continua sujeito ao funcionamento da loja,
        modalidade de entrega ou retirada e tempo médio de preparo.
      </p>

      <h3 style={{ marginTop: 28 }}>Horário de funcionamento</h3>

      <div style={{ overflowX: "auto" }}>
        <table
          style={{
            width: "100%",
            borderCollapse: "collapse",
            minWidth: 760,
          }}
        >
          <thead>
            <tr>
              <th align="left">Dia</th>
              <th>Fechado</th>
              <th>Abertura</th>
              <th>Fechamento</th>
              <th>Entrega até</th>
              <th>Retirada até</th>
              <th />
            </tr>
          </thead>

          <tbody>
            {DAYS.map((day, weekday) => {
              const saved = hourMap.get(weekday);

              return (
                <HourRow
                  key={weekday}
                  weekday={weekday}
                  day={day}
                  saved={saved}
                  disabled={saving}
                  onSave={saveHour}
                />
              );
            })}
          </tbody>
        </table>
      </div>

      <h3 style={{ marginTop: 28 }}>Observações para a Olívia</h3>

      <textarea
        style={{
          width: "100%",
          minHeight: 100,
          padding: 12,
          resize: "vertical",
        }}
        value={rules.general_notes ?? ""}
        onChange={(event) =>
          setRules({
            ...rules,
            general_notes: event.target.value || null,
          })
        }
        placeholder="Ex.: em dias de evento o tempo de preparo pode aumentar."
      />

      <div
        style={{
          marginTop: 22,
          display: "flex",
          alignItems: "center",
          gap: 14,
        }}
      >
        <button
          className="refreshButton"
          type="button"
          disabled={saving}
          onClick={() => void saveRules()}
          style={{ background: "#244c36", color: "white" }}
        >
          {saving ? "Salvando..." : "Salvar regras comerciais"}
        </button>

        {message && <span className="muted">{message}</span>}
      </div>

      <div
        style={{
          marginTop: 28,
          padding: 18,
          border: "1px dashed #cbd2ca",
          borderRadius: 12,
        }}
      >
        <strong>Cardápio PDF</strong>
        <p className="muted" style={{ marginTop: 5 }}>
          Upload e envio automático pelo WhatsApp serão ligados na próxima etapa.
        </p>
      </div>
    </section>
  );
}

function HourRow({
  weekday,
  day,
  saved,
  disabled,
  onSave,
}: {
  weekday: number;
  day: string;
  saved?: BusinessHour;
  disabled: boolean;
  onSave: (
    weekday: number,
    payload: Omit<BusinessHour, "weekday">,
  ) => Promise<void>;
}) {
  const [closed, setClosed] = useState(saved?.closed ?? false);
  const [openTime, setOpenTime] = useState(timeValue(saved?.open_time ?? null));
  const [closeTime, setCloseTime] = useState(
    timeValue(saved?.close_time ?? null),
  );
  const [deliveryUntil, setDeliveryUntil] = useState(
    timeValue(saved?.delivery_until ?? null),
  );
  const [takeoutUntil, setTakeoutUntil] = useState(
    timeValue(saved?.takeout_until ?? null),
  );

  return (
    <tr style={{ borderTop: "1px solid #e4e7e1" }}>
      <td style={{ padding: "12px 4px" }}>
        <strong>{day}</strong>
      </td>

      <td align="center">
        <input
          type="checkbox"
          checked={closed}
          onChange={(event) => setClosed(event.target.checked)}
        />
      </td>

      {[openTime, closeTime, deliveryUntil, takeoutUntil].map(
        (value, index) => (
          <td key={index} style={{ padding: 4 }}>
            <input
              type="time"
              disabled={closed}
              value={value}
              onChange={(event) => {
                const setters = [
                  setOpenTime,
                  setCloseTime,
                  setDeliveryUntil,
                  setTakeoutUntil,
                ];
                setters[index](event.target.value);
              }}
            />
          </td>
        ),
      )}

      <td>
        <button
          className="refreshButton"
          type="button"
          disabled={disabled}
          onClick={() =>
            void onSave(weekday, {
              closed,
              open_time: closed || !openTime ? null : openTime,
              close_time: closed || !closeTime ? null : closeTime,
              delivery_until:
                closed || !deliveryUntil ? null : deliveryUntil,
              takeout_until:
                closed || !takeoutUntil ? null : takeoutUntil,
            })
          }
        >
          Salvar
        </button>
      </td>
    </tr>
  );
}
