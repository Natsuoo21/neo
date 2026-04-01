import { useEffect, useState } from "react";
import { AlertTriangle } from "lucide-react";
import { rpc } from "@/lib/rpc";
import { useNeoStore } from "@/stores/neoStore";

export default function ConfirmationDialog() {
  const confirmations = useNeoStore((s) => s.pendingConfirmations);
  const removeConfirmation = useNeoStore((s) => s.removePendingConfirmation);

  if (confirmations.length === 0) return null;

  const current = confirmations[0];

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/50">
      <ConfirmationCard
        key={current.id}
        confirmation={current}
        onResolve={(approved) => {
          rpc("neo.automation.confirm", {
            confirmation_id: current.id,
            approved,
          }).catch(console.error);
          removeConfirmation(current.id);
        }}
      />
    </div>
  );
}

function ConfirmationCard({
  confirmation,
  onResolve,
}: {
  confirmation: { id: string; action_description: string; timeout_s?: number };
  onResolve: (approved: boolean) => void;
}) {
  const timeout = confirmation.timeout_s ?? 60;
  const [remaining, setRemaining] = useState(timeout);

  useEffect(() => {
    const interval = setInterval(() => {
      setRemaining((r) => {
        if (r <= 1) {
          onResolve(false);
          return 0;
        }
        return r - 1;
      });
    }, 1000);
    return () => clearInterval(interval);
  }, [onResolve]);

  return (
    <div className="bg-card border border-border rounded-2xl p-6 max-w-md w-full mx-4 shadow-xl">
      <div className="flex items-center gap-3 mb-4">
        <div className="p-2 bg-amber-500/10 rounded-full">
          <AlertTriangle className="w-5 h-5 text-amber-500" />
        </div>
        <h3 className="font-semibold text-sm">Confirmation Required</h3>
      </div>

      <p className="text-sm text-muted-foreground mb-6">
        {confirmation.action_description}
      </p>

      <div className="flex items-center justify-between">
        <span className="text-xs text-muted-foreground">
          Auto-deny in {remaining}s
        </span>
        <div className="flex gap-2">
          <button
            onClick={() => onResolve(false)}
            className="px-4 py-2 text-sm rounded-lg border border-border hover:bg-secondary transition-colors"
          >
            Deny
          </button>
          <button
            onClick={() => onResolve(true)}
            className="px-4 py-2 text-sm rounded-lg bg-primary text-primary-foreground hover:bg-primary/90 transition-colors"
          >
            Approve
          </button>
        </div>
      </div>
    </div>
  );
}
