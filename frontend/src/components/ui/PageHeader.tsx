import type { LucideIcon } from "lucide-react";

interface PageHeaderProps {
  icon: LucideIcon;
  title: string;
  subtitle?: string;
  children?: React.ReactNode;
}

export default function PageHeader({ icon: Icon, title, subtitle, children }: PageHeaderProps) {
  return (
    <div className="border-b border-border/60 px-6 py-4">
      <div className="flex items-center justify-between">
        <div className="flex items-center gap-2.5">
          <Icon className="w-5 h-5 text-primary" />
          <h2 className="text-[15px] font-semibold tracking-tight">{title}</h2>
          {subtitle && <span className="text-xs text-muted-foreground">{subtitle}</span>}
        </div>
        {children && <div className="flex items-center gap-2">{children}</div>}
      </div>
    </div>
  );
}
