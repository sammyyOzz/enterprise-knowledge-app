"use client";

import { useCallback, useEffect, useRef, useState } from "react";
import { Composer } from "@/components/chat/Composer";
import { ConversationList } from "@/components/chat/ConversationList";
import { MessageView, type UiMessage } from "@/components/chat/MessageView";
import {
  type ChatMessage,
  type ConversationSummary,
  askStream,
  errorMessage,
  getConversation,
  listConversations,
} from "@/lib/api";
import { uid } from "@/lib/format";

function toUi(message: ChatMessage): UiMessage {
  return {
    id: message.id,
    role: message.role,
    content: message.content,
    citations: message.citations ?? [],
    refused: message.refused,
    status: "done",
  };
}

export function Chat({ workspaceId }: { workspaceId: string }) {
  const [conversations, setConversations] = useState<ConversationSummary[]>([]);
  const [activeId, setActiveId] = useState<string | null>(null);
  const [messages, setMessages] = useState<UiMessage[]>([]);
  const [input, setInput] = useState("");
  const [streaming, setStreaming] = useState(false);
  const [loadError, setLoadError] = useState<string | null>(null);
  const [listOpen, setListOpen] = useState(false); // small screens: list and chat take turns

  const abortRef = useRef<AbortController | null>(null);
  const scrollRef = useRef<HTMLDivElement>(null);
  const stickToBottom = useRef(true);

  const loadConversations = useCallback(async () => {
    try {
      setConversations(await listConversations(workspaceId));
    } catch {
      // the list is a convenience; asking questions still works without it
    }
  }, [workspaceId]);

  useEffect(() => {
    void loadConversations();
  }, [loadConversations]);

  useEffect(() => () => abortRef.current?.abort(), []);

  useEffect(() => {
    const el = scrollRef.current;
    if (el && stickToBottom.current) el.scrollTop = el.scrollHeight;
  }, [messages]);

  function onScroll() {
    const el = scrollRef.current;
    if (el) stickToBottom.current = el.scrollHeight - el.scrollTop - el.clientHeight < 96;
  }

  function newConversation() {
    abortRef.current?.abort();
    setActiveId(null);
    setMessages([]);
    setLoadError(null);
    setListOpen(false);
  }

  async function openConversation(id: string) {
    abortRef.current?.abort();
    setActiveId(id);
    setMessages([]);
    setLoadError(null);
    setListOpen(false);
    stickToBottom.current = true;
    try {
      const conversation = await getConversation(id);
      setMessages(conversation.messages.map(toUi));
    } catch (e) {
      setLoadError(errorMessage(e));
    }
  }

  async function send(question: string) {
    const text = question.trim();
    if (!text || streaming) return;

    const assistantId = uid();
    setMessages((current) => [
      ...current,
      { id: uid(), role: "user", content: text, citations: [], refused: false, status: "done" },
      { id: assistantId, role: "assistant", content: "", citations: [], refused: false, status: "streaming" },
    ]);
    setInput("");
    setStreaming(true);
    stickToBottom.current = true;

    const controller = new AbortController();
    abortRef.current = controller;
    const patch = (changes: Partial<UiMessage>) =>
      setMessages((current) => current.map((m) => (m.id === assistantId ? { ...m, ...changes } : m)));

    let streamed = "";
    let finished = false;
    try {
      for await (const event of askStream(
        { workspace_id: workspaceId, question: text, conversation_id: activeId },
        controller.signal,
      )) {
        if (event.type === "meta") {
          setActiveId(event.conversation_id);
        } else if (event.type === "token") {
          streamed += event.text;
          patch({ content: streamed });
        } else if (event.type === "done") {
          finished = true;
          // The final text is authoritative: invalid citation markers have been removed from it.
          patch({ content: event.answer, citations: event.citations, refused: event.refused, status: "done" });
        } else if (event.type === "error") {
          finished = true;
          patch({ status: "error", errorText: event.message });
        }
      }
      if (!finished) patch({ status: "error", errorText: "The connection closed before the answer finished." });
    } catch (e) {
      if (e instanceof DOMException && e.name === "AbortError") patch({ status: "stopped" });
      else patch({ status: "error", errorText: errorMessage(e) });
    } finally {
      setStreaming(false);
      abortRef.current = null;
      void loadConversations();
    }
  }

  function retry(assistantIndex: number) {
    const question = messages[assistantIndex - 1]?.content;
    if (!question) return;
    setMessages((current) => current.slice(0, assistantIndex - 1)); // drop the failed exchange
    void send(question);
  }

  const lastIndex = messages.length - 1;

  return (
    <div className="flex h-full">
      <aside
        className={`${listOpen ? "flex" : "hidden"} w-full shrink-0 flex-col border-r border-rule bg-surface md:flex md:w-64`}
      >
        <ConversationList
          conversations={conversations}
          activeId={activeId}
          onSelect={(id) => void openConversation(id)}
          onNew={newConversation}
        />
      </aside>

      <section className={`${listOpen ? "hidden" : "flex"} min-w-0 flex-1 flex-col md:flex`}>
        <div className="flex items-center justify-between border-b border-rule px-5 py-2 md:hidden">
          <button onClick={() => setListOpen(true)} className="underline underline-offset-2">
            Conversations
          </button>
        </div>

        <div
          ref={scrollRef}
          onScroll={onScroll}
          role="log"
          aria-label="Conversation"
          aria-busy={streaming}
          className="flex-1 overflow-y-auto px-5 py-8 md:px-10"
        >
          <div className="mx-auto max-w-3xl">
            {loadError && (
              <p role="alert" className="text-bad">
                {loadError}
              </p>
            )}
            {messages.length === 0 && !loadError && (
              <div className="max-w-[54ch] pt-[10vh]">
                <h1 className="font-serif text-[28px] leading-tight">Ask your documents</h1>
                <p className="mt-2 text-muted">
                  Answers come only from the files in your knowledge base, with the passages they rest on. If nothing
                  relevant turns up, you will be told so.
                </p>
              </div>
            )}
            {messages.map((message, index) => (
              <MessageView
                key={message.id}
                message={message}
                onRetry={
                  index === lastIndex && !streaming && (message.status === "error" || message.status === "stopped")
                    ? () => retry(index)
                    : undefined
                }
              />
            ))}
          </div>
        </div>

        <Composer
          value={input}
          onChange={setInput}
          onSend={() => void send(input)}
          onStop={() => abortRef.current?.abort()}
          streaming={streaming}
        />
      </section>
    </div>
  );
}