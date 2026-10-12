import { CheckCircle2, FileUp, KeyRound, LogOut } from 'lucide-react'
import { useEffect, useState } from 'react'
import { Link } from 'react-router-dom'
import { EmptyState, ErrorState, KeyValue, Loading, PageHeader, Section, ValidationBadge } from '../components/common'
import { api, getAdminToken, setAdminToken } from '../services/api'
import { REVIEW_OUTCOMES, formatDate } from '../utils/labels'

function Login({ onLogin }) {
  const [token, setToken] = useState('')
  const [error, setError] = useState(null)
  const submit = async (e) => {
    e.preventDefault()
    setAdminToken(token)
    try {
      await api.admin.verify()
      onLogin()
    } catch (err) {
      setAdminToken('')
      setError(err)
    }
  }
  return (
    <Section title="Administrator sign-in" subtitle="Enter the ADMIN_TOKEN configured on the server">
      <form onSubmit={submit} className="inline">
        <input type="password" value={token} onChange={(e) => setToken(e.target.value)} placeholder="Admin token" aria-label="Admin token" autoComplete="current-password" />
        <button type="submit" className="btn btn-primary" disabled={!token}><KeyRound size={14} aria-hidden /> Sign in</button>
      </form>
      <ErrorState error={error} what="admin access" />
      <p className="small muted">The token is kept only in this browser tab (sessionStorage). Command-line imports do not need it — see the README.</p>
    </Section>
  )
}

