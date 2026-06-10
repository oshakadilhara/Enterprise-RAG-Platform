import { useState, useRef, useEffect, useCallback } from "react";
import { useQuery, useQueryClient } from "@tanstack/react-query";
import {
  Send,
  FileText,
  Loader2,
  Plus,
  Zap,
  AlertTriangle,
  ShieldCheck,
} from "lucide-react";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Card } from "@/components/ui/card";
import { chatApi, workspaceApi } from "@/lib/api";
import { useAppStore } from "@/stores/appStore";
import type { Message, Citation, ChatStreamEvent } from "@/types";

const MATCH_TYPE_LABELS: Record<Citation["match_type"], string> = {
  both: "semantic + keyword",
  keyword: "keyword",
  semantic: "semantic",
};

function MatchTypeBadge({ type }: { type: Citation["match_type"] }) {
  const styles: Record<Citation["match_type"], string> = {
    both: "bg-emerald-500/15 text-emerald-600",
    keyword: "bg-amber-500/15 text-amber-600",
    semantic: "bg-sky-500/15 text-sky-600",
  };
  return (
    <span className={`rounded px-1.5 py-0.5 text-[10px] font-medium ${styles[type]}`}>
      {MATCH_TYPE_LABELS[type]}
    </span>
  );
}

function CitationRow({ cite }: { cite: Citation }) {
  const [expanded, setExpanded] = useState(false);
  return (
    <button
      onClick={() => setExpanded((v) => !v)}
      className="block w-full rounded-md p-1.5 text-left text-xs opacity-90 hover:bg-accent/50"
      title="Click for score breakdown"
    >
      <div className="flex items-start gap-2">
        <FileText className="mt-0.5 h-3 w-3 shrink-0" />
        <span className="flex-1">
          {cite.file_name}
          {cite.page_number != null && `, Page ${cite.page_number}`}{" "}
          <span className="opacity-60">({(cite.relevance_score * 100).toFixed(0)}%)</span>
        </span>
        <MatchTypeBadge type={cite.match_type ?? "semantic"} />
      </div>
      {expanded && (
        <div className="mt-1.5 space-y-1 pl-5">
          <p className="italic opacity-70">"{cite.content_snippet}…"</p>
          <div className="flex gap-3 font-mono text-[10px] opacity-60">
            <span>vector {(cite.vector_score * 100).toFixed(0)}%</span>
            <span>bm25 {(cite.bm25_score * 100).toFixed(0)}%</span>
            <span>rerank {(cite.rerank_score * 100).toFixed(0)}%</span>
          </div>
        </div>
      )}
    </button>
  );
}

function ConfidenceIndicator({ msg }: { msg: Message }) {
  if (msg.abstained) {
    return (
      <span className="flex items-center gap-1 text-amber-600">
        <AlertTriangle className="h-3 w-3" /> low retrieval confidence — answer withheld
      </span>
    );
  }
  if (msg.cached) {
    return (
      <span className="flex items-center gap-1 text-emerald-600">
        <Zap className="h-3 w-3" /> cached answer
      </span>
    );
  }
  if (msg.confidence != null && msg.confidence > 0) {
    return (
      <span className="flex items-center gap-1 opacity-60">
        <ShieldCheck className="h-3 w-3" /> confidence {(msg.confidence * 100).toFixed(0)}%
      </span>
    );
  }
  return null;
}

