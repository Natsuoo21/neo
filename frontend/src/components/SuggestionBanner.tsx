import { useEffect } from "react";
import { Lightbulb, Check, X } from "lucide-react";
import { rpc } from "@/lib/rpc";
import { useNeoStore } from "@/stores/neoStore";
import type { SuggestionListResult } from "@/types/rpc";

export default function SuggestionBanner() {
  const suggestions = useNeoStore((s) => s.suggestions);
  const setSuggestions = useNeoStore((s) => s.setSuggestions);
  const dismissSuggestion = useNeoStore((s) => s.dismissSuggestion);
  const connected = useNeoStore((s) => s.connected);

  useEffect(() => {
    if (!connected) return;
    rpc<SuggestionListResult>("neo.suggestions.list")
      .then((res) => setSuggestions(res.suggestions))
      .catch(console.error);
  }, [connected, setSuggestions]);

  const handleAccept = async (id: number) => {
    try {
      await rpc("neo.suggestions.accept", { id });
      dismissSuggestion(id);
    } catch (err) {
      console.error("Failed to accept suggestion:", err);
    }
  };

  const handleDismiss = async (id: number) => {
    try {
      await rpc("neo.suggestions.dismiss", { id });
      dismissSuggestion(id);
    } catch (err) {
      console.error("Failed to dismiss suggestion:", err);
    }
  };

  if (suggestions.length === 0) return null;

  const suggestion = suggestions[0];

  return (
    <div className="mx-3 md:mx-6 mt-2 rounded-lg border border-primary/15 bg-primary/5 px-4 py-3 flex items-center gap-3 animate-fade-in-up">
      <Lightbulb className="w-4 h-4 text-primary shrink-0" />
      <p className="flex-1 text-[13px] text-foreground">{suggestion.message}</p>
      <button
        onClick={() => handleAccept(suggestion.id)}
        className="flex items-center gap-1 px-2.5 py-1 text-xs font-medium rounded-md bg-primary text-primary-foreground hover:brightness-110 active:scale-95 transition-interaction"
      >
        <Check className="w-3 h-3" />
        Automate
      </button>
      <button
        onClick={() => handleDismiss(suggestion.id)}
        className="p-1 rounded-md text-muted-foreground hover:bg-accent/60 hover:text-foreground active:scale-95 transition-interaction"
      >
        <X className="w-3.5 h-3.5" />
      </button>
    </div>
  );
}
