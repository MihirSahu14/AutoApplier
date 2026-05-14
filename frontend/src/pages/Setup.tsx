import { useEffect, useState } from "react";
import { useNavigate } from "react-router-dom";
import { useQuery, useQueryClient } from "@tanstack/react-query";
import { api, saveProfileLS } from "../api";
import { Field, inputCls } from "../components/Field";
import { useToast } from "../components/Toast";

type Step = 1 | 2 | 3 | 4 | 5;

export function Setup() {
  const nav = useNavigate();
  const toast = useToast();
  const qc = useQueryClient();
  const { data: profile } = useQuery({ queryKey: ["profile"], queryFn: api.getProfile });
  const [step, setStep] = useState<Step>(1);

  // local form state
  const [contact, setContact] = useState({
    name: "", email: "", phone: "", linkedin: "", github: "", portfolio: "", location: "",
  });
  const [bg, setBg] = useState({ mode: "upload" as "upload" | "describe", summary: "", filename: "" });
  const [targets, setTargets] = useState({
    rolesText: "",
    company_size_min: 0,
    company_size_max: 100000,
    locationsOk: "united states, usa, remote (us)",
    locationsPreferred: "",
    salary_min_usd: 0,
  });
  const [visa, setVisa] = useState({
    status: "",
    needs_sponsorship: false,
    disqualifiers: [
      "us citizen required", "us citizenship required",
      "active security clearance", "public trust clearance",
      "no sponsorship", "will not sponsor", "cannot sponsor",
    ].join("\n"),
  });
  const [keys, setKeys] = useState({ anthropic: "", hunter: "", apollo: "", serpapi: "" });

  useEffect(() => {
    if (!profile) return;
    setContact({ ...contact, ...profile.contact });
    setBg((b) => ({
      ...b,
      mode: profile.resume_pdf_filename ? "upload" : (profile.experience_summary ? "describe" : "upload"),
      summary: profile.experience_summary || "",
      filename: profile.resume_pdf_filename || "",
    }));
    setTargets({
      rolesText: (profile.targets.roles || []).join(", "),
      company_size_min: profile.targets.company_size_min ?? 0,
      company_size_max: profile.targets.company_size_max ?? 100000,
      locationsOk: (profile.targets.locations_ok || []).join(", "),
      locationsPreferred: (profile.targets.locations_preferred || []).join(", "),
      salary_min_usd: profile.targets.salary_min_usd || 0,
    });
    setVisa({
      status: profile.visa.status || "",
      needs_sponsorship: !!profile.visa.needs_sponsorship,
      disqualifiers: (profile.visa.disqualify_if || []).join("\n"),
    });
    // intentionally don't pre-populate api_keys (they're masked)
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [profile?.contact.name]);

  const next = () => setStep((s) => Math.min(5, (s + 1) as Step));
  const back = () => setStep((s) => Math.max(1, (s - 1) as Step));

  const finish = async () => {
    try {
      const patch: any = {
        contact,
        experience_summary: bg.mode === "describe" ? bg.summary : "",
        targets: {
          roles: targets.rolesText.split(",").map((s) => s.trim()).filter(Boolean),
          company_size_min: Number(targets.company_size_min) || 0,
          company_size_max: Number(targets.company_size_max) || 100000,
          locations_ok: targets.locationsOk.split(",").map((s) => s.trim()).filter(Boolean),
          locations_preferred: targets.locationsPreferred.split(",").map((s) => s.trim()).filter(Boolean),
          salary_min_usd: Number(targets.salary_min_usd) || 0,
        },
        visa: {
          status: visa.status,
          needs_sponsorship: visa.needs_sponsorship,
          disqualify_if: visa.disqualifiers.split("\n").map((s) => s.trim()).filter(Boolean),
        },
        api_keys: keys,
      };
      // Browser holds the authoritative copy — cloud backend is ephemeral.
      saveProfileLS(patch);
      await api.updateProfile(patch);
      qc.invalidateQueries({ queryKey: ["setup-status"] });
      qc.invalidateQueries({ queryKey: ["profile"] });
      toast("Setup complete!", "ok");
      nav("/");
    } catch (e: any) {
      toast(`Failed: ${e.message}`, "err");
    }
  };

  const uploadResume = async (f: File) => {
    try {
      const res = await api.uploadResume(f);
      setBg((b) => ({ ...b, filename: res.filename }));
      qc.invalidateQueries({ queryKey: ["profile"] });
      qc.invalidateQueries({ queryKey: ["setup-status"] });
      toast(`Uploaded ${res.filename}`, "ok");
    } catch (e: any) {
      toast(`Upload failed: ${e.message}`, "err");
    }
  };

  const stepLabels = ["About you", "Background", "Targets", "Visa & filters", "API key"];

  return (
    <div className="max-w-3xl mx-auto">
      <h1 className="text-3xl font-bold mb-2">Welcome — let's set you up</h1>
      <p className="text-slate-400 mb-6 text-sm">
        This is a 2-minute setup. Everything lives locally in <code>data/profile.json</code> — nothing leaves your machine except Anthropic API calls.
      </p>

      <ol className="flex gap-2 mb-6 text-xs">
        {stepLabels.map((label, i) => {
          const n = (i + 1) as Step;
          const active = step === n;
          const done = step > n;
          return (
            <li
              key={label}
              onClick={() => setStep(n)}
              className={`px-3 py-1.5 rounded cursor-pointer border ${
                active ? "bg-indigo-600 text-white border-indigo-600" :
                done ? "bg-emerald-500/15 text-emerald-300 border-emerald-500/30" :
                       "bg-[#0f1018] border-slate-800 text-slate-500"
              }`}
            >
              {n}. {label}
            </li>
          );
        })}
      </ol>

      <div className="bg-[#11121c] border border-slate-800 rounded-lg p-6">
        {step === 1 && (
          <div className="grid md:grid-cols-2 gap-4">
            <Field label="Full name *">
              <input className={inputCls} value={contact.name}
                     onChange={(e) => setContact({ ...contact, name: e.target.value })} />
            </Field>
            <Field label="Email *">
              <input className={inputCls} type="email" value={contact.email}
                     onChange={(e) => setContact({ ...contact, email: e.target.value })} />
            </Field>
            <Field label="Phone">
              <input className={inputCls} value={contact.phone}
                     onChange={(e) => setContact({ ...contact, phone: e.target.value })} />
            </Field>
            <Field label="Location">
              <input className={inputCls} placeholder="e.g. Madison, WI"
                     value={contact.location}
                     onChange={(e) => setContact({ ...contact, location: e.target.value })} />
            </Field>
            <Field label="LinkedIn URL">
              <input className={inputCls} value={contact.linkedin}
                     onChange={(e) => setContact({ ...contact, linkedin: e.target.value })} />
            </Field>
            <Field label="GitHub URL">
              <input className={inputCls} value={contact.github}
                     onChange={(e) => setContact({ ...contact, github: e.target.value })} />
            </Field>
            <Field label="Portfolio / personal site">
              <input className={inputCls} value={contact.portfolio}
                     onChange={(e) => setContact({ ...contact, portfolio: e.target.value })} />
            </Field>
          </div>
        )}

        {step === 2 && (
          <div>
            <div className="flex gap-2 mb-4 text-sm">
              <button
                onClick={() => setBg({ ...bg, mode: "upload" })}
                className={`px-3 py-1.5 rounded border ${bg.mode === "upload" ? "bg-indigo-600 text-white border-indigo-600" : "bg-[#0f1018] border-slate-800"}`}
              >Upload resume (PDF)</button>
              <button
                onClick={() => setBg({ ...bg, mode: "describe" })}
                className={`px-3 py-1.5 rounded border ${bg.mode === "describe" ? "bg-indigo-600 text-white border-indigo-600" : "bg-[#0f1018] border-slate-800"}`}
              >Describe my experience</button>
            </div>

            {bg.mode === "upload" ? (
              <Field label="Resume PDF" hint="A 1-page resume works best. Re-upload to replace.">
                <div className="border-2 border-dashed border-slate-700 rounded p-6 text-center bg-[#0f1018]">
                  <input
                    type="file" accept="application/pdf"
                    onChange={(e) => e.target.files?.[0] && uploadResume(e.target.files[0])}
                  />
                  {bg.filename && (
                    <div className="mt-2 text-sm text-emerald-300">✓ {bg.filename}</div>
                  )}
                </div>
              </Field>
            ) : (
              <Field label="Tell me about your experience" hint="Education, work history, projects, skills. The more concrete, the better.">
                <textarea
                  rows={14} className={inputCls}
                  value={bg.summary}
                  onChange={(e) => setBg({ ...bg, summary: e.target.value })}
                  placeholder={`e.g. I'm graduating in May with a BS in CS from UW–Madison. I've interned at Capital One on a fraud detection AWS pipeline, at a robotics lab building RL environments in IsaacGym, and at a medtech startup doing real-time perception with OpenCV. Strong in Python, React, FastAPI, AWS. Built a crypto portfolio tracker (cryptodash.vercel.app) and a 2D horror game. Looking for roles where I can ship to users quickly.`}
                />
              </Field>
            )}
          </div>
        )}

        {step === 3 && (
          <div className="grid md:grid-cols-2 gap-4">
            <Field label="Target roles" hint="Comma-separated">
              <input className={inputCls}
                     placeholder="software engineer, ai engineer, founding engineer"
                     value={targets.rolesText}
                     onChange={(e) => setTargets({ ...targets, rolesText: e.target.value })} />
            </Field>
            <Field label="Minimum salary (USD)">
              <input type="number" className={inputCls}
                     value={targets.salary_min_usd}
                     onChange={(e) => setTargets({ ...targets, salary_min_usd: +e.target.value })} />
            </Field>
            <Field label="Company size (min)">
              <input type="number" className={inputCls}
                     value={targets.company_size_min}
                     onChange={(e) => setTargets({ ...targets, company_size_min: +e.target.value })} />
            </Field>
            <Field label="Company size (max)">
              <input type="number" className={inputCls}
                     value={targets.company_size_max}
                     onChange={(e) => setTargets({ ...targets, company_size_max: +e.target.value })} />
            </Field>
            <Field label="Locations OK" hint="Comma-separated">
              <input className={inputCls}
                     value={targets.locationsOk}
                     onChange={(e) => setTargets({ ...targets, locationsOk: e.target.value })} />
            </Field>
            <Field label="Preferred locations" hint="Comma-separated">
              <input className={inputCls}
                     placeholder="nyc, san francisco, california"
                     value={targets.locationsPreferred}
                     onChange={(e) => setTargets({ ...targets, locationsPreferred: e.target.value })} />
            </Field>
          </div>
        )}

        {step === 4 && (
          <div className="grid gap-4">
            <Field label="Work authorization status" hint="e.g. US citizen / Green card / F-1 OPT / H-1B holder">
              <input className={inputCls}
                     value={visa.status}
                     onChange={(e) => setVisa({ ...visa, status: e.target.value })} />
            </Field>
            <label className="flex items-center gap-2 text-sm">
              <input type="checkbox" checked={visa.needs_sponsorship}
                     onChange={(e) => setVisa({ ...visa, needs_sponsorship: e.target.checked })} />
              I will need visa sponsorship (now or in the future)
            </label>
            <Field label="Auto-disqualify if job description contains…" hint="One phrase per line. Case-insensitive substring match.">
              <textarea rows={8} className={inputCls}
                        value={visa.disqualifiers}
                        onChange={(e) => setVisa({ ...visa, disqualifiers: e.target.value })} />
            </Field>
          </div>
        )}

        {step === 5 && (
          <div className="grid gap-4">
            <p className="text-sm text-slate-600">
              You need an <strong>Anthropic API key</strong> for scoring and tailoring.
              Get one at{" "}
              <a href="https://console.anthropic.com/settings/keys" target="_blank"
                 className="text-indigo-400 underline">console.anthropic.com</a>.
              Others are optional (used later for contact lookup).
            </p>
            <Field label="Anthropic API key *">
              <input type="password" className={inputCls}
                     value={keys.anthropic} placeholder="sk-ant-..."
                     onChange={(e) => setKeys({ ...keys, anthropic: e.target.value })} />
            </Field>
            <details className="text-sm">
              <summary className="cursor-pointer text-slate-500">Optional keys (Hunter, Apollo, SerpAPI)</summary>
              <div className="grid gap-3 mt-3">
                <Field label="Hunter.io"><input type="password" className={inputCls} value={keys.hunter}
                       onChange={(e) => setKeys({ ...keys, hunter: e.target.value })} /></Field>
                <Field label="Apollo.io"><input type="password" className={inputCls} value={keys.apollo}
                       onChange={(e) => setKeys({ ...keys, apollo: e.target.value })} /></Field>
                <Field label="SerpAPI"><input type="password" className={inputCls} value={keys.serpapi}
                       onChange={(e) => setKeys({ ...keys, serpapi: e.target.value })} /></Field>
              </div>
            </details>
          </div>
        )}

        <div className="flex justify-between mt-6">
          <button onClick={back} disabled={step === 1}
                  className="px-4 py-2 text-sm rounded border border-slate-700 text-slate-300 disabled:opacity-30">
            Back
          </button>
          {step < 5 ? (
            <button onClick={next}
                    className="px-4 py-2 text-sm rounded bg-indigo-600 text-white">
              Next →
            </button>
          ) : (
            <button onClick={finish}
                    className="px-4 py-2 text-sm rounded bg-emerald-600 hover:bg-emerald-500 text-white">
              Finish setup
            </button>
          )}
        </div>
      </div>
    </div>
  );
}
