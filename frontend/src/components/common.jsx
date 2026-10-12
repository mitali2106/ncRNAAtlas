import {
  AlertTriangle,
  CheckCircle2,
  CircleDashed,
  CircleHelp,
  Clock,
  CloudOff,
  Cpu,
  ExternalLink,
  FlaskConical,
  Inbox,
  Loader2,
  MinusCircle,
  ServerCrash,
  ShieldCheck,
  WifiOff,
  XCircle,
} from 'lucide-react'
import { DIRECTIONS, EVIDENCE_LEVELS, VALIDATION_STATUSES, label } from '../utils/labels'

export function Loading({ text = 'Loading…' }) {
  return (
    <div className="state state-loading" role="status" aria-live="polite">
      <Loader2 className="spin" size={18} aria-hidden /> {text}
    </div>
  )
}

/** Distinguishes unreachable backend, unavailable external source, missing record and generic failures. */
export function ErrorState({ error, onRetry, what = 'this data' }) {
  if (!error) return null
  let Icon = ServerCrash
  let title = `Could not load ${what}`
  if (error.isNetwork) {
    Icon = WifiOff
    title = 'The ncRNAAtlas API is unreachable'
  } else if (error.isExternal) {
    Icon = CloudOff
    title = 'An external resource is unavailable'
  } else if (error.isNotFound) {
    Icon = Inbox
    title = 'Record not found'
  }
  return (
    <div className={`state state-error ${error.isExternal ? 'state-external' : ''}`} role="alert">
      <Icon size={20} aria-hidden />
      <div>
        <strong>{title}</strong>
        <p>{error.message}</p>
        {error.isExternal && <p className="muted">Data already stored in ncRNAAtlas is unaffected.</p>}
        {onRetry && !error.isNotFound && (
          <button type="button" className="btn btn-small" onClick={onRetry}>
            Try again
          </button>
        )}
      </div>
    </div>
  )
}

export function EmptyState({ title = 'No records', children, icon: Icon = Inbox }) {
  return (
    <div className="state state-empty">
      <Icon size={20} aria-hidden />
      <div>
        <strong>{title}</strong>
        {children && <div className="muted">{children}</div>}
      </div>
    </div>
  )
}

const EVIDENCE_ICONS = {
  experimental: FlaskConical,
  computational_prediction: Cpu,
  literature_unclear: CircleHelp,
  conflicting: AlertTriangle,
  unverified: MinusCircle,
}

export function EvidenceBadge({ level }) {
  const Icon = EVIDENCE_ICONS[level] || CircleDashed
  return (
    <span className={`badge ev-${level}`} title={label(EVIDENCE_LEVELS, level)}>
      <Icon size={13} aria-hidden /> {label(EVIDENCE_LEVELS, level)}
    </span>
  )
}

const VALIDATION_ICONS = {
  not_reviewed: CircleDashed,
  under_review: Clock,
  curator_confirmed: ShieldCheck,
  insufficient_evidence: CircleHelp,
  conflicting: AlertTriangle,
  curator_rejected: XCircle,
}

export function ValidationBadge({ status }) {
  const Icon = VALIDATION_ICONS[status] || CircleDashed
  return (
    <span className={`badge val-${status}`} title={label(VALIDATION_STATUSES, status)}>
      <Icon size={13} aria-hidden /> {label(VALIDATION_STATUSES, status)}
    </span>
  )
}

export function ResolutionBadge({ status, note }) {
  if (!status || status === 'resolved') {
    return (
      <span className="badge res-resolved" title="Identifier resolved">
        <CheckCircle2 size={13} aria-hidden /> resolved
      </span>
    )
  }
  return (
    <span className={`badge res-${status}`} title={note || status}>
      <CircleHelp size={13} aria-hidden /> {status.replace('_', ' ')}
    </span>
  )
}

export function TypeBadge({ type }) {
  return <span className={`badge type-${type}`}>{type}</span>
}

export function Direction({ value }) {
  if (!value || value === 'unspecified') return <span className="muted">—</span>
  return <span className={`dir dir-${value}`}>{label(DIRECTIONS, value)}</span>
}

export function ExtLink({ href, children }) {
  if (!href) return <>{children}</>
  return (
    <a href={href} target="_blank" rel="noopener noreferrer" className="extlink">
      {children} <ExternalLink size={12} aria-hidden />
      <span className="sr-only">(opens in a new tab)</span>
    </a>
  )
}

export function Section({ title, subtitle, actions, children, id }) {
  return (
    <section className="card" id={id}>
      <header className="card-head">
        <div>
          <h2>{title}</h2>
          {subtitle && <p className="muted small">{subtitle}</p>}
        </div>
        {actions && <div className="card-actions">{actions}</div>}
      </header>
      {children}
    </section>
  )
}

export function KeyValue({ items }) {
  return (
    <dl className="kv">
      {items
        .filter(([, v]) => v !== undefined)
        .map(([k, v]) => (
          <div key={k}>
            <dt>{k}</dt>
            <dd>{v === null || v === '' ? <span className="muted">Not available</span> : v}</dd>
          </div>
        ))}
    </dl>
  )
}

export function Pagination({ pagination, onPage }) {
  if (!pagination || pagination.pages <= 1) {
    return pagination ? <p className="muted small pager-info">{pagination.total.toLocaleString()} records</p> : null
  }
  const { page, pages, total } = pagination
  return (
    <nav className="pager" aria-label="Pagination">
      <button type="button" className="btn btn-small" disabled={page <= 1} onClick={() => onPage(page - 1)}>
        Previous
      </button>
      <span className="small">
        Page {page} of {pages} · {total.toLocaleString()} records
      </span>
      <button type="button" className="btn btn-small" disabled={page >= pages} onClick={() => onPage(page + 1)}>
        Next
      </button>
    </nav>
  )
}

export function StatCard({ label: text, value, hint, icon: Icon }) {
  return (
    <div className="stat">
      {Icon && <Icon size={18} aria-hidden className="stat-icon" />}
      <div className="stat-value">{typeof value === 'number' ? value.toLocaleString() : value}</div>
      <div className="stat-label">{text}</div>
      {hint && <div className="stat-hint">{hint}</div>}
    </div>
  )
}

export function PageHeader({ eyebrow, title, children, actions }) {
  return (
    <div className="page-head">
      <div>
        {eyebrow && <div className="eyebrow">{eyebrow}</div>}
        <h1>{title}</h1>
        {children}
      </div>
      {actions && <div className="page-actions">{actions}</div>}
    </div>
  )
}
