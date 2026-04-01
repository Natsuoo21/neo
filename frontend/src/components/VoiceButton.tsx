import { useState } from "react";
import { Mic, MicOff } from "lucide-react";
import { rpc } from "@/lib/rpc";
import { useNeoStore } from "@/stores/neoStore";
import { cn } from "@/lib/utils";

export default function VoiceButton() {
  const voiceActive = useNeoStore((s) => s.voiceActive);
  const setVoiceActive = useNeoStore((s) => s.setVoiceActive);
  const [loading, setLoading] = useState(false);

  const toggleVoice = async () => {
    setLoading(true);
    try {
      if (voiceActive) {
        await rpc("neo.voice.stop");
        setVoiceActive(false);
      } else {
        await rpc("neo.voice.start", { mode: "record" });
        setVoiceActive(true);
      }
    } catch (err) {
      console.error("Voice toggle failed:", err);
    } finally {
      setLoading(false);
    }
  };

  return (
    <button
      onClick={toggleVoice}
      disabled={loading}
      className={cn(
        "shrink-0 w-10 h-10 rounded-lg flex items-center justify-center active:scale-95 transition-interaction",
        voiceActive
          ? "bg-destructive text-destructive-foreground ring-2 ring-destructive/30 ring-offset-2 ring-offset-background animate-pulse"
          : "bg-card border border-border text-muted-foreground hover:bg-accent/60 hover:text-foreground",
        loading && "opacity-40 cursor-not-allowed",
      )}
      title={voiceActive ? "Stop recording" : "Start voice input"}
    >
      {voiceActive ? (
        <MicOff className="w-4 h-4" />
      ) : (
        <Mic className="w-4 h-4" />
      )}
    </button>
  );
}
