import { useEffect, useState } from "react";
import { Settings, Save, Eye, EyeOff } from "lucide-react";
import { rpc } from "@/lib/rpc";
import { useNeoStore } from "@/stores/neoStore";
import type {
  SettingsGetResult,
  SettingsUpdateResult,
  ProvidersListResult,
} from "@/types/rpc";

export default function SettingsPanel() {
  const setProfile = useNeoStore((s) => s.setProfile);
  const providers = useNeoStore((s) => s.providers);
  const setProviders = useNeoStore((s) => s.setProviders);

  const [name, setName] = useState("");
  const [role, setRole] = useState("");
  const [saveDir, setSaveDir] = useState("");
  const [vaultPath, setVaultPath] = useState("");
  const [saving, setSaving] = useState(false);
  const [saved, setSaved] = useState(false);

  useEffect(() => {
    rpc<SettingsGetResult>("neo.settings.get")
      .then((res) => {
        if (res.profile) {
          setProfile(res.profile);
          setName(res.profile.name);
          setRole(res.profile.role);
          setSaveDir(res.profile.tool_paths?.default_save_dir || "");
          setVaultPath(res.profile.tool_paths?.obsidian_vault || "");
        }
      })
      .catch(console.error);

    rpc<ProvidersListResult>("neo.providers.list")
      .then((res) => setProviders(res.providers))
      .catch(console.error);
  }, [setProfile, setProviders]);

  const handleSave = async () => {
    setSaving(true);
    try {
      await rpc<SettingsUpdateResult>("neo.settings.update", {
        name,
        role,
        tool_paths: {
          default_save_dir: saveDir,
          obsidian_vault: vaultPath,
        },
      });
      setSaved(true);
      setTimeout(() => setSaved(false), 2000);
    } catch (err) {
      console.error("Failed to save settings:", err);
    } finally {
      setSaving(false);
    }
  };

  return (
    <div className="flex flex-col h-full">
      <div className="border-b border-border px-6 py-4">
        <div className="flex items-center gap-2">
          <Settings className="w-5 h-5 text-primary" />
          <h2 className="text-lg font-semibold">Settings</h2>
        </div>
      </div>

      <div className="flex-1 overflow-y-auto px-6 py-6 space-y-8 max-w-2xl">
        {/* Profile */}
        <Section title="Profile">
          <Field label="Name" value={name} onChange={setName} />
          <Field label="Role" value={role} onChange={setRole} placeholder="e.g., Software Engineer" />
        </Section>

        {/* Tool Paths */}
        <Section title="Tool Paths">
          <Field label="Default Save Directory" value={saveDir} onChange={setSaveDir} placeholder="~/Documents/Neo" />
          <Field label="Obsidian Vault" value={vaultPath} onChange={setVaultPath} placeholder="~/Documents/ObsidianVault" />
        </Section>

        {/* API Keys (read-only info) */}
        <Section title="API Keys">
          <p className="text-xs text-muted-foreground mb-3">
            API keys are managed via environment variables (.env.development).
          </p>
          {providers.length > 0 ? (
            <div className="space-y-2">
              {providers.map((p) => (
                <div
                  key={p.tier}
                  className="flex items-center justify-between bg-card border border-border rounded-lg px-3 py-2"
                >
                  <span className="text-sm">{p.tier}</span>
                  <span className="text-xs text-emerald-400">Connected ({p.name})</span>
                </div>
              ))}
            </div>
          ) : (
            <p className="text-sm text-muted-foreground">No providers connected.</p>
          )}
        </Section>

        {/* Hotkey */}
        <Section title="Hotkey">
          <div className="flex items-center justify-between bg-card border border-border rounded-lg px-3 py-2">
            <span className="text-sm">Toggle Floating Bar</span>
            <kbd className="px-2 py-0.5 bg-secondary rounded text-xs text-muted-foreground font-mono">
              Ctrl+Shift+N
            </kbd>
          </div>
        </Section>

        {/* Auto-start */}
        <Section title="Startup">
          <AutoStartToggle />
        </Section>

        {/* Save button */}
        <button
          onClick={handleSave}
          disabled={saving}
          className="flex items-center gap-2 bg-primary text-primary-foreground rounded-lg px-4 py-2 text-sm hover:bg-primary/90 disabled:opacity-50 transition-colors"
        >
          <Save className="w-4 h-4" />
          {saved ? "Saved!" : saving ? "Saving..." : "Save Settings"}
        </button>
      </div>
    </div>
  );
}

function Section({ title, children }: { title: string; children: React.ReactNode }) {
  return (
    <div>
      <h3 className="text-sm font-medium mb-3">{title}</h3>
      <div className="space-y-3">{children}</div>
    </div>
  );
}

function AutoStartToggle() {
  const [enabled, setEnabled] = useState(false);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    (async () => {
      try {
        const { isEnabled } = await import("@tauri-apps/plugin-autostart");
        setEnabled(await isEnabled());
      } catch {
        // Not in Tauri
      } finally {
        setLoading(false);
      }
    })();
  }, []);

  const handleToggle = async () => {
    try {
      if (enabled) {
        const { disable } = await import("@tauri-apps/plugin-autostart");
        await disable();
        setEnabled(false);
      } else {
        const { enable } = await import("@tauri-apps/plugin-autostart");
        await enable();
        setEnabled(true);
      }
    } catch (err) {
      console.error("Auto-start toggle failed:", err);
    }
  };

  return (
    <div className="flex items-center justify-between bg-card border border-border rounded-lg px-3 py-2">
      <div>
        <span className="text-sm">Start with Windows</span>
        <p className="text-xs text-muted-foreground">Launch Neo when you log in</p>
      </div>
      <button
        onClick={handleToggle}
        disabled={loading}
        className={`relative inline-flex h-5 w-9 shrink-0 cursor-pointer rounded-full transition-colors ${
          enabled ? "bg-primary" : "bg-secondary"
        }`}
      >
        <span
          className={`pointer-events-none inline-block h-4 w-4 rounded-full bg-white shadow transform transition-transform mt-0.5 ${
            enabled ? "translate-x-4 ml-0.5" : "translate-x-0.5"
          }`}
        />
      </button>
    </div>
  );
}

function Field({
  label,
  value,
  onChange,
  placeholder,
  type = "text",
}: {
  label: string;
  value: string;
  onChange: (v: string) => void;
  placeholder?: string;
  type?: string;
}) {
  const [show, setShow] = useState(type !== "password");

  return (
    <div>
      <label className="text-xs text-muted-foreground mb-1 block">{label}</label>
      <div className="relative">
        <input
          type={type === "password" && !show ? "password" : "text"}
          value={value}
          onChange={(e) => onChange(e.target.value)}
          placeholder={placeholder}
          className="w-full bg-card border border-border rounded-lg px-3 py-2 text-sm outline-none focus:border-primary/50 transition-colors placeholder:text-muted-foreground"
        />
        {type === "password" && (
          <button
            type="button"
            onClick={() => setShow(!show)}
            className="absolute right-2 top-1/2 -translate-y-1/2 text-muted-foreground hover:text-foreground"
          >
            {show ? <EyeOff className="w-4 h-4" /> : <Eye className="w-4 h-4" />}
          </button>
        )}
      </div>
    </div>
  );
}
