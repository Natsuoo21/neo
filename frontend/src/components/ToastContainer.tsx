import { useNeoStore } from "@/stores/neoStore";
import { X, CheckCircle, AlertCircle, Info } from "lucide-react";
import { cn } from "@/lib/utils";

const ICONS = {
  success: CheckCircle,
  error: AlertCircle,
  info: Info,
};

const COLORS = {
  success: "border-emerald-500/30 bg-emerald-500/10 text-emerald-300",
  error: "border-red-500/30 bg-red-500/10 text-red-300",
  info: "border-primary/30 bg-primary/10 text-primary",
};

export default function ToastContainer() {
  const toasts = useNeoStore((s) => s.toasts);
  const removeToast = useNeoStore((s) => s.removeToast);

  if (toasts.length === 0) return null;

  return (
    <div className="fixed bottom-6 right-6 z-50 flex flex-col gap-2 pointer-events-none">
      {toasts.map((toast) => {
        const Icon = ICONS[toast.type];
        return (
          <div
            key={toast.id}
            className={cn(
              "pointer-events-auto flex items-center gap-3 px-4 py-3 rounded-xl border backdrop-blur-xl shadow-float animate-fade-in-up",
              "max-w-sm",
              COLORS[toast.type],
            )}
          >
            <Icon className="w-4 h-4 shrink-0" />
            <span className="text-sm font-body flex-1">{toast.message}</span>
            <button
              onClick={() => removeToast(toast.id)}
              className="shrink-0 p-0.5 rounded hover:bg-white/10 transition-colors active:scale-90"
            >
              <X className="w-3.5 h-3.5 opacity-60" />
            </button>
          </div>
        );
      })}
    </div>
  );
}
