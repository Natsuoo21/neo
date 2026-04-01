import { useState, useCallback } from "react";
import ReactMarkdown from "react-markdown";
import remarkGfm from "remark-gfm";
import { Prism as SyntaxHighlighter } from "react-syntax-highlighter";
import { oneDark } from "react-syntax-highlighter/dist/esm/styles/prism";
import { Copy, Check } from "lucide-react";
import { cn } from "@/lib/utils";
import type { ChatMessage } from "@/stores/neoStore";

interface Props {
  message: ChatMessage;
}

export default function MessageBubble({ message }: Props) {
  const isUser = message.role === "user";
  const [copied, setCopied] = useState(false);

  const copyMessage = useCallback(() => {
    navigator.clipboard.writeText(message.content).then(() => {
      setCopied(true);
      setTimeout(() => setCopied(false), 1500);
    });
  }, [message.content]);

  return (
    <div className={cn("flex gap-3 py-3 animate-fade-in-up group/msg", isUser ? "justify-end" : "justify-start")}>
      <div
        className={cn(
          "relative max-w-[80%] rounded-2xl px-4 py-3 text-[13px] select-text",
          isUser
            ? "bg-primary/90 text-primary-foreground rounded-br-sm shadow-card"
            : "bg-card border border-border/60 rounded-bl-sm shadow-card",
        )}
      >
        {/* Hover copy button */}
        <button
          onClick={copyMessage}
          className={cn(
            "absolute -top-2 -right-2 p-1.5 rounded-lg bg-card border border-border/60 shadow-elevated",
            "opacity-0 group-hover/msg:opacity-100 transition-all duration-150",
            "hover:bg-accent active:scale-90 z-10",
            copied && "opacity-100",
          )}
          title="Copy message"
        >
          {copied ? (
            <Check className="w-3 h-3 text-emerald-400" />
          ) : (
            <Copy className="w-3 h-3 text-muted-foreground" />
          )}
        </button>

        {isUser ? (
          <p className="whitespace-pre-wrap">{message.content}</p>
        ) : (
          <div className="prose prose-invert prose-sm max-w-none">
            <ReactMarkdown
              remarkPlugins={[remarkGfm]}
              components={{
                code({ className, children, ...props }) {
                  const match = /language-(\w+)/.exec(className || "");
                  const code = String(children).replace(/\n$/, "");
                  if (match) {
                    return (
                      <CodeBlock language={match[1]} code={code} />
                    );
                  }
                  return (
                    <code className="bg-background/50 rounded px-1.5 py-0.5 text-xs" {...props}>
                      {children}
                    </code>
                  );
                },
              }}
            >
              {message.content}
            </ReactMarkdown>
          </div>
        )}

        {/* Metadata footer */}
        {!isUser && (message.model || message.tool || message.duration) && (
          <div className="flex items-center gap-2 mt-2 pt-2 border-t border-border/50 text-[10px] text-muted-foreground select-none">
            {message.model && <span className="font-mono">{message.model}</span>}
            {message.tool && (
              <>
                <span className="opacity-30">|</span>
                <span className="font-mono">{message.tool}</span>
              </>
            )}
            {message.duration !== undefined && (
              <>
                <span className="opacity-30">|</span>
                <span className="font-mono">{message.duration}ms</span>
              </>
            )}
          </div>
        )}
      </div>
    </div>
  );
}

function CodeBlock({ language, code }: { language: string; code: string }) {
  const [copied, setCopied] = useState(false);

  const handleCopy = () => {
    navigator.clipboard.writeText(code).then(() => {
      setCopied(true);
      setTimeout(() => setCopied(false), 1500);
    });
  };

  return (
    <div className="relative group/code my-2">
      {/* Language label + copy button */}
      <div className="flex items-center justify-between px-3 py-1.5 bg-background/70 rounded-t-lg border-b border-border/30">
        <span className="text-[10px] font-mono text-muted-foreground uppercase tracking-wider">{language}</span>
        <button
          onClick={handleCopy}
          className="flex items-center gap-1 px-1.5 py-0.5 rounded text-[10px] text-muted-foreground hover:text-foreground hover:bg-accent/60 active:scale-95 transition-interaction"
        >
          {copied ? (
            <>
              <Check className="w-3 h-3 text-emerald-400" />
              <span className="text-emerald-400">Copied</span>
            </>
          ) : (
            <>
              <Copy className="w-3 h-3" />
              <span>Copy</span>
            </>
          )}
        </button>
      </div>
      <SyntaxHighlighter
        style={oneDark}
        language={language}
        PreTag="div"
        className="!rounded-t-none rounded-b-lg !bg-background/50 text-xs !mt-0 !pt-3"
      >
        {code}
      </SyntaxHighlighter>
    </div>
  );
}
