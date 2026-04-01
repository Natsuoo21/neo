import type { LucideIcon } from "lucide-react";

interface EmptyStateProps {
  icon: LucideIcon;
  title: string;
  description?: string;
}

export default function EmptyState({ icon: Icon, title, description }: EmptyStateProps) {
  return (
    <div className="flex flex-col items-center justify-center h-full text-center py-16 px-6">
      <div className="p-3 rounded-xl bg-secondary/50 mb-4">
        <Icon className="w-8 h-8 text-muted-foreground/40" />
      </div>
      <p className="text-sm font-medium text-muted-foreground mb-1">{title}</p>
      {description && <p className="text-xs text-muted-foreground/60 max-w-xs">{description}</p>}
    </div>
  );
}
