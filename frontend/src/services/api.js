// Thin client for the ncRNAAtlas REST API. No credentials are stored in code;
// the optional admin token is entered by the user and kept in sessionStorage.

const BASE = import.meta.env.VITE_API_BASE || '/api'
const TIMEOUT_MS = 30000

export class ApiError extends Error {
  constructor(message, { status = 0, code = 'network_error', details } = {}) {
    super(message)
    this.status = status
    this.code = code
    this.details = details
  }

  get isNetwork() {
    return this.status === 0
  }

  get isExternal() {
    return ['external_unavailable', 'external_disabled'].includes(this.code)
  }

  get isNotFound() {
    return this.status === 404
  }
}

export function buildQuery(params = {}) {
  const q = new URLSearchParams()
  Object.entries(params).forEach(([k, v]) => {
    if (v === undefined || v === null || v === '') return
    q.set(k, Array.isArray(v) ? v.join(',') : String(v))
  })
  const s = q.toString()
  return s ? `?${s}` : ''
}

export function getAdminToken() {
  try {
    return sessionStorage.getItem('ncrnaatlas_admin_token') || ''
  } catch {
    return ''
  }
}

export function setAdminToken(token) {
  try {
    if (token) sessionStorage.setItem('ncrnaatlas_admin_token', token)
    else sessionStorage.removeItem('ncrnaatlas_admin_token')
  } catch {
    /* storage unavailable: token simply is not remembered */
  }
}

export async function request(path, { method = 'GET', params, body, admin = false, signal, raw = false } = {}) {
  const controller = new AbortController()
  const timer = setTimeout(() => controller.abort(), TIMEOUT_MS)
  if (signal) signal.addEventListener('abort', () => controller.abort(), { once: true })
  const headers = {}
  if (admin) headers['X-Admin-Token'] = getAdminToken()
  let payload = body
  if (body && !(body instanceof FormData)) {
    headers['Content-Type'] = 'application/json'
    payload = JSON.stringify(body)
  }
  let res
  try {
    res = await fetch(`${BASE}${path}${buildQuery(params)}`, { method, headers, body: payload, signal: controller.signal })
  } catch (err) {
    if (signal?.aborted) throw err
    throw new ApiError(
      err.name === 'AbortError' ? 'The request timed out.' : 'Cannot reach the ncRNAAtlas API. Is the backend running?',
    )
  } finally {
    clearTimeout(timer)
  }
  if (raw && res.ok) return res
  let json = null
  try {
    json = await res.json()
  } catch {
    /* non-JSON response */
  }
  if (!res.ok) {
    const e = json?.error || {}
    throw new ApiError(e.message || `Request failed (HTTP ${res.status})`, {
      status: res.status,
      code: e.code || 'http_error',
      details: e.details,
    })
  }
  return json
}

export const api = {
  health: () => request('/health'),
  statistics: () => request('/statistics'),
  sources: () => request('/sources'),
  vocabularies: () => request('/vocabularies'),
  importJobs: (params) => request('/import-jobs', { params }),
  importJob: (id) => request(`/import-jobs/${id}`),
  search: (q, params) => request('/search', { params: { q, ...params } }),
  suggest: (q, signal) => request('/search/suggest', { params: { q }, signal }),

  ncrnas: (params) => request('/ncrnas', { params }),
  ncrna: (id) => request(`/ncrnas/${id}`),
  ncrnaAssociations: (id, params) => request(`/ncrnas/${id}/associations`, { params }),
  ncrnaGenes: (id, params) => request(`/ncrnas/${id}/genes`, { params }),
  ncrnaPathways: (id) => request(`/ncrnas/${id}/pathways`),
  ncrnaPublications: (id, params) => request(`/ncrnas/${id}/publications`, { params }),

  diseases: (params) => request('/diseases', { params }),
  disease: (id) => request(`/diseases/${id}`),
  diseaseAssociations: (id, params) => request(`/diseases/${id}/associations`, { params }),
  diseaseGenes: (id) => request(`/diseases/${id}/genes`),
  diseasePathways: (id) => request(`/diseases/${id}/pathways`),
  diseasePublications: (id, params) => request(`/diseases/${id}/publications`, { params }),

  genes: (params) => request('/genes', { params }),
  gene: (id) => request(`/genes/${id}`),
  geneAssociations: (id, params) => request(`/genes/${id}/associations`, { params }),
  genePathways: (id) => request(`/genes/${id}/pathways`),

  associations: (params) => request('/associations', { params }),
  association: (id) => request(`/associations/${id}`),
  associationPublications: (id) => request(`/associations/${id}/publications`),
  associationSources: (id) => request(`/associations/${id}/sources`),
  associationReviews: (id) => request(`/associations/${id}/reviews`),

  publication: (pmid) => request(`/publications/${pmid}`),
  literatureSearch: (q, params) => request('/literature/search', { params: { q, ...params } }),

  pathways: (params) => request('/pathways', { params }),
  pathway: (id) => request(`/pathways/${id}`),
  network: (params) => request('/network', { params }),

  admin: {
    verify: () => request('/admin/verify', { method: 'POST', admin: true }),
    adapters: () => request('/admin/adapters', { admin: true }),
    upload: (form) => request('/admin/uploads', { method: 'POST', body: form, admin: true }),
    commit: (uploadId, body) => request(`/admin/uploads/${uploadId}/commit`, { method: 'POST', body, admin: true }),
    report: (jobId, format) =>
      request(`/admin/import-jobs/${jobId}/report`, { params: { format }, admin: true, raw: true }),
    qualityReport: () => request('/admin/quality-report', { admin: true }),
    reviewQueue: () => request('/admin/review-queue', { admin: true }),
    triage: (id, body) => request(`/admin/associations/${id}/triage`, { method: 'POST', body, admin: true }),
    review: (id, body) => request(`/admin/associations/${id}/reviews`, { method: 'POST', body, admin: true }),
  },
}
