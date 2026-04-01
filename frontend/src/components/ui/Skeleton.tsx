import { cn } from "@/lib/utils";

interface SkeletonProps {
  className?: string;
}

export function Skeleton({ className }: SkeletonProps) {
  return <div className={cn("skeleton", className)} />;
}

export function SkeletonCard() {
  return (
    <div className="rounded-[10px] border border-border/40 bg-card p-4 space-y-3">
      <div className="flex items-center gap-2">
        <Skeleton className="h-4 w-24" />
        <Skeleton className="h-4 w-12 rounded-full" />
      </div>
      <Skeleton className="h-3 w-full" />
      <Skeleton className="h-3 w-2/3" />
    </div>
  );
}
