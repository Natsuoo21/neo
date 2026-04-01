import { useCallback, useEffect, useRef, useState } from "react";
import { Send } from "lucide-react";
import { rpc } from "@/lib/rpc";
import { useNeoStore } from "@/stores/neoStore";
import MessageBubble from "./MessageBubble";
import SuggestionBanner from "./SuggestionBanner";
import VoiceButton from "./VoiceButton";
import type { ChatMessage } from "@/stores/neoStore";
import type { ConversationNewResult, ExecuteResult } from "@/types/rpc";

export default function ChatView() {
  const [input, setInput] = useState("");
  const messagesEndRef = useRef<HTMLDivElement>(null);
  const textareaRef = useRef<HTMLTextAreaElement>(null);

  const submittingRef = useRef(false);
  const loading = useNeoStore((s) => s.loading);
  const setLoading = useNeoStore((s) => s.setLoading);
  const messages = useNeoStore((s) => s.messages);
  const addMessage = useNeoStore((s) => s.addMessage);
  const sessionId = useNeoStore((s) => s.sessionId);
  const setSessionId = useNeoStore((s) => s.setSessionId);

  // Scroll to bottom on new messages
  useEffect(() => {
    messagesEndRef.current?.scrollIntoView({ behavior: "smooth" });
  }, [messages]);

  // Auto-resize textarea
  useEffect(() => {
    if (textareaRef.current) {
      textareaRef.current.style.height = "auto";
      textareaRef.current.style.height = `${Math.min(textareaRef.current.scrollHeight, 150)}px`;
    }
  }, [input]);

  const handleSend = useCallback(async () => {
    const cmd = input.trim();
    if (!cmd || loading || submittingRef.current) return;
    submittingRef.current = true;

    // Ensure we have a session
    let sid = sessionId;
    if (!sid) {
      try {
        const res = await rpc<ConversationNewResult>("neo.conversation.new");
        sid = res.session_id;
        setSessionId(sid);
      } catch {
        sid = crypto.randomUUID();
        setSessionId(sid);
      }
    }

    // Add user message
    const userMsg: ChatMessage = {
      id: crypto.randomUUID(),
      role: "user",
      content: cmd,
      timestamp: Date.now(),
    };
    addMessage(userMsg);
    setInput("");
    setLoading(true);

    try {
      const result = await rpc<ExecuteResult>("neo.execute", {
        command: cmd,
        session_id: sid,
      });

      const assistantMsg: ChatMessage = {
        id: crypto.randomUUID(),
        role: "assistant",
        content: result.message,
        model: result.model_used,
        tool: result.tool_used || undefined,
        duration: result.duration_ms,
        timestamp: Date.now(),
      };
      addMessage(assistantMsg);
    } catch (err) {
      const errorMsg: ChatMessage = {
        id: crypto.randomUUID(),
        role: "assistant",
        content: err instanceof Error ? err.message : "Failed to connect to backend.",
        timestamp: Date.now(),
      };
      addMessage(errorMsg);
    } finally {
      setLoading(false);
      submittingRef.current = false;
    }
  }, [input, loading, sessionId, addMessage, setSessionId, setLoading]);

  const handleKeyDown = (e: React.KeyboardEvent) => {
    if (e.key === "Enter" && !e.shiftKey) {
      e.preventDefault();
      handleSend();
    }
  };

  return (
    <div className="flex flex-col h-full">
      {/* Suggestion banner */}
      <SuggestionBanner />

      {/* Messages area */}
      <div className="flex-1 overflow-y-auto px-6 py-4">
        <div className="max-w-3xl mx-auto">
          {messages.length === 0 ? (
            <div className="flex items-center justify-center h-full text-muted-foreground">
              <div className="text-center space-y-3 max-w-sm">
                <div className="text-4xl font-bold text-primary/20 tracking-tighter select-none">Neo</div>
                <p className="text-[15px] font-medium text-foreground/80">Start a conversation</p>
                <p className="text-sm text-muted-foreground leading-relaxed">Ask Neo to create files, research topics, or automate tasks.</p>
              </div>
            </div>
          ) : (
            <>
              {messages.map((msg) => (
                <MessageBubble key={msg.id} message={msg} />
              ))}
              {loading && (
                <div className="flex gap-3 py-3 justify-start animate-fade-in-up">
                  <div className="bg-card border border-border/60 rounded-2xl rounded-bl-sm px-4 py-3 shadow-card flex gap-1.5 items-center">
                    <span className="w-1.5 h-1.5 rounded-full bg-muted-foreground/50 animate-bounce" style={{ animationDelay: "0ms" }} />
                    <span className="w-1.5 h-1.5 rounded-full bg-muted-foreground/50 animate-bounce" style={{ animationDelay: "150ms" }} />
                    <span className="w-1.5 h-1.5 rounded-full bg-muted-foreground/50 animate-bounce" style={{ animationDelay: "300ms" }} />
                  </div>
                </div>
              )}
              <div ref={messagesEndRef} />
            </>
          )}
        </div>
      </div>

      {/* Input area */}
      <div className="border-t border-border/60 p-4 bg-card/30">
        <div className="flex items-end gap-2 max-w-3xl mx-auto">
          <VoiceButton />
          <textarea
            ref={textareaRef}
            value={input}
            onChange={(e) => setInput(e.target.value)}
            onKeyDown={handleKeyDown}
            placeholder="Type a message... (Enter to send, Shift+Enter for new line)"
            rows={1}
            className="flex-1 bg-card border border-border rounded-lg px-4 py-3 text-[13px] resize-none outline-none focus:border-primary/40 focus:ring-2 focus:ring-primary/10 focus:bg-card/80 transition-all placeholder:text-muted-foreground"
          />
          <button
            onClick={handleSend}
            disabled={!input.trim() || loading}
            className="shrink-0 w-10 h-10 rounded-lg bg-primary text-primary-foreground flex items-center justify-center hover:brightness-110 active:scale-95 disabled:opacity-40 disabled:cursor-not-allowed transition-interaction"
          >
            <Send className="w-4 h-4" />
          </button>
        </div>
      </div>
    </div>
  );
}
