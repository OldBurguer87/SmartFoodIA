"use client";

import {
  CustomerAddress,
  CustomerDetail,
  ConversationMessage,
  HumanOrderCart,
  HumanOrderCatalogProduct,
  HumanOrderPaymentMethod,
  HumanOrderServiceMode,
  addHumanOrderItem,
  checkoutHumanOrder,
  cancelHumanPendingOrder,
  confirmHumanPix,
  createHumanOrderCart,
  createHumanCustomerAddress,
  getCustomerDetail,
  getConversationMessageMediaBlob,
  listHumanOrderProducts,
  removeHumanOrderItem,
  updateHumanOrderItem,
  updateHumanCustomerAddress,
} from "@/lib/api";
import {
  useEffect,
  useState,
} from "react";

type ConversationOrderPanelProps = {
  storeId: string;
  conversationId: string;
  messages: ConversationMessage[];
  assignedTo: string;
  customerId: string;
  customerName: string;
  onClose: () => void;
};

export function ConversationOrderPanel({
  storeId,
  conversationId,
  messages,
  assignedTo,
  customerId,
  customerName,
  onClose,
}: ConversationOrderPanelProps) {
  const [serviceMode, setServiceMode] =
    useState<HumanOrderServiceMode>("DELIVERY");

  const [customer, setCustomer] =
    useState<CustomerDetail | null>(null);

  const [products, setProducts] =
    useState<HumanOrderCatalogProduct[]>([]);

  const [productSearch, setProductSearch] =
    useState("");

  const [selectedProduct, setSelectedProduct] =
    useState<HumanOrderCatalogProduct | null>(null);

  const [productQuantity, setProductQuantity] =
    useState(1);

  const [productObservation, setProductObservation] =
    useState("");

  const [modifierQuantities, setModifierQuantities] =
    useState<Record<string, number>>({});

  const [cart, setCart] =
    useState<HumanOrderCart | null>(null);
  const [reusedCart, setReusedCart] =
    useState(false);

  const [selectedAddressId, setSelectedAddressId] =
    useState("");

  const [paymentMethod, setPaymentMethod] =
    useState<HumanOrderPaymentMethod>("PIX");

  const [changeFor, setChangeFor] =
    useState("");

  const [cartBusy, setCartBusy] =
    useState(false);

  const [pixBusyMessageId, setPixBusyMessageId] =
    useState<string | null>(null);
  const [pixConfirmed, setPixConfirmed] =
    useState(false);
  const [checkoutBusy, setCheckoutBusy] =
    useState(false);
  const [addressBusy, setAddressBusy] =
    useState(false);
  const [cancelBusy, setCancelBusy] =
    useState(false);

  const [completedOrder, setCompletedOrder] =
    useState<{
      id: string;
      display_id: string;
      total: number | string;
      status: string;
      payment_method: HumanOrderPaymentMethod;
    } | null>(null);

  const [catalogLoading, setCatalogLoading] =
    useState(false);

  const [loading, setLoading] =
    useState(true);

  const [error, setError] =
    useState<string | null>(null);

  useEffect(() => {
    let active = true;

    async function loadCustomer() {
      setLoading(true);
      setError(null);

      try {
        const detail = await getCustomerDetail(
          storeId,
          customerId,
        );

        if (active) {
          setCustomer(detail);

          const pendingPixOrders = detail.orders.filter(
            (order) =>
              order.payment_method === "PIX" &&
              order.status === "READY_FOR_INTEGRATION" &&
              !order.pix_confirmed,
          );

          if (pendingPixOrders.length > 0) {
            const pending = pendingPixOrders[0];

            setCompletedOrder({
              id: pending.id,
              display_id: pending.display_id,
              total: pending.total,
              status: pending.status,
              payment_method: "PIX",
            });
            setPaymentMethod("PIX");
            setPixConfirmed(false);

            if (
              pending.service_mode === "DELIVERY" ||
              pending.service_mode === "TAKEOUT"
            ) {
              setServiceMode(pending.service_mode);
            }

            if (pendingPixOrders.length > 1) {
              setError(
                `Existem ${pendingPixOrders.length} pedidos PIX pendentes para este cliente. Foi recuperado o mais recente (#${pending.display_id}). Não crie outro pedido antes de resolver os anteriores.`,
              );
            }
          }

          const defaultAddress =
            detail.addresses.find(
              (address) =>
                address.active &&
                address.is_default,
            ) ??
            detail.addresses.find(
              (address) => address.active,
            );

          setSelectedAddressId(
            defaultAddress?.id ?? "",
          );
        }
      } catch (err) {
        if (active) {
          setError(
            err instanceof Error
              ? err.message
              : "Não foi possível carregar o cliente.",
          );
        }
      } finally {
        if (active) {
          setLoading(false);
        }
      }
    }

    void loadCustomer();

    return () => {
      active = false;
    };
  }, [storeId, customerId]);

  useEffect(() => {
    let active = true;
    async function loadExistingCart() {
      try {
        const existing = await createHumanOrderCart(
          storeId,
          customerId,
          "DELIVERY",
        );
        if (!active) return;
        if (existing.items.length > 0) {
          setCart(existing);
          setServiceMode(existing.service_mode);
          setReusedCart(true);
        }
      } catch (err) {
        if (active) {
          setError(
            err instanceof Error
              ? err.message
              : "Não foi possível verificar o carrinho em aberto.",
          );
        }
      }
    }
    void loadExistingCart();
    return () => {
      active = false;
    };
  }, [storeId, customerId]);

  useEffect(() => {
    let active = true;

    async function loadCatalog() {
      setCatalogLoading(true);

      try {
        const catalog = await listHumanOrderProducts(
          storeId,
          serviceMode,
        );

        if (active) {
          setProducts(catalog);
        }
      } catch (err) {
        if (active) {
          setProducts([]);
          setError(
            err instanceof Error
              ? err.message
              : "Não foi possível carregar o cardápio.",
          );
        }
      } finally {
        if (active) {
          setCatalogLoading(false);
        }
      }
    }

    void loadCatalog();

    return () => {
      active = false;
    };
  }, [storeId, serviceMode]);

  function openProduct(
    product: HumanOrderCatalogProduct,
  ) {
    const defaults: Record<string, number> = {};

    for (const group of product.modifier_groups) {
      for (const modifier of group.modifiers) {
        defaults[modifier.external_code] =
          modifier.default_quantity ?? 0;
      }
    }

    setSelectedProduct(product);
    setProductQuantity(1);
    setProductObservation("");
    setModifierQuantities(defaults);
  }

  function changeModifier(
    externalCode: string,
    next: number,
    maximum: number,
  ) {
    setModifierQuantities((current) => ({
      ...current,
      [externalCode]: Math.max(
        0,
        Math.min(maximum, next),
      ),
    }));
  }

  async function addSelectedProduct() {
    if (
      !selectedProduct ||
      cartBusy ||
      completedOrder
    ) return;

    setCartBusy(true);
    setError(null);

    try {
      const activeCart =
        cart ??
        (await createHumanOrderCart(
          storeId,
          customerId,
          serviceMode,
        ));

      const modifiers =
        selectedProduct.modifier_groups.flatMap(
          (group) =>
            group.modifiers
              .map((modifier) => ({
                external_code:
                  modifier.external_code,
                quantity:
                  modifierQuantities[
                    modifier.external_code
                  ] ?? 0,
              }))
              .filter(
                (modifier) =>
                  modifier.quantity > 0,
              ),
        );

      const updated =
        await addHumanOrderItem(
          activeCart.id,
          {
            product_external_code:
              selectedProduct.external_code,
            quantity: productQuantity,
            observations:
              productObservation.trim() || null,
            modifiers,
          },
        );

      setCart(updated);
      setSelectedProduct(null);
      setProductQuantity(1);
      setProductObservation("");
      setModifierQuantities({});
    } catch (err) {
      setError(
        err instanceof Error
          ? err.message
          : "Não foi possível adicionar o produto.",
      );
    } finally {
      setCartBusy(false);
    }
  }

  async function changeCartItemQuantity(
    itemId: string,
    quantity: number,
    observations?: string | null,
  ) {
    if (!cart || cartBusy) return;

    setCartBusy(true);
    setError(null);

    try {
      const updated =
        await updateHumanOrderItem(
          cart.id,
          itemId,
          {
            quantity: Math.max(
              1,
              Math.min(99, quantity),
            ),
            observations: observations ?? null,
          },
        );

      setCart(updated);
    } catch (err) {
      setError(
        err instanceof Error
          ? err.message
          : "Não foi possível alterar o item.",
      );
    } finally {
      setCartBusy(false);
    }
  }

  async function removeCartItem(
    itemId: string,
  ) {
    if (!cart || cartBusy) return;

    setCartBusy(true);
    setError(null);

    try {
      const updated =
        await removeHumanOrderItem(
          cart.id,
          itemId,
        );

      setCart(updated);
    } catch (err) {
      setError(
        err instanceof Error
          ? err.message
          : "Não foi possível remover o item.",
      );
    } finally {
      setCartBusy(false);
    }
  }

  function askHumanAddress(
    existing?: CustomerAddress,
  ) {
    const label = window.prompt(
      "Nome do endereço (Casa, Trabalho, Principal):",
      existing?.label ?? "Principal",
    );
    if (label === null) return null;

    const street = window.prompt(
      "Rua / Avenida:",
      existing?.street ?? "",
    );
    if (street === null) return null;

    const number = window.prompt(
      "Número:",
      existing?.number ?? "",
    );
    if (number === null) return null;

    const neighborhood = window.prompt(
      "Bairro:",
      existing?.neighborhood ?? "",
    );
    if (neighborhood === null) return null;

    const complement = window.prompt(
      "Complemento (opcional):",
      existing?.complement ?? "",
    );
    if (complement === null) return null;

    const reference = window.prompt(
      "Ponto de referência (opcional):",
      existing?.reference ?? "",
    );
    if (reference === null) return null;

    if (
      !label.trim() ||
      !street.trim() ||
      !number.trim() ||
      !neighborhood.trim()
    ) {
      setError(
        "Nome, rua, número e bairro são obrigatórios.",
      );
      return null;
    }

    return {
      label: label.trim(),
      street: street.trim(),
      number: number.trim(),
      neighborhood: neighborhood.trim(),
      city: existing?.city ?? "Coari",
      state: existing?.state ?? "AM",
      postal_code: existing?.postal_code ?? null,
      complement: complement.trim() || null,
      reference: reference.trim() || null,
      is_default:
        existing?.is_default ??
        ((customer?.addresses ?? []).filter(
          (address) => address.active,
        ).length === 0),
    };
  }

  async function addHumanAddress() {
    const payload = askHumanAddress();
    if (!payload) return;

    setAddressBusy(true);
    setError(null);

    try {
      const created = await createHumanCustomerAddress(
        conversationId,
        payload,
      );

      const detail = await getCustomerDetail(
        storeId,
        customerId,
      );

      setCustomer(detail);
      setSelectedAddressId(created.id);
    } catch (err) {
      setError(
        err instanceof Error
          ? err.message
          : "Não foi possível cadastrar o endereço.",
      );
    } finally {
      setAddressBusy(false);
    }
  }

  async function editHumanAddress() {
    const existing = customer?.addresses.find(
      (address) => address.id === selectedAddressId,
    );

    if (!existing) {
      setError("Selecione um endereço para editar.");
      return;
    }

    const payload = askHumanAddress(existing);
    if (!payload) return;

    setAddressBusy(true);
    setError(null);

    try {
      await updateHumanCustomerAddress(
        conversationId,
        existing.id,
        payload,
      );

      const detail = await getCustomerDetail(
        storeId,
        customerId,
      );

      setCustomer(detail);
      setSelectedAddressId(existing.id);
    } catch (err) {
      setError(
        err instanceof Error
          ? err.message
          : "Não foi possível editar o endereço.",
      );
    } finally {
      setAddressBusy(false);
    }
  }

  async function cancelPendingHumanOrder() {
    if (!completedOrder) return;

    if (
      !window.confirm(
        `Cancelar o pedido #${completedOrder.display_id}?`,
      )
    ) {
      return;
    }

    setCancelBusy(true);
    setError(null);

    try {
      await cancelHumanPendingOrder(
        conversationId,
        completedOrder.id,
      );

      setCompletedOrder(null);
      setPixConfirmed(false);

      const detail = await getCustomerDetail(
        storeId,
        customerId,
      );

      setCustomer(detail);

      const defaultAddress =
        detail.addresses.find(
          (address) =>
            address.active && address.is_default,
        ) ??
        detail.addresses.find(
          (address) => address.active,
        );

      setSelectedAddressId(defaultAddress?.id ?? "");
    } catch (err) {
      setError(
        err instanceof Error
          ? err.message
          : "Não foi possível cancelar o pedido.",
      );
    } finally {
      setCancelBusy(false);
    }
  }

  const checkoutBlocked =
    !cart ||
    cart.items.length === 0 ||
    checkoutBusy ||
    (
      serviceMode === "DELIVERY" &&
      !selectedAddressId
    );

  async function confirmHumanOrder() {
    if (!cart || checkoutBlocked) return;

    const parsedChange =
      paymentMethod === "CASH" &&
      changeFor.trim()
        ? Number(
            changeFor
              .trim()
              .replace(",", "."),
          )
        : null;

    if (
      parsedChange !== null &&
      (
        !Number.isFinite(parsedChange) ||
        parsedChange < 0
      )
    ) {
      setError("Informe um valor válido para o troco.");
      return;
    }

    const confirmed = window.confirm(
      "Confirmar este pedido? Após a confirmação ele será criado na SmartFoodIA e seguirá o fluxo de integração configurado.",
    );

    if (!confirmed) return;

    setCheckoutBusy(true);
    setError(null);

    try {
      const order = await checkoutHumanOrder(
        cart.id,
        {
          address_id:
            serviceMode === "DELIVERY"
              ? selectedAddressId
              : null,
          payment_method: paymentMethod,
          change_for: parsedChange,
          discount: 0,
        },
      );

      setCompletedOrder({
        id: String(order.id),
        display_id: String(order.display_id),
        total: order.total,
        status: String(order.status),
        payment_method: paymentMethod,
      });

      setCart(null);
      setSelectedProduct(null);
    } catch (err) {
      setError(
        err instanceof Error
          ? err.message
          : "Não foi possível confirmar o pedido.",
      );
    } finally {
      setCheckoutBusy(false);
    }
  }

  const supportedPixMimes = new Set([
    "application/pdf",
    "image/jpeg",
    "image/png",
  ]);

  const pixReceiptMessages = messages
    .filter((message) => {
      const metadata = message.metadata_json;
      if (!metadata || metadata.stored_media !== true) {
        return false;
      }
      const mimeType =
        typeof metadata.mime_type === "string"
          ? metadata.mime_type.toLowerCase()
          : "";
      return (
        message.direction === "INBOUND" &&
        message.sender_type === "CUSTOMER" &&
        ["IMAGE", "DOCUMENT"].includes(
          message.content_type.toUpperCase(),
        ) &&
        supportedPixMimes.has(mimeType)
      );
    })
    .slice()
    .sort(
      (a, b) =>
        new Date(b.created_at).getTime() -
        new Date(a.created_at).getTime(),
    );

  async function openPixReceipt(
    messageId: string,
  ) {
    setError(null);

    const previewWindow = window.open(
      "about:blank",
      "_blank",
    );

    if (!previewWindow) {
      setError(
        "O navegador bloqueou a abertura do comprovante. Permita pop-ups para este site.",
      );
      return;
    }

    previewWindow.opener = null;

    try {
      previewWindow.document.title = "Comprovante PIX";
      previewWindow.document.body.innerText =
        "Carregando comprovante...";

      const blob =
        await getConversationMessageMediaBlob(
          conversationId,
          messageId,
        );

      const objectUrl = URL.createObjectURL(blob);
      previewWindow.location.href = objectUrl;

      window.setTimeout(
        () => URL.revokeObjectURL(objectUrl),
        60000,
      );
    } catch (err) {
      previewWindow.close();
      setError(
        err instanceof Error
          ? err.message
          : "Não foi possível abrir o comprovante.",
      );
    }
  }

  async function confirmPixReceipt(
    messageId: string,
  ) {
    if (
      !completedOrder ||
      completedOrder.payment_method !== "PIX" ||
      pixConfirmed ||
      pixBusyMessageId ||
      !assignedTo.trim()
    ) {
      return;
    }

    const confirmed = window.confirm(
      `Confirmar este arquivo como comprovante PIX do pedido #${completedOrder.display_id}?`,
    );
    if (!confirmed) return;

    setPixBusyMessageId(messageId);
    setError(null);
    try {
      await confirmHumanPix(
        conversationId,
        completedOrder.id,
        messageId,
        assignedTo.trim(),
      );
      setPixConfirmed(true);
    } catch (err) {
      setError(
        err instanceof Error
          ? err.message
          : "Não foi possível confirmar o PIX.",
      );
    } finally {
      setPixBusyMessageId(null);
    }
  }

  const normalizedSearch =
    productSearch.trim().toLowerCase();

  const visibleProducts = products.filter(
    (product) => {
      if (!normalizedSearch) return true;

      return [
        product.name,
        product.category ?? "",
        product.external_code,
      ]
        .join(" ")
        .toLowerCase()
        .includes(normalizedSearch);
    },
  );

  return (
    <section className="conversationOrderPanel">
      <header>
        <div>
          <small>PEDIDO DO CLIENTE</small>
          <strong>{customerName}</strong>
        </div>

        <button
          type="button"
          onClick={onClose}
        >
          Fechar
        </button>
      </header>

      <div className="orderServiceMode">
        <button
          type="button"
          className={
            serviceMode === "DELIVERY"
              ? "active"
              : ""
          }
          onClick={() =>
            setServiceMode("DELIVERY")
          }
          disabled={
            Boolean(cart?.items.length) &&
            serviceMode !== "DELIVERY"
          }
        >
          Entrega
        </button>

        <button
          type="button"
          className={
            serviceMode === "TAKEOUT"
              ? "active"
              : ""
          }
          onClick={() =>
            setServiceMode("TAKEOUT")
          }
          disabled={
            Boolean(cart?.items.length) &&
            serviceMode !== "TAKEOUT"
          }
        >
          Retirada
        </button>
      </div>

      {reusedCart && cart?.items.length ? (
        <div className="humanOrderWarning">
          Este cliente já tinha um carrinho em aberto.
          Confira os itens abaixo antes de continuar.
        </div>
      ) : null}
      {loading && (
        <p>Carregando cliente...</p>
      )}

      {error && (
        <div className="consoleError">
          {error}
        </div>
      )}

      {completedOrder && (
        <section className="humanOrderSuccess">
          <strong>
            Pedido #{completedOrder.display_id} criado
          </strong>

          <span>
            Total:{" "}
            {Number(
              completedOrder.total,
            ).toLocaleString(
              "pt-BR",
              {
                style: "currency",
                currency: "BRL",
              },
            )}
          </span>

          <small>
            {completedOrder.payment_method === "PIX"
              ? pixConfirmed
                ? "Pagamento PIX confirmado. Pedido liberado para integração."
                : "Pedido criado. Aguardando confirmação do comprovante PIX antes da integração."
              : "O pedido entrou no fluxo de integração configurado da SmartFoodIA."}
          </small>

            {completedOrder.status === "READY_FOR_INTEGRATION" && (
              <button
                type="button"
                disabled={cancelBusy}
                onClick={() =>
                  void cancelPendingHumanOrder()
                }
                style={{ marginTop: "10px" }}
              >
                {cancelBusy
                  ? "Cancelando..."
                  : "Cancelar pedido"}
              </button>
            )}
        </section>
      )}

      {completedOrder?.payment_method === "PIX" && (
        <section className="humanOrderPixReceipts">
          <header>
            <div>
              <small>PAGAMENTO PIX</small>
              <strong>Comprovantes recebidos</strong>
            </div>
          </header>

          {pixConfirmed ? (
            <div className="humanOrderPixConfirmed">
              <strong>PIX confirmado</strong>
              <span>
                O comprovante foi vinculado ao pedido e o
                pedido está liberado para o fluxo de integração.
              </span>
            </div>
          ) : pixReceiptMessages.length === 0 ? (
            <div className="humanOrderPixWaiting">
              <strong>Aguardando comprovante</strong>
              <span>
                Quando o cliente enviar uma imagem ou PDF do
                comprovante, ele aparecerá aqui automaticamente.
              </span>
            </div>
          ) : (
            <div className="humanOrderPixReceiptList">
              {pixReceiptMessages.slice(0, 8).map((message) => {
                const metadata = message.metadata_json ?? {};
                const filename =
                  typeof metadata.filename === "string"
                    ? metadata.filename
                    : message.content_type.toUpperCase() === "IMAGE"
                      ? "Imagem recebida"
                      : "Documento recebido";

                return (
                  <div
                    className="humanOrderPixReceipt"
                    key={message.id}
                  >
                    <div>
                      <strong>{filename}</strong>
                      <span>
                        Recebido às{" "}
                        {new Date(
                          message.created_at,
                        ).toLocaleTimeString(
                          "pt-BR",
                          {
                            hour: "2-digit",
                            minute: "2-digit",
                          },
                        )}
                      </span>
                    </div>

                    <div>
                      <button
                        type="button"
                        onClick={() =>
                          void openPixReceipt(message.id)
                        }
                      >
                        Ver comprovante
                      </button>

                      <button
                        type="button"
                        disabled={
                          Boolean(pixBusyMessageId) ||
                          !assignedTo.trim()
                        }
                        onClick={() =>
                          void confirmPixReceipt(message.id)
                        }
                      >
                        {pixBusyMessageId === message.id
                          ? "Confirmando..."
                          : "Confirmar este PIX"}
                      </button>
                    </div>
                  </div>
                );
              })}
            </div>
          )}

          {!assignedTo.trim() && !pixConfirmed && (
            <small className="humanOrderCheckoutHint">
              Informe o nome da atendente para confirmar o PIX.
            </small>
          )}
        </section>
      )}
      <div className="orderCatalogSummary">
        {catalogLoading ? (
          <span>Carregando cardápio...</span>
        ) : (
          <span>
            {products.length} produto
            {products.length === 1 ? "" : "s"}
            {" "}
            disponível
            {products.length === 1 ? "" : "is"}
          </span>
        )}
      </div>

      <div className="orderProductSearch">
        <input
          type="search"
          value={productSearch}
          onChange={(event) =>
            setProductSearch(event.target.value)
          }
          placeholder="Buscar produto..."
        />
      </div>

      <div className="orderProductList">
        {!catalogLoading &&
          visibleProducts.slice(0, 40).map(
            (product) => (
              <button
                type="button"
                className="orderProductCard"
                key={product.id}
                onClick={() => openProduct(product)}
              >
                <div>
                  <strong>{product.name}</strong>

                  <span>
                    {product.category ??
                      "Sem categoria"}
                  </span>
                </div>

                <strong>
                  {Number(product.price).toLocaleString(
                    "pt-BR",
                    {
                      style: "currency",
                      currency: "BRL",
                    },
                  )}
                </strong>
              </button>
            ),
          )}

        {!catalogLoading &&
          visibleProducts.length === 0 && (
            <p>Nenhum produto encontrado.</p>
          )}
      </div>

      {cart && cart.items.length > 0 && (
        <section className="humanOrderCartSummary">
          <header>
            <div>
              <small>PEDIDO ATUAL</small>
              <strong>
                {cart.items.length} item
                {cart.items.length === 1 ? "" : "s"}
              </strong>
            </div>

            <strong>
              {Number(cart.subtotal).toLocaleString(
                "pt-BR",
                {
                  style: "currency",
                  currency: "BRL",
                },
              )}
            </strong>
          </header>

          <div className="humanOrderCartItems">
            {cart.items.map((item) => (
              <div
                className="humanOrderCartItem"
                key={item.id}
              >
                <div className="humanOrderCartItemTop">
                  <strong>
                    {item.quantity}x{" "}
                    {item.product_name}
                  </strong>

                  <strong>
                    {Number(item.total).toLocaleString(
                      "pt-BR",
                      {
                        style: "currency",
                        currency: "BRL",
                      },
                    )}
                  </strong>
                </div>

                {item.modifiers.length > 0 && (
                  <div className="humanOrderCartModifiers">
                    {item.modifiers.map(
                      (modifier) => (
                        <span key={modifier.id}>
                          + {modifier.quantity}x{" "}
                          {modifier.name}
                        </span>
                      ),
                    )}
                  </div>
                )}

                {item.observations && (
                  <small>
                    Obs.: {item.observations}
                  </small>
                )}

                <div className="humanOrderCartItemActions">
                  <div className="humanOrderCartQuantity">
                    <button
                      type="button"
                      disabled={
                        cartBusy ||
                        item.quantity <= 1
                      }
                      onClick={() =>
                        void changeCartItemQuantity(
                          item.id,
                          item.quantity - 1,
                          item.observations,
                        )
                      }
                    >
                      −
                    </button>

                    <strong>
                      {item.quantity}
                    </strong>

                    <button
                      type="button"
                      disabled={
                        cartBusy ||
                        item.quantity >= 99
                      }
                      onClick={() =>
                        void changeCartItemQuantity(
                          item.id,
                          item.quantity + 1,
                          item.observations,
                        )
                      }
                    >
                      +
                    </button>
                  </div>

                  <button
                    type="button"
                    className="humanOrderRemoveItem"
                    disabled={cartBusy}
                    onClick={() =>
                      void removeCartItem(item.id)
                    }
                  >
                    Remover
                  </button>
                </div>
              </div>
            ))}
          </div>

          <div className="humanOrderCartTotal">
            <span>Subtotal</span>

            <strong>
              {Number(cart.subtotal).toLocaleString(
                "pt-BR",
                {
                  style: "currency",
                  currency: "BRL",
                },
              )}
            </strong>
          </div>
        </section>
      )}

      {cart && cart.items.length > 0 && (
        <section className="humanOrderCheckout">
          <header>
            <div>
              <small>FINALIZAÇÃO</small>
              <strong>Entrega e pagamento</strong>
            </div>
          </header>

          {serviceMode === "DELIVERY" ? (
            <label className="humanOrderField">
              Endereço de entrega

              <select
                value={selectedAddressId}
                onChange={(event) =>
                  setSelectedAddressId(
                    event.target.value,
                  )
                }
              >
                <option value="">
                  Selecione o endereço
                </option>

                {customer?.addresses
                  .filter(
                    (address) => address.active,
                  )
                  .map((address) => (
                    <option
                      key={address.id}
                      value={address.id}
                    >
                      {address.street},{" "}
                      {address.number} -{" "}
                      {address.neighborhood}
                    </option>
                  ))}
              </select>

                <div
                  style={{
                    display: "flex",
                    gap: "8px",
                    marginTop: "8px",
                    flexWrap: "wrap",
                  }}
                >
                  <button
                    type="button"
                    disabled={addressBusy}
                    onClick={() => void addHumanAddress()}
                  >
                    + Novo endereço
                  </button>

                  <button
                    type="button"
                    disabled={
                      addressBusy || !selectedAddressId
                    }
                    onClick={() => void editHumanAddress()}
                  >
                    Editar endereço selecionado
                  </button>
                </div>
            </label>
          ) : (
            <div className="humanOrderTakeout">
              <strong>Retirada no local</strong>
              <span>
                Não é necessário endereço de entrega.
              </span>
            </div>
          )}

          {serviceMode === "DELIVERY" &&
            customer &&
            customer.addresses.filter(
              (address) => address.active,
            ).length === 0 && (
              <div className="humanOrderWarning">
                Cliente sem endereço cadastrado.
              </div>
            )}

          <div className="humanOrderPayment">
            <span>Forma de pagamento</span>

            <div className="humanOrderPaymentOptions">
              {(
                [
                  ["PIX", "PIX"],
                  ["CREDIT", "Crédito"],
                  ["DEBIT", "Débito"],
                  ["CASH", "Dinheiro"],
                ] as const
              ).map(([value, label]) => (
                <button
                  key={value}
                  type="button"
                  className={
                    paymentMethod === value
                      ? "active"
                      : ""
                  }
                  onClick={() =>
                    setPaymentMethod(value)
                  }
                >
                  {label}
                </button>
              ))}
            </div>
          </div>

          {paymentMethod === "CASH" && (
            <label className="humanOrderField">
              Troco para quanto?

              <input
                type="number"
                inputMode="decimal"
                min="0"
                step="0.01"
                value={changeFor}
                onChange={(event) =>
                  setChangeFor(event.target.value)
                }
                placeholder="Ex.: 100,00"
              />
            </label>
          )}

          {paymentMethod === "PIX" && (
            <div className="humanOrderPixNotice">
              <strong>Pagamento via PIX</strong>
              <span>
                O pedido só será liberado para integração
                após a confirmação do comprovante.
              </span>
            </div>
          )}

          <div className="humanOrderCheckoutSummary">
            <div>
              <span>Produtos</span>

              <strong>
                {Number(cart.subtotal).toLocaleString(
                  "pt-BR",
                  {
                    style: "currency",
                    currency: "BRL",
                  },
                )}
              </strong>
            </div>

            {serviceMode === "DELIVERY" && (
              <small>
                A taxa de entrega e o total final serão
                calculados pela SmartFoodIA ao confirmar.
              </small>
            )}

            {serviceMode === "TAKEOUT" && (
              <small>
                Retirada no local: sem taxa de entrega.
              </small>
            )}
          </div>

          <button
            type="button"
            className="humanOrderConfirmButton"
            disabled={checkoutBlocked}
            onClick={() =>
              void confirmHumanOrder()
            }
          >
            {checkoutBusy
              ? "Confirmando pedido..."
              : "Confirmar pedido"}
          </button>

          {serviceMode === "DELIVERY" &&
            !selectedAddressId && (
              <small className="humanOrderCheckoutHint">
                Selecione um endereço para continuar.
              </small>
            )}
        </section>
      )}

      {selectedProduct && (
        <div className="orderProductEditor">
          <div className="orderProductEditorHeader">
            <div>
              <small>ADICIONANDO</small>
              <strong>
                {selectedProduct.name}
              </strong>
            </div>

            <button
              type="button"
              onClick={() =>
                setSelectedProduct(null)
              }
            >
              Cancelar
            </button>
          </div>

          <label>
            Quantidade
            <input
              type="number"
              min="1"
              max="99"
              value={productQuantity}
              onChange={(event) =>
                setProductQuantity(
                  Math.max(
                    1,
                    Math.min(
                      99,
                      Number(event.target.value) || 1,
                    ),
                  ),
                )
              }
            />
          </label>

          {selectedProduct.modifier_groups.map(
            (group) => (
              <div
                className="orderModifierGroup"
                key={group.id}
              >
                <div>
                  <strong>{group.name}</strong>
                  <small>
                    Mín. {group.min_select}
                    {" • "}
                    Máx. {group.max_select}
                  </small>
                </div>

                {group.modifiers.map((modifier) => {
                  const quantity =
                    modifierQuantities[
                      modifier.external_code
                    ] ?? 0;

                  return (
                    <div
                      className="orderModifierRow"
                      key={modifier.id}
                    >
                      <div>
                        <span>{modifier.name}</span>
                        <small>
                          {Number(
                            modifier.price,
                          ).toLocaleString(
                            "pt-BR",
                            {
                              style: "currency",
                              currency: "BRL",
                            },
                          )}
                        </small>
                      </div>

                      <div className="orderModifierQuantity">
                        <button
                          type="button"
                          onClick={() =>
                            changeModifier(
                              modifier.external_code,
                              quantity - 1,
                              modifier.max_quantity,
                            )
                          }
                          disabled={quantity <= 0}
                        >
                          −
                        </button>

                        <strong>{quantity}</strong>

                        <button
                          type="button"
                          onClick={() =>
                            changeModifier(
                              modifier.external_code,
                              quantity + 1,
                              modifier.max_quantity,
                            )
                          }
                          disabled={
                            quantity >=
                            modifier.max_quantity
                          }
                        >
                          +
                        </button>
                      </div>
                    </div>
                  );
                })}
              </div>
            ),
          )}

          <label>
            Observação
            <textarea
              maxLength={500}
              value={productObservation}
              onChange={(event) =>
                setProductObservation(
                  event.target.value,
                )
              }
              placeholder="Ex.: sem cebola"
            />
          </label>

          <button
            type="button"
            className="addOrderItemButton"
            onClick={() =>
              void addSelectedProduct()
            }
            disabled={cartBusy || Boolean(completedOrder)}
          >
            {cartBusy
              ? "Adicionando..."
              : "Adicionar ao pedido"}
          </button>
        </div>
      )}

      {customer && (
        <div>
          <strong>
            {customer.addresses.length}
            {" "}
            endereço
            {customer.addresses.length === 1
              ? ""
              : "s"}
            {" "}
            cadastrado
            {customer.addresses.length === 1
              ? ""
              : "s"}
          </strong>
        </div>
      )}
    </section>
  );
}
