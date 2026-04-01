import { Search } from "lucide-react";

interface SearchInputProps {
  value: string;
  onChange: (v: string) => void;
  placeholder?: string;
}

export default function SearchInput({ value, onChange, placeholder = "Search..." }: SearchInputProps) {
  return (
    <div className="relative">
      <Search className="absolute left-3 top-1/2 -translate-y-1/2 w-4 h-4 text-muted-foreground" />
      <input
        type="text"
        placeholder={placeholder}
        value={value}
        onChange={(e) => onChange(e.target.value)}
        className="w-full bg-card border border-border rounded-md pl-9 pr-3 py-2 text-[13px] outline-none focus:border-primary/40 focus:ring-2 focus:ring-primary/10 transition-all placeholder:text-muted-foreground"
      />
    </div>
  );
}
