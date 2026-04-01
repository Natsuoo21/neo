import { cn } from "@/lib/utils";

interface ToggleProps {
  enabled: boolean;
  onToggle: () => void;
  disabled?: boolean;
  size?: "sm" | "md";
}

export default function Toggle({ enabled, onToggle, disabled, size = "sm" }: ToggleProps) {
  const isSmall = size === "sm";
  return (
    <button
      onClick={(e) => { e.stopPropagation(); onToggle(); }}
      disabled={disabled}
      className={cn(
        "relative inline-flex shrink-0 cursor-pointer rounded-full transition-interaction",
        isSmall ? "h-5 w-9" : "h-6 w-11",
        enabled ? "bg-primary" : "bg-secondary",
        disabled && "opacity-40 cursor-not-allowed",
      )}
    >
      <span
        className={cn(
          "pointer-events-none inline-block rounded-full bg-white shadow-sm transform transition-transform",
          isSmall ? "h-4 w-4 mt-0.5" : "h-5 w-5 mt-0.5",
          enabled
            ? isSmall ? "translate-x-[18px]" : "translate-x-[22px]"
            : "translate-x-0.5",
        )}
      />
    </button>
  );
}
