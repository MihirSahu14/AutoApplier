import { useEffect, useState } from "react";
import { useQuery, useQueryClient } from "@tanstack/react-query";
import { Link } from "react-router-dom";
import { api, type Profile } from "../api";
import { Field, inputCls } from "../components/Field";
import { useToast } from "../components/Toast";

export function Settings() {
  const toast = useToast();
  const qc = useQueryClient();
  const { data } = useQuery({ queryKey: ["profile"], queryFn: api.getProfile });
  const [draft, setDraft] = useState<Profile | null>(null);
  const [keys, setKeys] = useState({ anthropic: "", hunter: "", apollo: "", serpapi: "" });
  useEffect(() => { if (data) setDraft(structuredClone(data)); }, [data?.contact.name]);
  if (!draft) return <div className="text-slate-400">Loading…</div>;

  const save = async () => {
    try {
      await api.updateProfile({
        ...draft,
        api_keys: keys,
      });
      qc.invalidateQueries({ queryKey: ["profile"] });
      qc.invalidateQueries({ queryKey: ["setup-status"] });
      toast("Saved", "ok");
    } catch (e: any) { toast(`Failed: ${e.message}`, "err"); }
  };

  const uploadResume = async (f: File) => {
    try {
      const res = await api.uploadResume(f);
      toast(`Uploaded ${res.filename}`, "ok");
      qc.invalidateQueries({ queryKey: ["profile"] });
    } catch (e: any) { toast(`Upload failed: ${e.message}`, "err"); }
  };

  return (
    <div className="max-w-4xl mx-auto">
      <Link to="/" className="text-sm text-slate-500 hover:text-slate-900">← back</Link>
      <h1 className="text-2xl font-bold mt-3 mb-6">Settings</h1>

      <section className="bg-white border border-slate-200 rounded shadow-sm p-5 mb-4">
        <h2 className="font-semibold mb-3">Contact</h2>
        <div className="grid md:grid-cols-2 gap-3">
          {Object.keys(draft.contact).map((k) => (
            <Field key={k} label={k}>
              <input className={inputCls}
                     value={(draft.contact as any)[k] || ""}
                     onChange={(e) => setDraft({ ...draft, contact: { ...draft.contact, [k]: e.target.value } })} />
            </Field>
          ))}
        </div>
      </section>

      <section className="bg-white border border-slate-200 rounded shadow-sm p-5 mb-4">
        <h2 className="font-semibold mb-3">Background</h2>
        <Field label="Resume PDF">
          <div className="border-2 border-dashed border-slate-300 rounded p-4 text-center text-sm">
            <input type="file" accept="application/pdf"
                   onChange={(e) => e.target.files?.[0] && uploadResume(e.target.files[0])} />
            {draft.resume_pdf_filename && (
              <div className="mt-2 text-emerald-700">✓ {draft.resume_pdf_filename}</div>
            )}
          </div>
        </Field>
        <Field label="Experience summary" hint="Used if no resume is uploaded.">
          <textarea rows={8} className={inputCls}
                    value={draft.experience_summary}
                    onChange={(e) => setDraft({ ...draft, experience_summary: e.target.value })} />
        </Field>
      </section>

      <section className="bg-white border border-slate-200 rounded shadow-sm p-5 mb-4">
        <h2 className="font-semibold mb-3">Targets</h2>
        <div className="grid md:grid-cols-2 gap-3">
          <Field label="Target roles (comma-separated)">
            <input className={inputCls} value={draft.targets.roles.join(", ")}
                   onChange={(e) => setDraft({ ...draft, targets: { ...draft.targets, roles: e.target.value.split(",").map(s => s.trim()).filter(Boolean) } })} />
          </Field>
          <Field label="Min salary (USD)">
            <input type="number" className={inputCls} value={draft.targets.salary_min_usd}
                   onChange={(e) => setDraft({ ...draft, targets: { ...draft.targets, salary_min_usd: +e.target.value } })} />
          </Field>
          <Field label="Company size min">
            <input type="number" className={inputCls} value={draft.targets.company_size_min}
                   onChange={(e) => setDraft({ ...draft, targets: { ...draft.targets, company_size_min: +e.target.value } })} />
          </Field>
          <Field label="Company size max">
            <input type="number" className={inputCls} value={draft.targets.company_size_max}
                   onChange={(e) => setDraft({ ...draft, targets: { ...draft.targets, company_size_max: +e.target.value } })} />
          </Field>
          <Field label="Locations OK (comma-separated)">
            <input className={inputCls} value={draft.targets.locations_ok.join(", ")}
                   onChange={(e) => setDraft({ ...draft, targets: { ...draft.targets, locations_ok: e.target.value.split(",").map(s => s.trim()).filter(Boolean) } })} />
          </Field>
          <Field label="Preferred locations (comma-separated)">
            <input className={inputCls} value={draft.targets.locations_preferred.join(", ")}
                   onChange={(e) => setDraft({ ...draft, targets: { ...draft.targets, locations_preferred: e.target.value.split(",").map(s => s.trim()).filter(Boolean) } })} />
          </Field>
        </div>
      </section>

      <section className="bg-white border border-slate-200 rounded shadow-sm p-5 mb-4">
        <h2 className="font-semibold mb-3">Visa & disqualifiers</h2>
        <div className="grid gap-3">
          <Field label="Work authorization status">
            <input className={inputCls} value={draft.visa.status}
                   onChange={(e) => setDraft({ ...draft, visa: { ...draft.visa, status: e.target.value } })} />
          </Field>
          <label className="flex items-center gap-2 text-sm">
            <input type="checkbox" checked={draft.visa.needs_sponsorship}
                   onChange={(e) => setDraft({ ...draft, visa: { ...draft.visa, needs_sponsorship: e.target.checked } })} />
            Needs visa sponsorship (now or eventually)
          </label>
          <Field label="Auto-disqualify if these phrases appear in the JD (one per line)">
            <textarea rows={7} className={inputCls}
                      value={draft.visa.disqualify_if.join("\n")}
                      onChange={(e) => setDraft({ ...draft, visa: { ...draft.visa, disqualify_if: e.target.value.split("\n").map(s => s.trim()).filter(Boolean) } })} />
          </Field>
        </div>
      </section>

      <CompaniesEditor />

      <section className="bg-white border border-slate-200 rounded shadow-sm p-5 mb-4">
        <h2 className="font-semibold mb-3">API keys</h2>
        <p className="text-xs text-slate-500 mb-3">Leave blank to keep the existing key.</p>
        <div className="grid md:grid-cols-2 gap-3">
          {(["anthropic","hunter","apollo","serpapi"] as const).map((k) => (
            <Field key={k} label={k} hint={`Current: ${(draft.api_keys as any)[k] || "not set"}`}>
              <input type="password" className={inputCls}
                     value={(keys as any)[k]}
                     onChange={(e) => setKeys({ ...keys, [k]: e.target.value })} />
            </Field>
          ))}
        </div>
      </section>

      <div className="flex justify-end">
        <button onClick={save}
                className="px-4 py-2 text-sm rounded bg-emerald-600 text-white">
          Save changes
        </button>
      </div>
    </div>
  );
}

