import { useCallback, useEffect, useRef, useState } from "react";
import { Send, FileText, Search, Wand2 } from "lucide-react";
import { rpc } from "@/lib/rpc";
import { useNeoStore } from "@/stores/neoStore";
import MessageBubble from "./MessageBubble";
import SuggestionBanner from "./SuggestionBanner";
import VoiceButton from "./VoiceButton";
import type { ChatMessage } from "@/stores/neoStore";
import type { ConversationNewResult, ExecuteResult } from "@/types/rpc";

const QUICK_ACTIONS = [
  { label: "Write a report", icon: FileText, prompt: "Write a report about " },
  { label: "Research a topic", icon: Search, prompt: "Research and summarize " },
  { label: "Automate a task", icon: Wand2, prompt: "Create an automation that " },
];

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
      {/* Input area — top */}
      <div className="border-b border-border/60 px-3 md:px-6 py-3 bg-gradient-to-b from-card/50 to-transparent">
        <div className="flex items-end gap-2 max-w-3xl mx-auto">
          <VoiceButton />
          <textarea
            ref={textareaRef}
            value={input}
            onChange={(e) => setInput(e.target.value)}
            onKeyDown={handleKeyDown}
            placeholder="Ask Neo anything... (Enter to send)"
            rows={1}
            className="flex-1 bg-card border border-border rounded-xl px-4 py-3 text-sm resize-none outline-none focus:border-primary/40 focus:ring-2 focus:ring-primary/10 focus:bg-card/80 transition-all placeholder:text-muted-foreground/50"
          />
          <button
            onClick={handleSend}
            disabled={!input.trim() || loading}
            className="shrink-0 w-10 h-10 rounded-xl bg-primary text-primary-foreground flex items-center justify-center hover:brightness-110 active:scale-95 disabled:opacity-40 disabled:cursor-not-allowed transition-interaction"
          >
            <Send className="w-4 h-4" />
          </button>
        </div>
      </div>

      {/* Suggestion banner */}
      <SuggestionBanner />

      {/* Messages area */}
      <div className="flex-1 overflow-y-auto px-3 md:px-6 py-4">
        <div className="max-w-3xl mx-auto">
          {messages.length === 0 ? (
            <div className="flex items-center justify-center h-full text-muted-foreground">
              <div className="text-center space-y-6 max-w-md">
                {/* Animated Neo wordmark */}
                <div className="text-6xl font-bold tracking-tighter bg-gradient-to-r from-primary/40 via-primary/20 to-primary/40 bg-clip-text text-transparent bg-[length:200%_100%] animate-[shimmer_3s_ease-in-out_infinite] select-none">
                  Neo
                </div>
                <div className="space-y-1.5">
                  <p className="text-[15px] font-medium text-foreground/80">Your personal intelligence agent</p>
                  <p className="text-sm text-muted-foreground leading-relaxed">
                    Ask questions, create files, research topics, or automate workflows.
                  </p>
                </div>

                {/* Quick action chips */}
                <div className="flex flex-wrap justify-center gap-2 pt-2">
                  {QUICK_ACTIONS.map(({ label, icon: Icon, prompt }) => (
                    <button
                      key={label}
                      onClick={() => {
                        setInput(prompt);
                        textareaRef.current?.focus();
                      }}
                      className="flex items-center gap-2 px-3.5 py-2 rounded-xl border border-border/60 bg-card/60 text-xs text-muted-foreground hover:text-foreground hover:bg-card hover:shadow-card hover:border-border active:scale-[0.97] transition-interaction"
                    >
                      <Icon className="w-3.5 h-3.5" />
                      {label}
                    </button>
                  ))}
                </div>
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
    </div>
  );
}
