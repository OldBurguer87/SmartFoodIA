"use client";

import {
  KeyboardEvent,
  useEffect,
  useMemo,
  useRef,
  useState,
} from "react";

import {
  ConversationDetail,
  ConversationMessage,
  ConversationSummary,
  CustomerSummary,
  StoreOperationMode,
  closeConversation,
  getConversation,
  getConversationMessageMediaBlob,
  getStoreOperationMode,
  listConversations,
  listCustomers,
  markConversationRead,
  releaseConversation,
  sendHumanMedia,
  sendHumanReply,
  takeOverConversation,
  updateStoreOperationMode,
} from "@/lib/api";
import { ConversationOrderPanel } from "@/components/conversation-order-panel";

type Filter =
  | "ACTIVE"
  | "WAITING"
  | "HUMAN"
  | "CLOSED"
  | "ALL";

function digits(value?: string | null) {
  return String(value ?? "").replace(/\D/g, "");
}

function formatPhone(value?: string | null) {
  const phone = digits(value);

  if (phone.length === 13 && phone.startsWith("55")) {
    return `+55 (${phone.slice(2, 4)}) ${phone.slice(4, 9)}-${phone.slice(9)}`;
  }

  if (phone.length === 12 && phone.startsWith("55")) {
    return `+55 (${phone.slice(2, 4)}) ${phone.slice(4, 8)}-${phone.slice(8)}`;
  }

  return value || "Telefone não informado";
}

function initials(name: string) {
  const parts = name.trim().split(/\s+/).filter(Boolean);

  if (!parts.length) return "CL";
  if (parts.length === 1) {
    return parts[0].slice(0, 2).toUpperCase();
  }

  return (
    parts[0][0] + parts[parts.length - 1][0]
  ).toUpperCase();
}

function statusLabel(status: ConversationSummary["status"]) {
  if (status === "WAITING_HUMAN") return "Aguardando";
  if (status === "HUMAN") return "Em atendimento";
  if (status === "CLOSED") return "Encerrada";
  return "Aberta";
}

function elapsed(value: string, now: number) {
  const time = new Date(value).getTime();
  if (!Number.isFinite(time)) return "";

  const minutes = Math.max(
    0,
    Math.floor((now - time) / 60000),
  );

  if (minutes < 1) return "agora";
  if (minutes < 60) return `${minutes} min`;

  const hours = Math.floor(minutes / 60);
  if (hours < 24) return `${hours} h`;

  return new Date(value).toLocaleDateString("pt-BR", {
    day: "2-digit",
    month: "2-digit",
  });
}

function author(message: ConversationMessage) {
  if (message.sender_type === "CUSTOMER") return "Cliente";
  if (message.sender_type === "HUMAN") return "Atendente";
  if (message.sender_type === "OLIVIA") return "Olívia";
  return "Sistema";
}

function MessageContent({
  conversationId,
  message,
}: {
  conversationId: string;
  message: ConversationMessage;
}) {
  const [url, setUrl] = useState<string | null>(null);
  const [failed, setFailed] = useState(false);

  const metadata =
    (message.metadata_json ?? {}) as Record<
      string,
      unknown
    >;

  const type = message.content_type.toUpperCase();
  const isImage = type === "IMAGE";
  const isDocument = type === "DOCUMENT";
  const stored = metadata.stored_media === true;

  const filename =
    typeof metadata.filename === "string" &&
    metadata.filename.trim()
      ? metadata.filename
      : isDocument
        ? "Documento recebido"
        : "Imagem recebida";

  useEffect(() => {
    if (!stored || (!isImage && !isDocument)) return;

    let active = true;
    let objectUrl: string | null = null;

    setFailed(false);
    setUrl(null);

    void getConversationMessageMediaBlob(
      conversationId,
      message.id,
    )
      .then((blob) => {
        if (!active) return;

        objectUrl = URL.createObjectURL(blob);
        setUrl(objectUrl);
      })
      .catch(() => {
        if (active) setFailed(true);
      });

    return () => {
      active = false;
      if (objectUrl) URL.revokeObjectURL(objectUrl);
    };
  }, [
    conversationId,
    message.id,
    stored,
    isImage,
    isDocument,
  ]);

  if (!isImage && !isDocument) {
    return <p>{message.content}</p>;
  }

  if (!stored) {
    return (
      <div className="conversationMediaUnavailable">
        <strong>{message.content}</strong>
        <span>
          Este arquivo não foi armazenado no painel.
        </span>
      </div>
    );
  }

  if (failed) {
    return (
      <div className="conversationMediaUnavailable">
        <strong>{message.content}</strong>
        <span>Não foi possível abrir este arquivo.</span>
      </div>
    );
  }

  if (!url) {
    return (
      <div className="conversationMediaLoading">
        Carregando mídia...
      </div>
    );
  }

  if (isImage) {
    return (
      <a
        className="conversationImageLink"
        href={url}
        target="_blank"
        rel="noreferrer"
      >
        <img
          className="conversationImage"
          src={url}
          alt={filename}
        />
        <span>Abrir imagem</span>
      </a>
    );
  }

  return (
    <a
      className="conversationDocument"
      href={url}
      target="_blank"
      rel="noreferrer"
    >
      <span className="conversationDocumentIcon">
        DOC
      </span>
      <span>
        <strong>{filename}</strong>
        <small>Abrir documento</small>
      </span>
    </a>
  );
}

