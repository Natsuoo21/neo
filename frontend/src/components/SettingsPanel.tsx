import { useEffect, useState } from "react";
import { rpc } from "@/lib/rpc";
import { useNeoStore } from "@/stores/neoStore";
import Toggle from "./ui/Toggle";
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
  const [defaultProvider, setDefaultProvider] = useState("");
  const [browserHeadless, setBrowserHeadless] = useState(true);
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
          setBrowserHeadless(res.profile.preferences?.browser_headless !== "false");
          setDefaultProvider(res.profile.preferences?.default_provider || "");
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
        preferences: {
          browser_headless: String(browserHeadless),
          default_provider: defaultProvider,
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
    <div className="flex flex-col h-full font-body">
      <div className="flex items-center gap-3 px-3 md:px-6 py-4 border-b border-white/5">
        <span className="material-symbols-outlined text-primary">settings</span>
        <h2 className="text-lg font-headline font-bold tracking-tight">Settings</h2>
      </div>

      <div className="flex-1 overflow-y-auto px-3 md:px-6 py-6 space-y-8 max-w-2xl">
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
                  className="flex items-center justify-between bg-surface-container border border-white/5 rounded-2xl px-4 py-3 shadow-sm"
                >
                  <span className="text-[13px] font-mono text-on-surface">{p.tier}</span>
                  <div className="flex items-center gap-2">
                    <span className="w-2 h-2 rounded-full bg-emerald-500 animate-pulse"></span>
                    <span className="text-xs text-emerald-400/80 font-bold uppercase tracking-wider">Connected ({p.name})</span>
                  </div>
                </div>
              ))}
            </div>
          ) : (
            <p className="text-[13px] text-muted-foreground">No providers connected.</p>
          )}
        </Section>

        {/* Default Model */}
        <Section title="Default Model">
          <p className="text-xs text-muted-foreground mb-1">
            Which provider handles complex or unknown tasks.
          </p>
          <div className="relative group">
            <select
              value={defaultProvider}
              onChange={(e) => setDefaultProvider(e.target.value)}
              className="w-full bg-surface-container-highest border border-white/10 rounded-xl px-4 py-3 text-sm text-on-surface outline-none focus:border-primary/40 focus:ring-2 focus:ring-primary/10 transition-all appearance-none cursor-pointer"
              style={{ colorScheme: "dark" }}
            >
              <option value="" className="bg-surface-container text-on-surface">Automatic (recommended)</option>
              {providers.map((p) => (
                <option key={p.tier} value={p.tier} className="bg-surface-container text-on-surface">
                  {p.tier} — {p.name}
                </option>
              ))}
            </select>
            <div className="absolute right-4 top-1/2 -translate-y-1/2 pointer-events-none text-slate-500">
              <span className="material-symbols-outlined text-[20px]">expand_more</span>
            </div>
          </div>
        </Section>

        {/* Browser */}
        <Section title="Browser">
          <div className="flex items-center justify-between bg-surface-container-low/40 border border-white/5 rounded-2xl px-4 py-3.5">
            <div>
              <span className="text-sm font-semibold text-on-surface">Headless Mode</span>
              <p className="text-xs text-on-surface-variant/60">
                Run browser invisibly in the background
              </p>
            </div>
            <Toggle enabled={browserHeadless} onToggle={() => setBrowserHeadless(!browserHeadless)} />
          </div>
        </Section>

        {/* Hotkey */}
        <Section title="Hotkey">
          <div className="flex items-center justify-between bg-surface-container-low/40 border border-white/5 rounded-2xl px-4 py-3.5">
            <span className="text-sm font-semibold text-on-surface">Toggle Floating Bar</span>
            <kbd className="px-3 py-1 bg-white/5 rounded-lg text-[11px] text-on-surface-variant font-mono border border-white/5">
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
          className="flex items-center justify-center gap-3 bg-gradient-to-r from-primary to-primary-dim text-on-primary-fixed rounded-full px-8 py-4 text-sm font-bold shadow-lg hover:shadow-primary/20 active:scale-95 disabled:opacity-40 transition-all"
        >
          <span className="material-symbols-outlined text-[20px]">{saved ? "check_circle" : "save"}</span>
          <span className="uppercase tracking-widest">{saved ? "Saved!" : saving ? "Saving..." : "Save Settings"}</span>
        </button>
      </div>
    </div>
  );
}

function Section({ title, children }: { title: string; children: React.ReactNode }) {
  return (
    <div className="mb-6">
      <h3 className="text-xs font-bold text-slate-500 tracking-[0.2em] uppercase mb-4">{title}</h3>
      <div className="space-y-4">{children}</div>
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
    <div className="flex items-center justify-between bg-surface-container-low/40 border border-white/5 rounded-2xl px-4 py-3.5">
      <div>
        <span className="text-sm font-semibold text-on-surface">Start with Windows</span>
        <p className="text-xs text-on-surface-variant/60">Launch Neo when you log in</p>
      </div>
      <Toggle enabled={enabled} onToggle={handleToggle} disabled={loading} />
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
    <div className="space-y-1.5">
      <label className="text-[10px] font-bold text-slate-500 tracking-wider uppercase ml-1">{label}</label>
      <div className="relative group">
        <input
          type={type === "password" && !show ? "password" : "text"}
          value={value}
          onChange={(e) => onChange(e.target.value)}
          placeholder={placeholder}
          className="w-full bg-surface-container-highest border border-white/10 rounded-xl px-4 py-3 text-sm text-on-surface outline-none focus:border-primary/40 focus:ring-2 focus:ring-primary/10 transition-all placeholder:text-on-surface-variant/40"
        />
        {type === "password" && (
          <button
            type="button"
            onClick={() => setShow(!show)}
            className="absolute right-4 top-1/2 -translate-y-1/2 text-on-surface-variant/60 hover:text-on-surface transition-colors"
          >
            <span className="material-symbols-outlined text-[20px]">{show ? "visibility_off" : "visibility"}</span>
          </button>
        )}
      </div>
    </div>
  );
}
