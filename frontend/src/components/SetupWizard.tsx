import { useState } from "react";
import { ArrowRight, Check } from "lucide-react";
import { cn } from "@/lib/utils";
import { rpc } from "@/lib/rpc";
import type { SettingsUpdateResult } from "@/types/rpc";

interface Props {
  onComplete: () => void;
}

const STEPS = ["Welcome", "Profile", "Paths", "Done"] as const;

const INPUT_CLASS =
  "w-full bg-background border border-border rounded-md px-3 py-2.5 text-[13px] outline-none focus:border-primary/40 focus:ring-2 focus:ring-primary/10 transition-all placeholder:text-muted-foreground";

export default function SetupWizard({ onComplete }: Props) {
  const [step, setStep] = useState(0);
  const [name, setName] = useState("");
  const [role, setRole] = useState("");
  const [saveDir, setSaveDir] = useState("~/Documents/Neo");
  const [vaultPath, setVaultPath] = useState("");

  const handleNext = async () => {
    if (step === 2) {
      // Save settings before finishing
      try {
        await rpc<SettingsUpdateResult>("neo.settings.update", {
          name: name || "User",
          role,
          tool_paths: {
            default_save_dir: saveDir,
            obsidian_vault: vaultPath,
          },
        });
      } catch (err) {
        console.error("Failed to save setup:", err);
      }
    }

    if (step < STEPS.length - 1) {
      setStep(step + 1);
    } else {
      // Mark setup complete
      try {
        const { load } = await import("@tauri-apps/plugin-store");
        const store = await load("neo-settings.json");
        await store.set("setup_complete", true);
        await store.save();
      } catch {
        // Not in Tauri — skip
      }
      onComplete();
    }
  };

  return (
    <div className="h-screen flex items-center justify-center bg-background">
      <div className="w-full max-w-md mx-auto px-6">
        {/* Progress dots */}
        <div className="flex items-center justify-center gap-2 mb-8">
          {STEPS.map((_, i) => (
            <div
              key={i}
              className={cn(
                "h-2 rounded-full transition-all duration-300",
                i === step
                  ? "w-6 bg-primary"
                  : i < step
                    ? "w-2 bg-primary"
                    : "w-2 bg-secondary",
              )}
            />
          ))}
        </div>

        {/* Step content */}
        <div className="bg-card border border-border/60 rounded-[18px] p-8 space-y-6 shadow-elevated">
          {step === 0 && <StepWelcome />}
          {step === 1 && (
            <StepProfile
              name={name}
              setName={setName}
              role={role}
              setRole={setRole}
            />
          )}
          {step === 2 && (
            <StepPaths
              saveDir={saveDir}
              setSaveDir={setSaveDir}
              vaultPath={vaultPath}
              setVaultPath={setVaultPath}
            />
          )}
          {step === 3 && <StepDone name={name} />}

          <button
            onClick={handleNext}
            className="flex items-center justify-center gap-2 w-full bg-primary text-primary-foreground rounded-lg py-3 text-[13px] font-semibold hover:brightness-110 active:scale-[0.98] transition-interaction"
          >
            {step === STEPS.length - 1 ? (
              <>
                <Check className="w-4 h-4" /> Get Started
              </>
            ) : (
              <>
                Continue <ArrowRight className="w-4 h-4" />
              </>
            )}
          </button>
        </div>
      </div>
    </div>
  );
}

function StepWelcome() {
  return (
    <div className="text-center space-y-3">
      <h1 className="text-2xl font-bold tracking-tight">Welcome to Neo</h1>
      <p className="text-muted-foreground text-[13px] leading-relaxed">
        Your personal intelligence agent. Let's set up a few things to get started.
      </p>
    </div>
  );
}

function StepProfile({
  name,
  setName,
  role,
  setRole,
}: {
  name: string;
  setName: (v: string) => void;
  role: string;
  setRole: (v: string) => void;
}) {
  return (
    <div className="space-y-4">
      <h2 className="text-[15px] font-semibold tracking-tight">Who are you?</h2>
      <div>
        <label className="text-xs text-muted-foreground mb-1 block">Your Name</label>
        <input
          type="text"
          value={name}
          onChange={(e) => setName(e.target.value)}
          placeholder="e.g., Andre"
          className={INPUT_CLASS}
        />
      </div>
      <div>
        <label className="text-xs text-muted-foreground mb-1 block">Your Role</label>
        <input
          type="text"
          value={role}
          onChange={(e) => setRole(e.target.value)}
          placeholder="e.g., Software Engineer"
          className={INPUT_CLASS}
        />
      </div>
    </div>
  );
}

function StepPaths({
  saveDir,
  setSaveDir,
  vaultPath,
  setVaultPath,
}: {
  saveDir: string;
  setSaveDir: (v: string) => void;
  vaultPath: string;
  setVaultPath: (v: string) => void;
}) {
  return (
    <div className="space-y-4">
      <h2 className="text-[15px] font-semibold tracking-tight">File Paths</h2>
      <p className="text-xs text-muted-foreground">
        Where should Neo save files? You can change these later in Settings.
      </p>
      <div>
        <label className="text-xs text-muted-foreground mb-1 block">Default Save Directory</label>
        <input
          type="text"
          value={saveDir}
          onChange={(e) => setSaveDir(e.target.value)}
          placeholder="~/Documents/Neo"
          className={INPUT_CLASS}
        />
      </div>
      <div>
        <label className="text-xs text-muted-foreground mb-1 block">
          Obsidian Vault Path (optional)
        </label>
        <input
          type="text"
          value={vaultPath}
          onChange={(e) => setVaultPath(e.target.value)}
          placeholder="~/Documents/ObsidianVault"
          className={INPUT_CLASS}
        />
      </div>
    </div>
  );
}

function StepDone({ name }: { name: string }) {
  return (
    <div className="text-center space-y-3">
      <h2 className="text-2xl font-bold tracking-tight">You're all set!</h2>
      <p className="text-muted-foreground text-[13px] leading-relaxed">
        {name ? `Welcome, ${name}! ` : ""}Neo is ready. Press{" "}
        <kbd className="px-1.5 py-0.5 bg-secondary rounded-[var(--radius-sm)] text-xs font-mono">
          Ctrl+Shift+N
        </kbd>{" "}
        anywhere to open the command bar.
      </p>
    </div>
  );
}
