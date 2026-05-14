import { useState } from "react";
import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";
import { api, type Contact } from "../api";
import { useToast } from "./Toast";

function gmailComposeUrl(to: string, subject: string, body: string) {
  const q = new URLSearchParams({ view: "cm", fs: "1", to, su: subject, body });
  return `https://mail.google.com/mail/?${q.toString()}`;
}
function mailtoUrl(to: string, subject: string, body: string) {
  return `mailto:${to}?subject=${encodeURIComponent(subject)}&body=${encodeURIComponent(body)}`;
}

export function Outreach({ jobId }: { jobId: number }) {
  const qc = useQueryClient();
  const toast = useToast();
  const contacts = useQuery({
    queryKey: ["contacts", jobId],
    queryFn: () => api.listContacts(jobId),
  });

  const find = useMutation({
    mutationFn: () => api.findContacts(jobId),
    onSuccess: (r) => {
      if (r.found > 0) {
        toast(`Found ${r.found} new contact(s) at ${r.domain || ""}`, "ok");
      } else if (!r.total_returned) {
        toast(`No contacts found${r.domain ? ` for ${r.domain}` : ""}`, "info");
      } else {
        toast(`No new contacts (all duplicates).`, "info");
      }
      qc.invalidateQueries({ queryKey: ["contacts", jobId] });
    },
    onError: (e: any) => toast(e.message, "err"),
  });

  return (
    <div className="bg-[#11121c] border border-slate-800 rounded-lg p-5 mt-4">
      <div className="flex items-center justify-between mb-3">
        <h2 className="font-semibold text-slate-100">Outreach</h2>
        <button
          disabled={find.isPending}
          onClick={() => find.mutate()}
          className="px-3 py-1.5 bg-fuchsia-600 hover:bg-fuchsia-500 text-white rounded text-sm disabled:opacity-50"
        >
          {find.isPending ? "Searching…" : "Find contacts"}
        </button>
      </div>

      {contacts.data && contacts.data.contacts.length === 0 && (
        <p className="text-sm text-slate-500">
          No contacts yet. Click "Find contacts" — uses Hunter.io to look up
          founders / hiring managers at this company's domain.
        </p>
      )}

      <div className="grid gap-3">
        {contacts.data?.contacts.map((c) => (
          <ContactCard key={c.id} c={c} />
        ))}
      </div>
    </div>
  );
}

function ContactCard({ c }: { c: Contact }) {
  const [open, setOpen] = useState(!!c.subject);
  const [subject, setSubject] = useState(c.subject || "");
  const [body, setBody] = useState(c.body || "");
  const qc = useQueryClient();
  const toast = useToast();

  const draft = useMutation({
    mutationFn: () => api.draftEmail(c.id),
    onSuccess: (r) => {
      setSubject(r.subject); setBody(r.body); setOpen(true);
      qc.invalidateQueries({ queryKey: ["contacts", c.job_id] });
      qc.invalidateQueries({ queryKey: ["budget"] });
      toast("Email drafted", "ok");
    },
    onError: (e: any) => toast(e.message, "err"),
  });

  const sent = useMutation({
    mutationFn: () => api.markSent(c.id),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ["contacts", c.job_id] });
      toast("Marked as sent", "ok");
    },
  });

  return (
    <div className="border border-slate-800 bg-[#0f1018] rounded-md p-3">
      <div className="flex items-start justify-between gap-3 flex-wrap">
        <div className="text-sm">
          <div className="font-medium text-slate-100">
            {c.name || <span className="text-slate-500">(name unknown)</span>}
            {c.confidence !== null && (
              <span className="ml-2 text-xs text-slate-500 font-normal">conf {c.confidence}</span>
            )}
            {c.sent_at && (
              <span className="ml-2 text-xs text-emerald-300 bg-emerald-500/10 border border-emerald-500/30 rounded px-1.5">
                sent
              </span>
            )}
          </div>
          <div className="text-slate-400">{c.title || ""}</div>
          <div className="text-slate-300 font-mono text-xs mt-0.5">{c.email}</div>
          {c.linkedin && (
            <a href={c.linkedin} target="_blank"
               className="text-xs text-indigo-400 hover:underline">LinkedIn</a>
          )}
        </div>
        <button
          disabled={draft.isPending}
          onClick={() => draft.mutate()}
          className="px-3 py-1.5 bg-indigo-600 hover:bg-indigo-500 text-white rounded text-xs disabled:opacity-50"
        >
          {draft.isPending ? "Drafting…" : (c.subject ? "Re-draft" : "Draft email")}
        </button>
      </div>

      {(open && (subject || body)) && (
        <div className="mt-3 pt-3 border-t border-slate-800 grid gap-2">
          <label className="text-xs uppercase tracking-wide text-slate-500">Subject</label>
          <input
            value={subject} onChange={(e) => setSubject(e.target.value)}
            className="px-3 py-1.5 border border-slate-800 rounded text-sm"
          />
          <label className="text-xs uppercase tracking-wide text-slate-500">Body</label>
          <textarea
            rows={9} value={body} onChange={(e) => setBody(e.target.value)}
            className="px-3 py-2 border border-slate-800 rounded text-sm font-mono"
          />
          <div className="flex flex-wrap gap-2 mt-1">
            <a href={gmailComposeUrl(c.email, subject, body)} target="_blank"
               className="px-3 py-1.5 bg-indigo-600 hover:bg-indigo-500 text-white rounded text-xs">
              Open in Gmail
            </a>
            <a href={mailtoUrl(c.email, subject, body)}
               className="px-3 py-1.5 bg-slate-700 hover:bg-slate-600 text-white rounded text-xs">
              Open in default mail
            </a>
            <button
              onClick={() => { navigator.clipboard.writeText(body); toast("Body copied", "ok"); }}
              className="px-3 py-1.5 bg-slate-800 hover:bg-slate-700 text-slate-200 rounded text-xs border border-slate-700"
            >
              Copy body
            </button>
            <button
              onClick={() => sent.mutate()}
              className="px-3 py-1.5 bg-emerald-600 hover:bg-emerald-500 text-white rounded text-xs"
            >
              Mark as sent
            </button>
          </div>
        </div>
      )}
    </div>
  );
}