export function ConversationsConsole({
  storeId,
}: {
  storeId: string;
}) {
  const [items, setItems] =
    useState<ConversationSummary[]>([]);

  const [customers, setCustomers] =
    useState<CustomerSummary[]>([]);

  const [selected, setSelected] =
    useState<ConversationDetail | null>(null);
  const [orderOpen, setOrderOpen] = useState(false);

  const [filter, setFilter] =
    useState<Filter>("ACTIVE");

  const [search, setSearch] = useState("");
  const [operator, setOperator] =
    useState("Atendente");

  const [reply, setReply] = useState("");
  const [attachment, setAttachment] =
    useState<File | null>(null);
  const [busy, setBusy] = useState(false);

  const [operationMode, setOperationMode] =
    useState<StoreOperationMode | null>(null);

  const [operationModeBusy, setOperationModeBusy] =
    useState(false);

  const [error, setError] =
    useState<string | null>(null);

  const [now, setNow] = useState(() => Date.now());

  const timelineEnd =
    useRef<HTMLDivElement | null>(null);
  const attachmentInput =
    useRef<HTMLInputElement | null>(null);

  const unreadSnapshot =
    useRef<Map<string, number>>(new Map());
  const listInitialized = useRef(false);
  const audioContext =
    useRef<AudioContext | null>(null);

  function playNewMessageSound() {
    const context = audioContext.current;

    if (!context || context.state !== "running") return;

    const start = context.currentTime;
    const oscillator = context.createOscillator();
    const gain = context.createGain();

    oscillator.type = "sine";
    oscillator.frequency.setValueAtTime(880, start);
    oscillator.frequency.exponentialRampToValueAtTime(
      660,
      start + 0.2,
    );

    gain.gain.setValueAtTime(0.0001, start);
    gain.gain.exponentialRampToValueAtTime(
      0.16,
      start + 0.015,
    );
    gain.gain.exponentialRampToValueAtTime(
      0.0001,
      start + 0.24,
    );

    oscillator.connect(gain);
    gain.connect(context.destination);
    oscillator.start(start);
    oscillator.stop(start + 0.25);
  }

  async function loadList(silent = false) {
    if (!storeId) return;

    try {
      const nextItems = await listConversations(storeId);

      const hasNewUnread =
        listInitialized.current &&
        nextItems.some(
          (item) =>
            (item.unread_count ?? 0) >
            (unreadSnapshot.current.get(item.id) ?? 0),
        );

      unreadSnapshot.current = new Map(
        nextItems.map((item) => [
          item.id,
          item.unread_count ?? 0,
        ]),
      );
      listInitialized.current = true;

      setItems(nextItems);

      if (hasNewUnread) {
        playNewMessageSound();
      }

      if (!silent) setError(null);
    } catch (err) {
      if (!silent) {
        setError(
          err instanceof Error
            ? err.message
            : "Erro ao carregar conversas.",
        );
      }
    }
  }

  async function loadCustomers() {
    if (!storeId) return;

    try {
      const response = await listCustomers(storeId);
      setCustomers(response.customers);
    } catch {
      // Falha de nomes não pode bloquear atendimento.
    }
  }

  async function loadOperationMode(
    silent = false,
  ) {
    if (!storeId) return;

    try {
      const mode = await getStoreOperationMode(storeId);
      setOperationMode(mode);

      if (!silent) setError(null);
    } catch (err) {
      if (!silent) {
        setError(
          err instanceof Error
            ? err.message
            : "Erro ao carregar o modo de atendimento.",
        );
      }
    }
  }

  async function toggleOperationMode() {
    if (
      !operationMode ||
      !operationMode.can_change ||
      operationModeBusy
    ) {
      return;
    }

    if (operationMode.server_forced_human) {
      setError(
        "O modo 100% humano está obrigatório pelo servidor.",
      );
      return;
    }

    const nextMode =
      operationMode.effective_mode === "HUMAN_ONLY"
        ? "OLIVIA"
        : "HUMAN_ONLY";

    const confirmed = window.confirm(
      nextMode === "HUMAN_ONLY"
        ? "Ativar o modo 100% humano? Novas mensagens irão diretamente para a equipe, sem passar pela Olívia."
        : "Reativar a Olívia? Novas conversas poderão voltar ao atendimento automático. Conversas já assumidas por atendentes continuarão humanas.",
    );

    if (!confirmed) return;

    setOperationModeBusy(true);
    setError(null);

    try {
      const mode = await updateStoreOperationMode(
        storeId,
        nextMode,
      );
      setOperationMode(mode);
    } catch (err) {
      setError(
        err instanceof Error
          ? err.message
          : "Erro ao alterar o modo de atendimento.",
      );
    } finally {
      setOperationModeBusy(false);
    }
  }

  async function openConversation(
    id: string,
    silent = false,
  ) {
    if (!silent) setBusy(true);

    try {
      let detail = await getConversation(id);

      if (
        detail.unread_count > 0 &&
        document.visibilityState === "visible"
      ) {
        try {
          await markConversationRead(id);

          detail = {
            ...detail,
            unread_count: 0,
          };

          setItems((current) =>
            current.map((item) =>
              item.id === id
                ? { ...item, unread_count: 0 }
                : item,
            ),
          );

          unreadSnapshot.current.set(id, 0);
        } catch {
          // Falha ao marcar como lida não bloqueia o atendimento.
        }
      }

      setSelected(detail);
      if (!silent) setError(null);
    } catch (err) {
      if (!silent) {
        setError(
          err instanceof Error
            ? err.message
            : "Erro ao abrir conversa.",
        );
      }
    } finally {
      if (!silent) setBusy(false);
    }
  }

  async function assumeConversation() {
    if (
      !selected ||
      selected.status === "HUMAN" ||
      selected.status === "CLOSED"
    ) {
      return;
    }

    setBusy(true);
    setError(null);

    try {
      await takeOverConversation(
        selected.id,
        operator.trim() || "Atendente",
      );

      await Promise.all([
        openConversation(selected.id, true),
        loadList(true),
      ]);
    } catch (err) {
      setError(
        err instanceof Error
          ? err.message
          : "Erro ao assumir atendimento.",
      );
    } finally {
      setBusy(false);
    }
  }

  async function returnConversationToOlivia() {
    if (
      !selected ||
      selected.status !== "HUMAN" ||
      busy
    ) {
      return;
    }

    if (
      operationMode?.effective_mode !== "OLIVIA"
    ) {
      setError(
        "A Olívia precisa estar ativa na loja antes de receber esta conversa.",
      );
      return;
    }

    const confirmed = window.confirm(
      `Devolver o atendimento de ${displayName(selected)} para a Olívia?`,
    );

    if (!confirmed) return;

    const conversationId = selected.id;

    setBusy(true);
    setError(null);

    try {
      await releaseConversation(
        conversationId,
        operator.trim() || "Atendente",
      );

      setReply("");

      await Promise.all([
        openConversation(conversationId, true),
        loadList(true),
      ]);
    } catch (err) {
      setError(
        err instanceof Error
          ? err.message
          : "Erro ao devolver atendimento para a Olívia.",
      );
    } finally {
      setBusy(false);
    }
  }

  async function finishConversation() {
    if (
      !selected ||
      selected.status !== "HUMAN" ||
      busy
    ) {
      return;
    }

    const confirmed = window.confirm(
      `Finalizar o atendimento de ${displayName(selected)}?`,
    );

    if (!confirmed) return;

    const conversationId = selected.id;

    setBusy(true);
    setError(null);

    try {
      await closeConversation(
        conversationId,
        operator.trim() || "Atendente",
      );

      setReply("");
      setSelected(null);

      await loadList(true);
    } catch (err) {
      setError(
        err instanceof Error
          ? err.message
          : "Erro ao finalizar atendimento.",
      );
    } finally {
      setBusy(false);
    }
  }

  function clearAttachment() {
    setAttachment(null);

    if (attachmentInput.current) {
      attachmentInput.current.value = "";
    }
  }

  function selectAttachment(file: File | null) {
    if (!file) return;

    const allowed = new Set([
      "application/pdf",
      "image/jpeg",
      "image/png",
      "image/webp",
    ]);

    if (!allowed.has(file.type)) {
      setError(
        "Formato não permitido. Envie PDF, JPG, PNG ou WEBP.",
      );
      clearAttachment();
      return;
    }

    if (file.size > 10_485_760) {
      setError("O arquivo deve ter no máximo 10 MB.");
      clearAttachment();
      return;
    }

    setError(null);
    setAttachment(file);
  }

  async function sendReply() {
    const content = reply.trim();

    if (
      !selected ||
      selected.status !== "HUMAN" ||
      (!content && !attachment) ||
      busy
    ) {
      return;
    }

    setBusy(true);
    setError(null);

    try {
      if (attachment) {
        await sendHumanMedia(
          selected.id,
          operator.trim() || "Atendente",
          attachment,
          content,
        );

        clearAttachment();
      } else {
        await sendHumanReply(
          selected.id,
          operator.trim() || "Atendente",
          content,
        );
      }

      setReply("");

      await Promise.all([
        openConversation(selected.id, true),
        loadList(true),
      ]);
    } catch (err) {
      setError(
        err instanceof Error
          ? err.message
          : "Erro ao enviar mensagem ou arquivo.",
      );
    } finally {
      setBusy(false);
    }
  }

  function handleKeyDown(
    event: KeyboardEvent<HTMLTextAreaElement>,
  ) {
    if (
      event.key === "Enter" &&
      !event.shiftKey &&
      !event.nativeEvent.isComposing
    ) {
      event.preventDefault();
      void sendReply();
    }
  }

  const customerById = useMemo(() => {
    const map = new Map<string, CustomerSummary>();

    for (const customer of customers) {
      map.set(customer.id, customer);
    }

    return map;
  }, [customers]);

  const customerByPhone = useMemo(() => {
    const map = new Map<string, CustomerSummary>();

    for (const customer of customers) {
      const phone = digits(customer.phone);
      if (phone) map.set(phone, customer);
    }

    return map;
  }, [customers]);

  function getCustomer(
    conversation:
      | ConversationSummary
      | ConversationDetail,
  ) {
    if (conversation.customer_id) {
      const byId = customerById.get(
        conversation.customer_id,
      );

      if (byId) return byId;
    }

    const phone = digits(
      conversation.external_conversation_id,
    );

    return phone
      ? customerByPhone.get(phone) ?? null
      : null;
  }

  function displayName(
    conversation:
      | ConversationSummary
      | ConversationDetail,
  ) {
    return (
      getCustomer(conversation)?.name?.trim() ||
      "Cliente"
    );
  }

  useEffect(() => {
    const saved = window.localStorage.getItem(
      "smartfoodia-conversation-operator",
    );

    if (saved?.trim()) setOperator(saved);
  }, []);

  useEffect(() => {
    if (operator.trim()) {
      window.localStorage.setItem(
        "smartfoodia-conversation-operator",
        operator.trim(),
      );
    }
  }, [operator]);

  useEffect(() => {
    const unlockSound = () => {
      if (
        !audioContext.current ||
        audioContext.current.state === "closed"
      ) {
        audioContext.current = new AudioContext();
      }

      if (audioContext.current.state === "suspended") {
        void audioContext.current.resume();
      }
    };

    window.addEventListener("pointerdown", unlockSound);
    window.addEventListener("keydown", unlockSound);

    return () => {
      window.removeEventListener(
        "pointerdown",
        unlockSound,
      );
      window.removeEventListener(
        "keydown",
        unlockSound,
      );
    };
  }, []);

  useEffect(() => {
    function handleCustomerConversation(
      event: Event,
    ) {
      const requested = event as CustomEvent<{
        conversationId?: string;
      }>;

      const conversationId =
        requested.detail?.conversationId;

      if (!conversationId) return;

      setFilter("ALL");
      setSearch("");

      void (async () => {
        await loadList(true);
        await openConversation(conversationId);

        window.requestAnimationFrame(() => {
          document
            .getElementById("conversas")
            ?.scrollIntoView({
              behavior: "smooth",
              block: "start",
            });
        });
      })();
    }

    window.addEventListener(
      "smartfoodia:open-conversation",
      handleCustomerConversation,
    );

    return () => {
      window.removeEventListener(
        "smartfoodia:open-conversation",
        handleCustomerConversation,
      );
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [storeId]);


  useEffect(() => {
    setOperationMode(null);
    void loadOperationMode();

    let refreshing = false;

    const refreshOperationMode = async () => {
      if (refreshing) return;
      refreshing = true;

      try {
        await loadOperationMode(true);
      } finally {
        refreshing = false;
      }
    };

    const handleVisibility = () => {
      if (document.visibilityState === "visible") {
        void refreshOperationMode();
      }
    };

    const timer = window.setInterval(
      () => void refreshOperationMode(),
      10000,
    );

    window.addEventListener(
      "focus",
      refreshOperationMode,
    );
    document.addEventListener(
      "visibilitychange",
      handleVisibility,
    );

    return () => {
      window.clearInterval(timer);
      window.removeEventListener(
        "focus",
        refreshOperationMode,
      );
      document.removeEventListener(
        "visibilitychange",
        handleVisibility,
      );
    };
  }, [storeId]);

  useEffect(() => {
    setSelected(null);
    setReply("");

    void loadList();
    void loadCustomers();

    let refreshing = false;

    const refreshList = async () => {
      if (refreshing) return;
      refreshing = true;
      try {
        await loadList(true);
      } finally {
        refreshing = false;
      }
    };

    const handleVisibility = () => {
      if (document.visibilityState === "visible") {
        void refreshList();
      }
    };

    const timer = window.setInterval(
      () => void refreshList(),
      4000,
    );

    window.addEventListener("focus", refreshList);
    window.addEventListener("online", refreshList);
    document.addEventListener(
      "visibilitychange",
      handleVisibility,
    );

    return () => {
      window.clearInterval(timer);
      window.removeEventListener("focus", refreshList);
      window.removeEventListener("online", refreshList);
      document.removeEventListener(
        "visibilitychange",
        handleVisibility,
      );
    };
  }, [storeId]);

  useEffect(() => {
    setReply("");
    setOrderOpen(false);
    setAttachment(null);

    if (attachmentInput.current) {
      attachmentInput.current.value = "";
    }

    if (!selected) return;

    const id = selected.id;
    let refreshing = false;

    const refreshConversation = async () => {
      if (refreshing) return;
      refreshing = true;
      try {
        await openConversation(id, true);
      } finally {
        refreshing = false;
      }
    };

    const handleVisibility = () => {
      if (document.visibilityState === "visible") {
        void refreshConversation();
      }
    };

    const timer = window.setInterval(
      () => void refreshConversation(),
      4000,
    );

    window.addEventListener(
      "focus",
      refreshConversation,
    );
    window.addEventListener(
      "online",
      refreshConversation,
    );
    document.addEventListener(
      "visibilitychange",
      handleVisibility,
    );

    return () => {
      window.clearInterval(timer);
      window.removeEventListener(
        "focus",
        refreshConversation,
      );
      window.removeEventListener(
        "online",
        refreshConversation,
      );
      document.removeEventListener(
        "visibilitychange",
        handleVisibility,
      );
    };
  }, [selected?.id]);

  useEffect(() => {
    const timer = window.setInterval(
      () => setNow(Date.now()),
      30000,
    );

    return () => window.clearInterval(timer);
  }, []);

  const lastMessageId =
    selected?.messages[
      selected.messages.length - 1
    ]?.id ?? null;

  useEffect(() => {
    if (!lastMessageId) return;

    timelineEnd.current?.scrollIntoView({
      behavior: "smooth",
      block: "end",
    });
  }, [selected?.id, lastMessageId]);

  const counts = useMemo(() => {
    const open = items.filter(
      (item) => item.status === "OPEN",
    ).length;

    const waiting = items.filter(
      (item) => item.status === "WAITING_HUMAN",
    ).length;

    const human = items.filter(
      (item) => item.status === "HUMAN",
    ).length;

    const closed = items.filter(
      (item) => item.status === "CLOSED",
    ).length;

    return {
      open,
      waiting,
      human,
      closed,
      all: items.length,
    };
  }, [items]);

  const visibleItems = useMemo(() => {
    const needle = search
      .trim()
      .toLocaleLowerCase("pt-BR");

    const rank: Record<string, number> = {
      WAITING_HUMAN: 0,
      OPEN: 1,
      HUMAN: 2,
      CLOSED: 3,
    };

    return items
      .filter((item) => {
        if (filter === "WAITING") {
          return item.status === "WAITING_HUMAN";
        }

        if (filter === "HUMAN") {
          return item.status === "HUMAN";
        }

        if (filter === "CLOSED") {
          return item.status === "CLOSED";
        }

        if (filter === "ACTIVE") {
          return (
            item.status === "OPEN" ||
            item.status === "WAITING_HUMAN" ||
            item.status === "HUMAN"
          );
        }

        return true;
      })
      .filter((item) => {
        if (!needle) return true;

        const customer =
          item.customer_id
            ? customerById.get(item.customer_id)
            : customerByPhone.get(
                digits(
                  item.external_conversation_id,
                ),
              );

        return [
          customer?.name,
          customer?.phone,
          item.external_conversation_id,
          item.last_message?.content,
        ]
          .filter(Boolean)
          .some((value) =>
            String(value)
              .toLocaleLowerCase("pt-BR")
              .includes(needle),
          );
      })
      .sort((a, b) => {
        const priority =
          (rank[a.status] ?? 9) -
          (rank[b.status] ?? 9);

        if (priority !== 0) return priority;

        if (
          a.status === "WAITING_HUMAN" &&
          b.status === "WAITING_HUMAN"
        ) {
          return (
            new Date(a.last_message_at).getTime() -
            new Date(b.last_message_at).getTime()
          );
        }

        return (
          new Date(b.last_message_at).getTime() -
          new Date(a.last_message_at).getTime()
        );
      });
  }, [
    items,
    customerById,
    customerByPhone,
    filter,
    search,
  ]);

  const selectedCustomer = selected
    ? getCustomer(selected)
    : null;

  return (
    <section
      className="conversationsConsole conversationsConsoleV2"
      id="conversas"
    >
      <header className="consoleHeader consoleHeaderV2">
        <div className="consoleTitleRow">
          <div>
            <p className="eyebrow">
              CENTRAL DE ATENDIMENTO
            </p>
            <h2>Conversas do WhatsApp</h2>
          </div>

          <div className="operationModeControl">
            <span
              className={
                operationMode?.effective_mode === "OLIVIA"
                  ? "humanModeBadge oliviaModeBadge"
                  : "humanModeBadge"
              }
            >
              <span />
              {!operationMode
                ? "Carregando modo..."
                : operationMode.server_forced_human
                  ? "Modo 100% humano — obrigatório pelo servidor"
                  : operationMode.effective_mode === "HUMAN_ONLY"
                    ? "Modo 100% humano"
                    : "Olívia ativa"}
            </span>

            {operationMode?.can_change &&
              !operationMode.server_forced_human && (
                <button
                  type="button"
                  className="operationModeButton"
                  onClick={() => void toggleOperationMode()}
                  disabled={operationModeBusy}
                >
                  {operationModeBusy
                    ? "Alterando..."
                    : operationMode.effective_mode === "HUMAN_ONLY"
                      ? "Reativar Olívia"
                      : "Ativar modo 100% humano"}
                </button>
              )}
          </div>
        </div>

        <div className="consoleSearchRow">
          <label className="consoleSearchBox">
            <span>Buscar</span>
            <input
              value={search}
              onChange={(event) =>
                setSearch(event.target.value)
              }
              placeholder="Nome, telefone ou mensagem..."
            />
          </label>

          <label className="operatorField">
            <span>Atendente</span>
            <input
              value={operator}
              onChange={(event) =>
                setOperator(event.target.value)
              }
              placeholder="Nome da atendente"
            />
          </label>

          <button
            className="consoleRefreshButton"
            type="button"
            onClick={() => void loadList()}
          >
            Atualizar
          </button>
        </div>

        <div className="consoleTabs">
          <button
            type="button"
            className={
              filter === "ACTIVE" ? "active" : ""
            }
            onClick={() => setFilter("ACTIVE")}
          >
            Ativas
            <strong>
              {counts.open + counts.waiting + counts.human}
            </strong>
          </button>

          <button
            type="button"
            className={
              filter === "WAITING" ? "active" : ""
            }
            onClick={() => setFilter("WAITING")}
          >
            Aguardando
            <strong>{counts.waiting}</strong>
          </button>

          <button
            type="button"
            className={
              filter === "HUMAN" ? "active" : ""
            }
            onClick={() => setFilter("HUMAN")}
          >
            Em atendimento
            <strong>{counts.human}</strong>
          </button>

          <button
            type="button"
            className={
              filter === "ALL" ? "active" : ""
            }
            onClick={() => setFilter("ALL")}
          >
            Todas
            <strong>{counts.all}</strong>
          </button>

          <button
            type="button"
            className={
              filter === "CLOSED" ? "active" : ""
            }
            onClick={() => setFilter("CLOSED")}
          >
            Encerradas
            <strong>{counts.closed}</strong>
          </button>
        </div>
      </header>

      {error && (
        <div className="consoleError">{error}</div>
      )}

      <div
        className={`conversationWorkspace ${
          selected ? "hasSelection" : ""
        }`}
      >
        <aside className="conversationList">
          <div className="conversationListHeader">
            <strong>
              {visibleItems.length} conversa
              {visibleItems.length === 1 ? "" : "s"}
            </strong>

            {counts.waiting > 0 && (
              <span>
                {counts.waiting} aguardando
              </span>
            )}
          </div>

          {visibleItems.length ? (
            visibleItems.map((item) => {
              const customer = getCustomer(item);
              const name = displayName(item);

              const waiting =
                item.status === "WAITING_HUMAN";

              const unreadCount =
                Math.max(0, item.unread_count ?? 0);
              const unread = unreadCount > 0;

              const needsReply =
                item.last_message?.sender_type ===
                  "CUSTOMER" &&
                (
                  item.status === "WAITING_HUMAN" ||
                  item.status === "HUMAN"
                );

              return (
                <button
                  key={item.id}
                  type="button"
                  className={[
                    "conversationRow",
                    selected?.id === item.id
                      ? "selected"
                      : "",
                    waiting ? "waiting" : "",
                    needsReply ? "needsReply" : "",
                    unread ? "unread" : "",
                  ]
                    .filter(Boolean)
                    .join(" ")}
                  onClick={() =>
                    void openConversation(item.id)
                  }
                >
                  <div className="avatar">
                    {initials(name)}
                  </div>

                  <div className="conversationPreview">
                    <div className="conversationPreviewTop">
                      <strong>{name}</strong>
                      <time>
                        {elapsed(
                          item.last_message_at,
                          now,
                        )}
                      </time>
                        {unread && (
                          <span
                            className="conversationUnreadBadge"
                            aria-label={`${unreadCount} mensagens não lidas`}
                          >
                            {unreadCount > 99 ? "99+" : unreadCount}
                          </span>
                        )}
                    </div>

                    <span className="conversationPhone">
                      {formatPhone(
                        customer?.phone ??
                          item.external_conversation_id,
                      )}
                    </span>

                    <p>
                      {item.last_message?.content ??
                        "Sem mensagens"}
                    </p>

                    <div className="conversationRowMeta">
                      <span
                        className={`conversationStatus ${item.status}`}
                      >
                        {statusLabel(item.status)}
                      </span>

                      {needsReply &&
                        item.status !== "CLOSED" && (
                          <span className="needsReplyBadge">
                            Cliente aguardando
                          </span>
                        )}
                    </div>
                  </div>
                </button>
              );
            })
          ) : (
            <div className="consoleEmpty">
              <strong>Nenhuma conversa</strong>
              <span>
                Não encontramos conversas com este filtro.
              </span>
            </div>
          )}
        </aside>

        <article className="chatPanel">
          {selected ? (
            <>
              <header className="chatHeader chatHeaderV2">
                <button
                  className="mobileBack"
                  type="button"
                  onClick={() => setSelected(null)}
                  aria-label="Voltar"
                >
                  ←
                </button>

                <div className="chatCustomerAvatar">
                  {initials(displayName(selected))}
                </div>

                <div className="chatCustomerIdentity">
                  <strong>
                    {displayName(selected)}
                  </strong>

                  <span>
                    {formatPhone(
                      selectedCustomer?.phone ??
                        selected.external_conversation_id,
                    )}
                  </span>

                  <small
                    className={`chatStatus ${selected.status}`}
                  >
                    {statusLabel(selected.status)}
                  </small>
                </div>

                <div className="chatHeaderAction">
                  {selected.status === "HUMAN" ? (
                    <div className="conversationOwnedActions">
                      <span className="conversationOwned">
                        ✓ Atendimento assumido
                      </span>

                      <button
                        type="button"
                        className="launchOrderButton"
                        onClick={() => setOrderOpen(true)}
                        disabled={
                          busy || !selectedCustomer?.id
                        }
                        title={
                          selectedCustomer?.id
                            ? "Lançar pedido para este cliente"
                            : "Cliente não localizado no cadastro"
                        }
                      >
                        + Lançar pedido
                      </button>
                      <button
                        type="button"
                        className="releaseConversationButton"
                        onClick={() =>
                          void returnConversationToOlivia()
                        }
                        disabled={
                          busy ||
                          operationMode?.effective_mode !== "OLIVIA"
                        }
                        title={
                          operationMode?.effective_mode === "OLIVIA"
                            ? "Devolver esta conversa para a Olívia"
                            : "A Olívia não está ativa nesta loja"
                        }
                      >
                        Devolver para Olívia
                      </button>

                      <button
                        type="button"
                        className="closeConversationButton"
                        onClick={() =>
                          void finishConversation()
                        }
                        disabled={busy}
                      >
                        Encerrar conversa
                      </button>
                    </div>
                  ) : selected.status === "CLOSED" ? (
                    <span className="conversationClosed">
                      Conversa encerrada
                    </span>
                  ) : (
                    <button
                      type="button"
                      onClick={() =>
                        void assumeConversation()
                      }
                      disabled={busy}
                    >
                      {busy
                        ? "Assumindo..."
                        : "Assumir atendimento"}
                    </button>
                  )}
                </div>
              </header>

              {orderOpen && selectedCustomer?.id && (
                <div className="conversationOrderOverlay">
                  <ConversationOrderPanel
                    storeId={storeId}
                    conversationId={selected.id}
                    messages={selected.messages}
                    assignedTo={operator.trim()}
                    customerId={selectedCustomer.id}
                    customerName={displayName(selected)}
                    onClose={() => setOrderOpen(false)}
                  />
                </div>
              )}

              <div className="messageTimeline">
                {selected.messages.map((message) => (
                  <div
                    key={message.id}
                    className={`messageBubble ${message.sender_type.toLowerCase()}`}
                  >
                    <span>{author(message)}</span>

                    <MessageContent
                      conversationId={selected.id}
                      message={message}
                    />

                    <time>
                      {new Date(
                        message.created_at,
                      ).toLocaleString("pt-BR", {
                        day: "2-digit",
                        month: "2-digit",
                        hour: "2-digit",
                        minute: "2-digit",
                      })}
                    </time>
                  </div>
                ))}

                <div ref={timelineEnd} />
              </div>

              <div className="replyComposerWrap">
                {selected.status !== "HUMAN" && (
                  <div className="composerNotice">
                    {selected.status === "CLOSED"
                      ? "Esta conversa está encerrada."
                      : "Assuma o atendimento para responder ao cliente."}
                  </div>
                )}

                {attachment && (
                  <div className="composerAttachment">
                    <div>
                      <span className="composerAttachmentIcon">
                        {attachment.type ===
                        "application/pdf"
                          ? "PDF"
                          : "IMG"}
                      </span>

                      <span>
                        <strong>
                          {attachment.name}
                        </strong>
                        <small>
                          {(
                            attachment.size /
                            1024 /
                            1024
                          ).toLocaleString(
                            "pt-BR",
                            {
                              maximumFractionDigits: 2,
                            },
                          )}{" "}
                          MB
                        </small>
                      </span>
                    </div>

                    <button
                      type="button"
                      className="composerAttachmentRemove"
                      onClick={clearAttachment}
                      disabled={busy}
                      aria-label="Remover arquivo"
                      title="Remover arquivo"
                    >
                      ×
                    </button>
                  </div>
                )}

                <div className="replyComposer">
                  <input
                    ref={attachmentInput}
                    className="composerFileInput"
                    type="file"
                    accept=".pdf,image/jpeg,image/png,image/webp"
                    disabled={
                      selected.status !== "HUMAN" ||
                      busy
                    }
                    onChange={(event) =>
                      selectAttachment(
                        event.target.files?.[0] ??
                          null,
                      )
                    }
                  />

                  <button
                    type="button"
                    className="attachmentButton"
                    onClick={() =>
                      attachmentInput.current?.click()
                    }
                    disabled={
                      selected.status !== "HUMAN" ||
                      busy
                    }
                    aria-label="Anexar arquivo"
                    title="Anexar PDF ou imagem"
                  >
                    📎
                  </button>

                  <textarea
                    value={reply}
                    onChange={(event) =>
                      setReply(event.target.value)
                    }
                    onKeyDown={handleKeyDown}
                    disabled={
                      selected.status !== "HUMAN" ||
                      busy
                    }
                    placeholder={
                      selected.status !== "HUMAN"
                        ? "Atendimento ainda não assumido"
                        : attachment
                          ? "Adicionar legenda (opcional)..."
                          : "Digite uma mensagem..."
                    }
                  />

                  <button
                    type="button"
                    onClick={() => void sendReply()}
                    disabled={
                      selected.status !== "HUMAN" ||
                      busy ||
                      (!reply.trim() && !attachment)
                    }
                  >
                    {busy
                      ? attachment
                        ? "Enviando arquivo..."
                        : "Enviando..."
                      : "Enviar"}
                  </button>
                </div>

                {selected.status === "HUMAN" && (
                  <small className="composerHint">
                    {attachment
                      ? "Arquivo selecionado • texto é legenda opcional"
                      : "Enter envia • Shift + Enter quebra linha"}
                  </small>
                )}
              </div>
            </>
          ) : (
            <div className="chatEmpty chatEmptyV2">
              <div className="chatEmptyIcon">💬</div>
              <h3>Selecione uma conversa</h3>
              <p>
                Escolha um cliente para acompanhar o
                histórico e iniciar o atendimento.
              </p>

              {counts.waiting > 0 && (
                <span>
                  {counts.waiting} conversa
                  {counts.waiting === 1 ? "" : "s"} aguardando
                  atendimento.
                </span>
              )}
            </div>
          )}
        </article>
      </div>
    </section>
  );
}
