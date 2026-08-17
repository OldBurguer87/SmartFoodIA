"use client";

import {
  FormEvent,
  useEffect,
  useState,
} from "react";

import {
  CustomerDetail,
  CustomerSummary,
  getCustomerDetail,
  listCustomers,
} from "@/lib/api";


const currency = new Intl.NumberFormat("pt-BR", {
  style: "currency",
  currency: "BRL",
});


export function CustomerWalletPanel({
  storeId,
}: {
  storeId: string;
}) {
  const [customers, setCustomers] = useState<CustomerSummary[]>([]);
  const [total, setTotal] = useState(0);
  const [search, setSearch] = useState("");
  const [draftSearch, setDraftSearch] = useState("");
  const [selected, setSelected] = useState<CustomerDetail | null>(null);
  const [loading, setLoading] = useState(false);
  const [detailLoading, setDetailLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  async function loadCustomers(nextSearch = search) {
    setLoading(true);
    setError(null);

    try {
      const result = await listCustomers(
        storeId,
        nextSearch,
      );

      setCustomers(result.customers);
      setTotal(result.total);

      if (
        selected &&
        !result.customers.some(
          (customer) => customer.id === selected.id,
        )
      ) {
        setSelected(null);
      }
    } catch (requestError) {
      setError(
        requestError instanceof Error
          ? requestError.message
          : "Não foi possível carregar os clientes.",
      );
    } finally {
      setLoading(false);
    }
  }

  async function openCustomer(customerId: string) {
    setDetailLoading(true);
    setError(null);

    try {
      const result = await getCustomerDetail(
        storeId,
        customerId,
      );

      setSelected(result);
    } catch (requestError) {
      setError(
        requestError instanceof Error
          ? requestError.message
          : "Não foi possível abrir o cliente.",
      );
    } finally {
      setDetailLoading(false);
    }
  }

  useEffect(() => {
    setSearch("");
    setDraftSearch("");
    setSelected(null);
    void loadCustomers("");
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [storeId]);

  function submitSearch(event: FormEvent) {
    event.preventDefault();

    const normalized = draftSearch.trim();
    setSearch(normalized);
    setSelected(null);
    void loadCustomers(normalized);
  }

  return (
    <section
      className="customerWallet"
      id="clientes"
    >
      <div className="customerWalletHeader">
        <div>
          <p className="eyebrow">
            CARTEIRA DE CLIENTES
          </p>
          <h2>Clientes</h2>
          <p>
            Dados, endereços e histórico de pedidos
            desta loja.
          </p>
        </div>

        <strong className="customerWalletCount">
          {total} {total === 1 ? "cliente" : "clientes"}
        </strong>
      </div>

      <form
        className="customerSearch"
        onSubmit={submitSearch}
      >
        <input
          value={draftSearch}
          onChange={(event) =>
            setDraftSearch(event.target.value)
          }
          placeholder="Buscar por nome ou telefone"
          aria-label="Buscar clientes"
        />

        <button
          type="submit"
          disabled={loading}
        >
          {loading ? "Buscando..." : "Buscar"}
        </button>

        {search && (
          <button
            type="button"
            className="secondaryButton"
            onClick={() => {
              setSearch("");
              setDraftSearch("");
              setSelected(null);
              void loadCustomers("");
            }}
          >
            Limpar
          </button>
        )}
      </form>

      {error && (
        <div className="errorBox">
          <strong>Não foi possível carregar.</strong>
          <span>{error}</span>
        </div>
      )}

      <div className="customerWalletGrid">
        <div className="customerList">
          {customers.length ? (
            customers.map((customer) => (
              <button
                type="button"
                key={customer.id}
                className={
                  selected?.id === customer.id
                    ? "customerRow selected"
                    : "customerRow"
                }
                onClick={() =>
                  void openCustomer(customer.id)
                }
              >
                <div>
                  <strong>{customer.name}</strong>
                  <span>{formatPhone(customer.phone)}</span>
                </div>

                <small>
                  {customer.addresses_count}{" "}
                  {customer.addresses_count === 1
                    ? "endereço"
                    : "endereços"}
                </small>
              </button>
            ))
          ) : (
            <div className="customerEmpty">
              {loading
                ? "Carregando clientes..."
                : "Nenhum cliente encontrado."}
            </div>
          )}
        </div>

        <div className="customerDetail">
          {detailLoading ? (
            <div className="customerEmpty">
              Carregando ficha...
            </div>
          ) : selected ? (
            <>
              <header className="customerDetailHeader">
                <div>
                  <span>Cliente</span>
                  <h3>{selected.name}</h3>
                  <p>{formatPhone(selected.phone)}</p>
                </div>

                <span className="customerStatus">
                  Ativo
                </span>
              </header>

              <div className="customerSection">
                <h4>Endereços</h4>

                {selected.addresses.length ? (
                  <div className="addressList">
                    {selected.addresses.map(
                      (address) => (
                        <article
                          className="addressCard"
                          key={address.id}
                        >
                          <div>
                            <strong>
                              {address.label}
                            </strong>

                            {address.is_default && (
                              <span>
                                Principal
                              </span>
                            )}
                          </div>

                          <p>
                            {address.street},{" "}
                            {address.number}
                          </p>

                          <p>
                            {address.neighborhood} •{" "}
                            {address.city}/{address.state}
                          </p>

                          {address.complement && (
                            <small>
                              {address.complement}
                            </small>
                          )}

                          {address.reference && (
                            <small>
                              Referência:{" "}
                              {address.reference}
                            </small>
                          )}
                        </article>
                      ),
                    )}
                  </div>
                ) : (
                  <p className="muted">
                    Nenhum endereço salvo.
                  </p>
                )}
              </div>

              <div className="customerSection">
                <h4>
                  Últimos pedidos
                </h4>

                {selected.orders.length ? (
                  <div className="customerOrders">
                    {selected.orders.map(
                      (order) => (
                        <div
                          className="customerOrderRow"
                          key={order.id}
                        >
                          <div>
                            <strong>
                              #{order.display_id}
                            </strong>
                            <span>
                              {formatDate(
                                order.created_at,
                              )}
                            </span>
                          </div>

                          <div>
                            <strong>
                              {currency.format(
                                Number(order.total),
                              )}
                            </strong>
                            <span>
                              {formatOrderStatus(
                                order.status,
                              )}
                            </span>
                          </div>
                        </div>
                      ),
                    )}
                  </div>
                ) : (
                  <p className="muted">
                    Nenhum pedido registrado.
                  </p>
                )}
              </div>
            </>
          ) : (
            <div className="customerEmpty">
              Selecione um cliente para abrir a ficha.
            </div>
          )}
        </div>
      </div>
    </section>
  );
}


function formatPhone(phone: string) {
  const digits = phone.replace(/\D/g, "");

  if (
    digits.length === 13 &&
    digits.startsWith("55")
  ) {
    return `+55 (${digits.slice(2, 4)}) ${digits.slice(
      4,
      9,
    )}-${digits.slice(9)}`;
  }

  if (digits.length === 11) {
    return `(${digits.slice(0, 2)}) ${digits.slice(
      2,
      7,
    )}-${digits.slice(7)}`;
  }

  return phone;
}


function formatDate(value: string) {
  return new Date(value).toLocaleString(
    "pt-BR",
    {
      dateStyle: "short",
      timeStyle: "short",
    },
  );
}


function formatOrderStatus(status: string) {
  const labels: Record<string, string> = {
    PLACED: "Novo",
    READY_FOR_INTEGRATION: "Pronto para integração",
    CONFIRMED: "Confirmado",
    READY: "Pronto",
    DISPATCHED: "Saiu para entrega",
    CONCLUDED: "Finalizado",
    CANCELLED: "Cancelado",
  };

  return labels[status] ?? status.replaceAll("_", " ");
}
