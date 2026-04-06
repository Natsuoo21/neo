import { useCallback, useEffect, useRef, useState } from "react";
import { cn } from "@/lib/utils";
import { rpc } from "@/lib/rpc";
import { useNeoStore } from "@/stores/neoStore";
import MessageBubble from "./MessageBubble";
import SuggestionBanner from "./SuggestionBanner";
import VoiceButton from "./VoiceButton";
import type { ChatMessage } from "@/stores/neoStore";
import type { ConversationNewResult, ExecuteResult } from "@/types/rpc";

const QUICK_ACTIONS = [
  { label: "Write a report", icon: "description", prompt: "Write a report about " },
  { label: "Research a topic", icon: "search", prompt: "Research and summarize " },
  { label: "Automate a task", icon: "auto_awesome", prompt: "Create an automation that " },
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

  const isEmpty = messages.length === 0;

  return (
    <div className="flex flex-col h-full w-full relative overflow-hidden">
      {/* Background Ambient Glow */}
      <div className="absolute top-1/2 left-1/2 -translate-x-1/2 -translate-y-1/2 w-[600px] h-[600px] bg-primary/5 rounded-full blur-[120px] pointer-events-none"></div>

      {/* Visual Detail: Asymmetric Editorial Element */}
      <div className="absolute top-12 right-12 opacity-20 pointer-events-none">
        <div className="font-headline text-[12rem] font-bold text-transparent bg-clip-text bg-gradient-to-b from-white/20 to-transparent tracking-tighter leading-none select-none">AI</div>
      </div>

      {/* Suggestion banner */}
      <SuggestionBanner />

      {/* Messages area */}
      <div className="flex-1 overflow-y-auto px-3 md:px-6 py-4">
        <div className="max-w-3xl mx-auto relative z-10">
          {isEmpty ? (
            <div className="flex flex-col items-center justify-end h-full pb-6">
              <div className="text-center space-y-6 max-w-md">
                {/* Neo wordmark */}
                <h2 className="font-headline text-[7rem] font-bold text-white tracking-tighter neo-glow leading-none select-none">
                  Neo
                </h2>
                <div className="space-y-1.5">
                  <p className="font-headline text-2xl text-slate-400 tracking-wide font-light">Your personal intelligence agent</p>
                  <p className="text-sm text-muted-foreground/60 leading-relaxed font-body">
                    Ask questions, create files, research topics, or automate workflows.
                  </p>
                </div>

                {/* Quick action chips */}
                <div className="flex flex-wrap justify-center gap-4 pt-8">
                  {QUICK_ACTIONS.map(({ label, icon, prompt }) => (
                    <button
                      key={label}
                      onClick={() => {
                        setInput(prompt);
                        textareaRef.current?.focus();
                      }}
                       className="bg-white/5 hover:bg-white/10 backdrop-blur-md px-6 py-3 rounded-full border border-white/5 transition-all duration-300 group flex items-center gap-2 active:scale-95"
                    >
                      <span className="material-symbols-outlined text-[18px] text-on-surface-variant group-hover:text-on-surface">{icon}</span>
                      <span className="text-sm font-semibold text-on-surface-variant group-hover:text-on-surface">{label}</span>
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
                  <div className="bg-white/5 backdrop-blur-md border border-white/5 rounded-2xl rounded-bl-sm px-4 py-3 shadow-card flex gap-1.5 items-center">
                    <span className="w-1.5 h-1.5 rounded-full bg-muted-foreground/30 animate-bounce" style={{ animationDelay: "0ms" }} />
                    <span className="w-1.5 h-1.5 rounded-full bg-muted-foreground/30 animate-bounce" style={{ animationDelay: "150ms" }} />
                    <span className="w-1.5 h-1.5 rounded-full bg-muted-foreground/30 animate-bounce" style={{ animationDelay: "300ms" }} />
                  </div>
                </div>
              )}
              <div ref={messagesEndRef} />
            </>
          )}
        </div>
      </div>

      {/* Input area — bottom, lifted slightly when empty */}
      <div className={cn(
        "px-3 md:px-6 pt-3 bg-transparent relative z-20",
        isEmpty ? "pb-[12vh]" : "pb-4",
      )}>
        <div className="max-w-3xl mx-auto">
           <div className="relative group">
              <div className="absolute -inset-0.5 bg-gradient-to-r from-primary/30 to-secondary/30 rounded-2xl blur opacity-30 group-focus-within:opacity-60 transition duration-1000 group-hover:duration-200"></div>
              <div className="relative flex items-center bg-surface-container-highest/60 backdrop-blur-2xl border border-white/10 rounded-2xl p-2 pl-6 gap-2">
                <VoiceButton />
                <input
                  ref={textareaRef as any}
                  value={input}
                  onChange={(e) => setInput(e.target.value)}
                  onKeyDown={handleKeyDown}
                  placeholder="Ask Neo anything... (Enter to send)"
                  className="bg-transparent border-none focus:ring-0 w-full py-4 text-on-surface placeholder:text-slate-500 font-body text-lg outline-none"
                />
                <button
                  onClick={handleSend}
                  disabled={!input.trim() || loading}
                  className="w-12 h-12 shrink-0 bg-primary text-on-primary-fixed rounded-xl flex items-center justify-center hover:bg-primary-container transition-all shadow-lg active:scale-95 disabled:opacity-40"
                >
                  <span className="material-symbols-outlined" style={{fontVariationSettings: "'FILL' 1"}}>send</span>
                </button>
              </div>
           </div>
           
           {isEmpty && (
              <div className="flex justify-center gap-6 mt-4 opacity-40">
                 <span className="text-[10px] uppercase tracking-widest text-slate-400 font-bold">GPT-4 Omni</span>
                 <span className="text-[10px] uppercase tracking-widest text-slate-400 font-bold">Obsidian Engine 2.1</span>
              </div>
           )}
        </div>
      </div>
    </div>
  );
}
