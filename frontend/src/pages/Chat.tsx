import { useState, useRef, useEffect } from "react";
import { useQuery, useMutation } from "@tanstack/react-query";
import { Send, FileText, Loader2 } from "lucide-react";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Card } from "@/components/ui/card";
import { chatApi, workspaceApi } from "@/lib/api";
import { useAppStore } from "@/stores/appStore";
import type { Message, Citation } from "@/types";

export function Chat() {
  const [message, setMessage] = useState("");
  const [conversationId, setConversationId] = useState<string | null>(null);
  const [messages, setMessages] = useState<Message[]>([]);
  const [streaming, setStreaming] = useState(false);
  const messagesEndRef = useRef<HTMLDivElement>(null);
  const currentWorkspace = useAppStore((s) => s.currentWorkspace);

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

  const sendMutation = useMutation({
    mutationFn: async (msg: string) => {
      if (!workspaceId) throw new Error("No workspace selected");
      const { data } = await chatApi.send({
        message: msg,
        workspace_id: workspaceId,
        conversation_id: conversationId || undefined,
      });
      return data;
    },
    onSuccess: (data) => {
      setConversationId(data.conversation_id);
      setMessages((prev) => [
        ...prev,
        {
          id: crypto.randomUUID(),
          conversation_id: data.conversation_id,
          role: "user",
          content: message,
          citations: null,
          model: null,
          latency_ms: null,
          created_at: new Date().toISOString(),
        },
        {
          id: data.message_id,
          conversation_id: data.conversation_id,
          role: "assistant",
          content: data.content,
          citations: data.citations,
          model: data.model,
          latency_ms: data.latency_ms,
          created_at: new Date().toISOString(),
        },
      ]);
      setMessage("");
    },
  });

  const handleSend = () => {
    if (!message.trim() || !workspaceId) return;
    sendMutation.mutate(message);
  };

  const loadConversation = async (id: string) => {
    setConversationId(id);
    const { data } = await chatApi.messages(id);
    setMessages(data);
  };

  return (
    <div className="flex h-full">
      <div className="w-64 border-r bg-card p-4">
        <h2 className="mb-4 text-sm font-semibold text-muted-foreground">Conversations</h2>
        <div className="space-y-1">
          {conversations?.items?.map((conv: { id: string; title: string }) => (
            <button
              key={conv.id}
              onClick={() => loadConversation(conv.id)}
              className={`w-full rounded-lg px-3 py-2 text-left text-sm hover:bg-accent ${
                conversationId === conv.id ? "bg-accent" : ""
              }`}
            >
              {conv.title}
            </button>
          ))}
        </div>
      </div>

      <div className="flex flex-1 flex-col">
        <div className="flex-1 overflow-y-auto p-6 space-y-6">
          {messages.length === 0 && (
            <div className="flex h-full items-center justify-center">
              <div className="text-center">
                <h2 className="text-2xl font-semibold mb-2">Knowledge Assistant</h2>
                <p className="text-muted-foreground">Ask questions about your company documents</p>
              </div>
            </div>
          )}
          {messages.map((msg) => (
            <div key={msg.id} className={`flex ${msg.role === "user" ? "justify-end" : "justify-start"}`}>
              <Card className={`max-w-2xl p-4 ${msg.role === "user" ? "bg-primary text-primary-foreground" : ""}`}>
                <p className="whitespace-pre-wrap">{msg.content}</p>
                {msg.citations && msg.citations.length > 0 && (
                  <div className="mt-3 border-t pt-3 space-y-2">
                    <p className="text-xs font-semibold opacity-70">Sources</p>
                    {msg.citations.map((cite: Citation, i: number) => (
                      <div key={i} className="flex items-start gap-2 text-xs opacity-80">
                        <FileText className="h-3 w-3 mt-0.5 shrink-0" />
                        <span>
                          {cite.file_name}
                          {cite.page_number && `, Page ${cite.page_number}`}
                          {" "}({(cite.relevance_score * 100).toFixed(0)}%)
                        </span>
                      </div>
                    ))}
                  </div>
                )}
                {msg.latency_ms && (
                  <p className="mt-2 text-xs opacity-50">{msg.latency_ms}ms · {msg.model}</p>
                )}
              </Card>
            </div>
          ))}
          {(sendMutation.isPending || streaming) && (
            <div className="flex items-center gap-2 text-muted-foreground">
              <Loader2 className="h-4 w-4 animate-spin" />
              Thinking...
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
              disabled={!workspaceId || sendMutation.isPending}
            />
            <Button onClick={handleSend} disabled={!message.trim() || sendMutation.isPending}>
              <Send className="h-4 w-4" />
            </Button>
          </div>
        </div>
      </div>
    </div>
  );
}