export function Chat() {
  const [message, setMessage] = useState("");
  const [conversationId, setConversationId] = useState<string | null>(null);
  const [messages, setMessages] = useState<Message[]>([]);
  const [streaming, setStreaming] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const messagesEndRef = useRef<HTMLDivElement>(null);
  const abortRef = useRef<AbortController | null>(null);
  const currentWorkspace = useAppStore((s) => s.currentWorkspace);
  const queryClient = useQueryClient();

  const { data: workspaces } = useQuery({
    queryKey: ["workspaces"],
    queryFn: () => workspaceApi.list().then((r) => r.data),
  });

  const workspaceId = currentWorkspace?.id || workspaces?.items?.[0]?.id;

  const { data: conversations } = useQuery({
    queryKey: ["conversations", workspaceId],
    queryFn: () => chatApi.conversations(workspaceId).then((r) => r.data),
    enabled: !!workspaceId,
  });

  useEffect(() => {
    messagesEndRef.current?.scrollIntoView({ behavior: "smooth" });
  }, [messages]);

  useEffect(() => () => abortRef.current?.abort(), []);

  const handleSend = useCallback(async () => {
    const text = message.trim();
    if (!text || !workspaceId || streaming) return;

    setError(null);
    setMessage("");
    setStreaming(true);

    const userMsg: Message = {
      id: crypto.randomUUID(),
      conversation_id: conversationId || "",
      role: "user",
      content: text,
      citations: null,
      model: null,
      latency_ms: null,
      created_at: new Date().toISOString(),
    };
    const assistantId = crypto.randomUUID();
    const assistantMsg: Message = {
      id: assistantId,
      conversation_id: conversationId || "",
      role: "assistant",
      content: "",
      citations: null,
      model: null,
      latency_ms: null,
      created_at: new Date().toISOString(),
    };
    setMessages((prev) => [...prev, userMsg, assistantMsg]);

    const updateAssistant = (patch: Partial<Message>) =>
      setMessages((prev) =>
        prev.map((m) => (m.id === assistantId ? { ...m, ...patch } : m))
      );

    abortRef.current = new AbortController();
    try {
      await chatApi.stream(
        {
          message: text,
          workspace_id: workspaceId,
          conversation_id: conversationId || undefined,
        },
        (event: ChatStreamEvent) => {
          if (event.type === "metadata") {
            setConversationId(event.conversation_id);
            updateAssistant({
              conversation_id: event.conversation_id,
              citations: event.citations,
              confidence: event.confidence,
              abstained: event.abstained,
              cached: event.cached,
            });
          } else if (event.type === "content") {
            setMessages((prev) =>
              prev.map((m) =>
                m.id === assistantId ? { ...m, content: m.content + event.content } : m
              )
            );
          } else if (event.type === "done") {
            updateAssistant({ id: event.message_id });
            queryClient.invalidateQueries({ queryKey: ["conversations", workspaceId] });
          }
        },
        abortRef.current.signal
      );
    } catch (e) {
      if ((e as Error).name !== "AbortError") {
        setError(e instanceof Error ? e.message : "Failed to get a response");
        setMessages((prev) => prev.filter((m) => m.id !== assistantId || m.content !== ""));
      }
    } finally {
      setStreaming(false);
    }
  }, [message, workspaceId, conversationId, streaming, queryClient]);

  const loadConversation = async (id: string) => {
    abortRef.current?.abort();
    setConversationId(id);
    setError(null);
    const { data } = await chatApi.messages(id);
    setMessages(data);
  };

  const newConversation = () => {
    abortRef.current?.abort();
    setConversationId(null);
    setMessages([]);
    setError(null);
  };

  return (
    <div className="flex h-full">
      <div className="flex w-64 flex-col border-r bg-card p-4">
        <Button variant="outline" size="sm" className="mb-4 w-full" onClick={newConversation}>
          <Plus className="mr-2 h-4 w-4" /> New chat
        </Button>
        <h2 className="mb-2 text-sm font-semibold text-muted-foreground">Conversations</h2>
        <div className="flex-1 space-y-1 overflow-y-auto">
          {conversations?.items?.map((conv: { id: string; title: string }) => (
            <button
              key={conv.id}
              onClick={() => loadConversation(conv.id)}
              className={`w-full truncate rounded-lg px-3 py-2 text-left text-sm hover:bg-accent ${
                conversationId === conv.id ? "bg-accent" : ""
              }`}
            >
              {conv.title}
            </button>
          ))}
        </div>
      </div>

      <div className="flex flex-1 flex-col">
        <div className="flex-1 space-y-6 overflow-y-auto p-6">
          {messages.length === 0 && (
            <div className="flex h-full items-center justify-center">
              <div className="text-center">
                <h2 className="mb-2 text-2xl font-semibold">Knowledge Assistant</h2>
                <p className="text-muted-foreground">
                  Ask questions about your company documents — answers include sources and
                  retrieval confidence
                </p>
              </div>
            </div>
          )}
          {messages.map((msg) => (
            <div
              key={msg.id}
              className={`flex ${msg.role === "user" ? "justify-end" : "justify-start"}`}
            >
              <Card
                className={`max-w-2xl p-4 ${
                  msg.role === "user"
                    ? "bg-primary text-primary-foreground"
                    : msg.abstained
                      ? "border-amber-500/40"
                      : ""
                }`}
              >
                <p className="whitespace-pre-wrap">
                  {msg.content}
                  {streaming && msg.role === "assistant" && msg.content === "" && (
                    <Loader2 className="inline h-4 w-4 animate-spin" />
                  )}
                </p>
                {msg.citations && msg.citations.length > 0 && (
                  <div className="mt-3 space-y-1 border-t pt-3">
                    <p className="text-xs font-semibold opacity-70">Sources</p>
                    {msg.citations.map((cite, i) => (
                      <CitationRow key={i} cite={cite} />
                    ))}
                  </div>
                )}
                {msg.role === "assistant" && (
                  <div className="mt-2 flex items-center gap-3 text-xs">
                    <ConfidenceIndicator msg={msg} />
                    {msg.latency_ms != null && (
                      <span className="opacity-50">
                        {msg.latency_ms}ms{msg.model ? ` · ${msg.model}` : ""}
                      </span>
                    )}
                  </div>
                )}
              </Card>
            </div>
          ))}
          {error && (
            <div className="flex items-center gap-2 text-sm text-destructive">
              <AlertTriangle className="h-4 w-4" /> {error}
            </div>
          )}
          <div ref={messagesEndRef} />
        </div>

        <div className="border-t p-4">
          <div className="mx-auto flex max-w-3xl gap-2">
            <Input
              value={message}
              onChange={(e) => setMessage(e.target.value)}
              onKeyDown={(e) => e.key === "Enter" && !e.shiftKey && handleSend()}
              placeholder="Ask a question about your documents..."
              disabled={!workspaceId || streaming}
            />
            <Button onClick={handleSend} disabled={!message.trim() || streaming}>
              {streaming ? <Loader2 className="h-4 w-4 animate-spin" /> : <Send className="h-4 w-4" />}
            </Button>
          </div>
        </div>
      </div>
    </div>
  );
}