function CompaniesEditor() {
  const toast = useToast();
  const qc = useQueryClient();
  const { data } = useQuery({ queryKey: ["companies"], queryFn: api.getCompanies });
  const [gh, setGh] = useState("");
  const [lv, setLv] = useState("");
  const [as_, setAs] = useState("");
  useEffect(() => {
    if (!data) return;
    setGh(data.greenhouse.join("\n"));
    setLv(data.lever.join("\n"));
    setAs(data.ashby.join("\n"));
  }, [data?.greenhouse?.length]);

  const save = async () => {
    try {
      const toList = (s: string) => s.split("\n").map(x => x.trim()).filter(Boolean);
      await api.setCompanies({
        greenhouse: toList(gh), lever: toList(lv), ashby: toList(as_),
      });
      qc.invalidateQueries({ queryKey: ["companies"] });
      toast("Saved companies", "ok");
    } catch (e: any) { toast(e.message, "err"); }
  };

  return (
    <section className="bg-white border border-slate-200 rounded shadow-sm p-5 mb-4">
      <h2 className="font-semibold mb-1">Companies to scrape</h2>
      <p className="text-xs text-slate-500 mb-3">
        One slug per line. The slug is what you see in the company's public job-board URL:
        <code className="ml-1 bg-slate-100 px-1 rounded">jobs.lever.co/<b>slug</b></code>,
        <code className="ml-1 bg-slate-100 px-1 rounded">boards.greenhouse.io/<b>slug</b></code>,
        <code className="ml-1 bg-slate-100 px-1 rounded">jobs.ashbyhq.com/<b>slug</b></code>.
      </p>
      <div className="grid md:grid-cols-3 gap-3">
        <Field label="Greenhouse">
          <textarea rows={10} className={inputCls} value={gh} onChange={(e) => setGh(e.target.value)} />
        </Field>
        <Field label="Lever">
          <textarea rows={10} className={inputCls} value={lv} onChange={(e) => setLv(e.target.value)} />
        </Field>
        <Field label="Ashby">
          <textarea rows={10} className={inputCls} value={as_} onChange={(e) => setAs(e.target.value)} />
        </Field>
      </div>
      <div className="flex justify-end mt-3">
        <button onClick={save}
                className="px-3 py-1.5 text-sm rounded bg-slate-900 text-white">
          Save companies
        </button>
      </div>
    </section>
  );
}