function UploadPanel({ adapters, onJob }) {
  const [file, setFile] = useState(null)
  const [adapter, setAdapter] = useState('generic_associations')
  const [version, setVersion] = useState('')
  const [sourceName, setSourceName] = useState('')
  const [preview, setPreview] = useState(null)
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState(null)
  const [skipUnresolved, setSkipUnresolved] = useState(false)
  const [humanOnly, setHumanOnly] = useState(false)
  const [overrides, setOverrides] = useState({})
  const desc = adapters.find((a) => a.key === adapter)

  const upload = async (e) => {
    e.preventDefault()
    setBusy(true)
    setError(null)
    setPreview(null)
    const form = new FormData()
    form.append('file', file)
    form.append('adapter', adapter)
    if (version) form.append('source_version', version)
    if (sourceName) form.append('source_database', sourceName)
    try {
      setPreview((await api.admin.upload(form)).data)
      setOverrides({})
    } catch (err) {
      setError(err)
    } finally {
      setBusy(false)
    }
  }

  const commit = async () => {
    setBusy(true)
    setError(null)
    const ov = {}
    Object.entries(overrides).forEach(([key, value]) => {
      const [kind, raw] = key.split('::')
      if (value.trim()) ov[kind] = { ...(ov[kind] || {}), [raw]: value.trim() }
    })
    try {
      const job = (await api.admin.commit(preview.upload_id, { overrides: ov, skip_unresolved: skipUnresolved, human_only: humanOnly })).data
      setPreview(null)
      setFile(null)
      onJob(job)
    } catch (err) {
      setError(err)
    } finally {
      setBusy(false)
    }
  }

  const p = preview?.preview
  return (
    <Section title="1. Upload and validate a file" subtitle="CSV/TSV, UTF-8, up to the server's size limit. Nothing is written until you confirm.">
      <form onSubmit={upload} className="upload-form">
        <label>Format
          <select value={adapter} onChange={(e) => setAdapter(e.target.value)}>
            {adapters.map((a) => <option key={a.key} value={a.key}>{a.source_database} — {a.key}</option>)}
          </select>
        </label>
        <label>File <input type="file" accept=".csv,.tsv,.txt" onChange={(e) => setFile(e.target.files[0] || null)} /></label>
        <label>Source version <input value={version} onChange={(e) => setVersion(e.target.value)} placeholder="e.g. 2026-10" maxLength={64} /></label>
        {adapter.startsWith('generic') && <label>Source name (optional) <input value={sourceName} onChange={(e) => setSourceName(e.target.value)} placeholder="overrides source_database column" maxLength={64} /></label>}
        <button type="submit" className="btn btn-primary" disabled={!file || busy}><FileUp size={14} aria-hidden /> Upload &amp; preview</button>
      </form>
      {desc && (
        <p className="small muted">
          {desc.description} Required columns: <code>{desc.required_columns.join(', ')}</code>
          {desc.optional_columns.length > 0 && <> · optional: <code>{desc.optional_columns.join(', ')}</code></>}
        </p>
      )}
      {busy && <Loading text="Working…" />}
      <ErrorState error={error} what="the upload" />
      {p && (
        <div className="preview">
          <h3 className="h3">Validation preview — {preview.original_filename}</h3>
          {p.errors.length > 0 && <div className="state state-error"><div><strong>File rejected</strong>{p.errors.map((e) => <p key={e}>{e}</p>)}</div></div>}
          <KeyValue items={[
            ['Rows read', p.raw_records], ['Valid records', p.valid_records], ['Would create associations / interactions', p.inserted],
            ['Would merge into existing', p.merged_into_existing], ['Already present (unchanged)', p.unchanged],
            ['Skipped', `${p.skipped} ${Object.keys(p.skip_reasons).length ? JSON.stringify(p.skip_reasons) : ''}`],
            ['Duplicates within file', p.duplicates_in_file], ['Non-human records', p.non_human_records], ['Records without PMID', p.missing_pmid],
          ]} />
          {Object.entries(p.unresolved).map(([kind, rows]) => rows.length > 0 && (
            <div key={kind}>
              <h4>Unresolved / ambiguous {kind} names ({rows.length})</h4>
              <p className="small muted">Optionally map a name to an existing canonical name; otherwise it is imported and flagged{skipUnresolved ? ' (or skipped, as selected below)' : ''}.</p>
              <div className="table-wrap">
                <table className="table compact">
                  <thead><tr><th scope="col">Name in file</th><th scope="col">Status</th><th scope="col">Note</th><th scope="col" className="num">Rows</th><th scope="col">Map to (optional)</th></tr></thead>
                  <tbody>
                    {rows.map((r) => (
                      <tr key={r.name}>
                        <td className="mono small">{r.name}</td><td className="small">{r.status}</td><td className="small">{r.note}</td><td className="num">{r.count}</td>
                        <td><input aria-label={`Map ${r.name} to`} value={overrides[`${kind}::${r.name}`] || ''} onChange={(e) => setOverrides((o) => ({ ...o, [`${kind}::${r.name}`]: e.target.value }))} placeholder="canonical name" /></td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            </div>
          ))}
          {p.warnings.length > 0 && (
            <details>
              <summary>Data-cleaning warnings ({p.warnings.length}{p.warnings_truncated ? '+' : ''})</summary>
              <ul className="small">{p.warnings.map((w, i) => <li key={i}>{w.line ? `Line ${w.line}: ` : ''}{w.message}</li>)}</ul>
            </details>
          )}
          {p.preview.length > 0 && (
            <details>
              <summary>Record preview (first {p.preview.length})</summary>
              <div className="table-wrap">
                <table className="table compact">
                  <thead><tr>{Object.keys(p.preview[0]).map((k) => <th key={k} scope="col">{k}</th>)}</tr></thead>
                  <tbody>{p.preview.map((r) => <tr key={r.line}>{Object.values(r).map((v, i) => <td key={i} className="small">{Array.isArray(v) ? v.join(', ') : String(v)}</td>)}</tr>)}</tbody>
                </table>
              </div>
            </details>
          )}
          {preview.valid && (
            <div className="confirm-row">
              <label className="check"><input type="checkbox" checked={skipUnresolved} onChange={(e) => setSkipUnresolved(e.target.checked)} /> Skip records with unresolved or ambiguous entities</label>
              <label className="check"><input type="checkbox" checked={humanOnly} onChange={(e) => setHumanOnly(e.target.checked)} /> Import human records only</label>
              <button type="button" className="btn btn-primary" onClick={commit} disabled={busy}><CheckCircle2 size={14} aria-hidden /> Confirm import</button>
            </div>
          )}
        </div>
      )}
    </Section>
  )
}

function JobPanel({ job }) {
  const [current, setCurrent] = useState(job)
  useEffect(() => {
    setCurrent(job)
    if (!job || !['pending', 'running'].includes(job.status)) return undefined
    const t = setInterval(async () => {
      try {
        const j = (await api.importJob(job.id)).data
        setCurrent(j)
        if (!['pending', 'running'].includes(j.status)) clearInterval(t)
      } catch {
        clearInterval(t)
      }
    }, 1500)
    return () => clearInterval(t)
  }, [job])
  if (!current) return null
  const getReport = async (format) => {
    const res = await api.admin.report(current.id, format)
    const blob = await res.blob()
    const url = URL.createObjectURL(blob)
    const a = document.createElement('a')
    a.href = url
    a.download = `ncrnaatlas_import_${current.id}_quality.${format}`
    a.click()
    URL.revokeObjectURL(url)
  }
  const running = ['pending', 'running'].includes(current.status)
  return (
    <Section title={`2. Import job #${current.id}`} subtitle={current.source_file}>
      {running && <Loading text={`Importing… ${current.records_processed.toLocaleString()} records processed`} />}
      {!running && (
        <p className={current.status === 'failed' ? 'state state-error' : 'success'} role="status">
          {current.status === 'failed' ? `Import failed: ${current.error_summary}` : `Import ${current.status.replaceAll('_', ' ')}.`}
        </p>
      )}
      <KeyValue items={[
        ['Status', current.status], ['Processed', current.records_processed], ['New', current.records_inserted],
        ['Merged into existing', current.records_updated], ['Skipped', current.records_skipped],
        ['Completed', formatDate(current.completed_at)],
      ]} />
      {!running && current.has_report && (
        <div className="inline">
          <button type="button" className="btn btn-small" onClick={() => getReport('csv')}>Download quality report (CSV)</button>
          <button type="button" className="btn btn-small" onClick={() => getReport('json')}>Download quality report (JSON)</button>
        </div>
      )}
    </Section>
  )
}

function ReviewPanel() {
  const [queue, setQueue] = useState(null)
  const [error, setError] = useState(null)
  const [form, setForm] = useState({ association: '', pmid: '', outcome: 'supports_direct_experimental', evidence_type: '', notes: '', reviewer: '' })
  const [msg, setMsg] = useState(null)
  const load = () => api.admin.reviewQueue().then((j) => setQueue(j.data)).catch(setError)
  useEffect(() => { load() }, [])
  const set = (k) => (e) => setForm((f) => ({ ...f, [k]: e.target.value }))
  const submit = async (e) => {
    e.preventDefault()
    setMsg(null)
    setError(null)
    try {
      const r = await api.admin.review(form.association, { pmid: form.pmid || null, outcome: form.outcome, evidence_type: form.evidence_type, notes: form.notes, reviewer: form.reviewer })
      setMsg(`Review recorded. Association #${form.association} is now “${r.data.validation_status.replaceAll('_', ' ')}”.`)
      load()
    } catch (err) {
      setError(err)
    }
  }
  return (
    <Section title="Literature review" subtitle="Record a curator decision after reading the publication. Keyword co-occurrence is never sufficient.">
      <form onSubmit={submit} className="upload-form">
        <label>Association ID <input required value={form.association} onChange={set('association')} inputMode="numeric" /></label>
        <label>PMID reviewed <input value={form.pmid} onChange={set('pmid')} inputMode="numeric" /></label>
        <label>Outcome
          <select value={form.outcome} onChange={set('outcome')}>
            {Object.entries(REVIEW_OUTCOMES).map(([k, v]) => <option key={k} value={k}>{v}</option>)}
          </select>
        </label>
        <label>Evidence type <input value={form.evidence_type} onChange={set('evidence_type')} placeholder="e.g. luciferase reporter, qRT-PCR in tissue" /></label>
        <label>Reviewer <input required value={form.reviewer} onChange={set('reviewer')} /></label>
        <label className="wide">Notes <textarea value={form.notes} onChange={set('notes')} rows={2} /></label>
        <button type="submit" className="btn btn-primary">Record review</button>
      </form>
      {msg && <p className="success" role="status">{msg}</p>}
      <ErrorState error={error} what="the review" />
      <h3 className="h3">Awaiting review</h3>
      {!queue ? <Loading /> : queue.length === 0 ? <EmptyState title="Queue is empty" /> : (
        <div className="table-wrap">
          <table className="table compact">
            <thead><tr><th scope="col">ID</th><th scope="col">Association</th><th scope="col">Status</th><th scope="col" className="num">PMIDs</th></tr></thead>
            <tbody>
              {queue.map((a) => (
                <tr key={a.id}>
                  <td>{a.id}</td>
                  <td><Link to={`/associations/${a.id}`}>{a.ncrna.canonical_name} – {a.disease.canonical_name}</Link> <span className="small muted">({a.association_type})</span></td>
                  <td><ValidationBadge status={a.validation_status} /></td>
                  <td className="num">{a.publication_count}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </Section>
  )
}

export default function AdminPage() {
  const [authed, setAuthed] = useState(false)
  const [checking, setChecking] = useState(Boolean(getAdminToken()))
  const [adapters, setAdapters] = useState([])
  const [job, setJob] = useState(null)
  const [error, setError] = useState(null)

  useEffect(() => {
    if (!getAdminToken()) return
    api.admin.verify().then(() => setAuthed(true)).catch(() => setAdminToken('')).finally(() => setChecking(false))
  }, [])
  useEffect(() => {
    if (authed) api.admin.adapters().then((j) => setAdapters(j.data)).catch(setError)
  }, [authed])

  return (
    <>
      <PageHeader eyebrow="Administration" title="Data import & quality control"
        actions={authed && <button type="button" className="btn" onClick={() => { setAdminToken(''); setAuthed(false) }}><LogOut size={14} aria-hidden /> Sign out</button>}>
        <p className="muted">Upload documented CSV/TSV files, review cleaning warnings and unresolved identifiers, then confirm. No destructive operations are available here.</p>
      </PageHeader>
      {checking && <Loading text="Checking session…" />}
      {!checking && !authed && <Login onLogin={() => setAuthed(true)} />}
      <ErrorState error={error} what="admin data" />
      {authed && adapters.length > 0 && (
        <>
          <UploadPanel adapters={adapters} onJob={setJob} />
          <JobPanel job={job} />
          <ReviewPanel />
        </>
      )}
    </>
  )
}
