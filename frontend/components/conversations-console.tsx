"use client";
import { FormEvent, useEffect, useState } from "react";
import { ConversationDetail, ConversationSummary, getConversation, listConversations, releaseConversation, sendHumanReply, takeOverConversation } from "@/lib/api";

export function ConversationsConsole({ storeId }: { storeId: string }) {
  const [items, setItems] = useState<ConversationSummary[]>([]);
  const [selected, setSelected] = useState<ConversationDetail | null>(null);
  const [filter, setFilter] = useState("");
  const [operator, setOperator] = useState("Atendente");
  const [reply, setReply] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  async function loadList() {
    if (!storeId) return;
    try { setItems(await listConversations(storeId, filter || undefined)); }
    catch (e) { setError(e instanceof Error ? e.message : "Erro ao carregar conversas."); }
  }
  async function open(id: string, silent = false) {
    if (!silent) setBusy(true);
    setError(null);
    try {
      setSelected(await getConversation(id));
    } catch (e) {
      setError(e instanceof Error ? e.message : "Erro ao abrir conversa.");
    } finally {
      if (!silent) setBusy(false);
    }
  }
  async function toggle() {
    if (!selected) return;
    setBusy(true); setError(null);
    try {
      if (selected.status === "HUMAN") await releaseConversation(selected.id, operator);
      else await takeOverConversation(selected.id, operator);
      await open(selected.id); await loadList();
    } catch (e) { setError(e instanceof Error ? e.message : "Erro ao alterar atendimento."); }
    finally { setBusy(false); }
  }
  async function submit(event: FormEvent) {
    event.preventDefault();
    if (!selected || !reply.trim()) return;
    setBusy(true); setError(null);
    try { await sendHumanReply(selected.id, operator, reply.trim()); setReply(""); await open(selected.id); await loadList(); }
    catch (e) { setError(e instanceof Error ? e.message : "Erro ao enviar mensagem."); }
    finally { setBusy(false); }
  }

  useEffect(() => {
    void loadList();
    const timer = window.setInterval(() => void loadList(), 5000);
    return () => window.clearInterval(timer);
  }, [storeId, filter]);
  useEffect(() => {
    if (!selected) return;
    const timer = window.setInterval(() => void open(selected.id, true), 8000);
    return () => window.clearInterval(timer);
  }, [selected?.id]);

  return <section className="conversationsConsole" id="conversas">
    <header className="consoleHeader">
      <div><p className="eyebrow">CENTRAL DE CONVERSAS</p><h2>Atendimento em tempo real</h2></div>
      <div className="consoleControls">
        <input value={operator} onChange={e => setOperator(e.target.value)} placeholder="Nome do atendente" />
        <select value={filter} onChange={e => setFilter(e.target.value)}><option value="">Todas</option><option value="OPEN">Olívia</option><option value="WAITING_HUMAN">Aguardando atendente</option><option value="HUMAN">Atendente</option><option value="CLOSED">Encerradas</option></select>
        <button onClick={() => void loadList()}>Atualizar</button>
      </div>
    </header>
    {error && <div className="consoleError">{error}</div>}
    <div className="conversationWorkspace">
      <aside className="conversationList">
        {items.length ? items.map(item => <button key={item.id} className={`conversationRow ${selected?.id===item.id?"selected":""}`} onClick={() => void open(item.id)}>
          <div className="avatar">{item.external_conversation_id?.slice(-2) ?? "CL"}</div>
          <div className="conversationPreview"><div><strong>{item.external_conversation_id ?? "Cliente"}</strong><time>{new Date(item.last_message_at).toLocaleTimeString("pt-BR", {hour:"2-digit",minute:"2-digit"})}</time></div><p>{item.last_message?.content ?? "Sem mensagens"}</p><span className={`conversationStatus ${item.status}`}>{item.status === "WAITING_HUMAN" ? "Aguardando atendente" : item.status === "HUMAN" ? "Atendente" : item.status === "OPEN" ? "Olívia" : "Encerrada"}</span></div>
        </button>) : <div className="consoleEmpty">Nenhuma conversa encontrada.</div>}
      </aside>
      <article className="chatPanel">
        {selected ? <>
          <header className="chatHeader"><div><strong>{selected.external_conversation_id ?? "Cliente"}</strong><span>{selected.status === "WAITING_HUMAN" ? "Aguardando atendente" : selected.status === "HUMAN" ? "Com atendente" : "Com a Olívia"}</span></div><button className={selected.status === "HUMAN" ? "release" : ""} onClick={() => void toggle()} disabled={busy || selected.status === "CLOSED"}>{selected.status === "HUMAN" ? "Devolver para Olívia" : "Assumir conversa"}</button></header>
          <div className="messageTimeline">{selected.messages.map(message => <div key={message.id} className={`messageBubble ${message.sender_type.toLowerCase()}`}><span>{message.sender_type === "CUSTOMER" ? "Cliente" : message.sender_type === "OLIVIA" ? "Olívia" : message.sender_type === "HUMAN" ? "Atendente" : "Sistema"}</span><p>{message.content}</p><time>{new Date(message.created_at).toLocaleString("pt-BR")}</time></div>)}</div>
          <form className="replyComposer" onSubmit={submit}><textarea value={reply} onChange={e => setReply(e.target.value)} disabled={selected.status !== "HUMAN" || busy} placeholder={selected.status === "HUMAN" ? "Digite a resposta..." : "Assuma a conversa para responder."}/><button type="submit" disabled={selected.status !== "HUMAN" || busy || !reply.trim()}>Enviar</button></form>
        </> : <div className="chatEmpty"><h3>Selecione uma conversa</h3><p>Acompanhe o histórico e assuma o atendimento quando necessário.</p></div>}
      </article>
    </div>
  </section>;
}
