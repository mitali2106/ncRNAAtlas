import { FilterX } from 'lucide-react'
import { useState } from 'react'
import { Link } from 'react-router-dom'
import { useApi, useDebounce } from '../hooks/useApi'
import { ASSOCIATION_TYPES, EVIDENCE_LEVELS, VALIDATION_STATUSES, label } from '../utils/labels'
import { Direction, EmptyState, ErrorState, EvidenceBadge, Loading, Pagination, TypeBadge, ValidationBadge } from './common'

const EMPTY = {
  q: '',
  ncrna_type: '',
  evidence_level: '',
  validation_status: '',
  association_type: '',
  source: '',
  year_from: '',
  year_to: '',
}

const SOURCES = ['HMDD', 'LncRNADisease', 'ncRNAAtlas curated sample']

/**
 * Filterable, paginated association list.
 * `fetcher(params)` returns a promise of the API envelope; `hide` hides columns/filters
 * that are fixed by the page (e.g. the ncRNA on an ncRNA page).
 */
export default function AssociationTable({ fetcher, deps = [], hide = [], emptyText, initialFilters = {} }) {
  const [filters, setFilters] = useState({ ...EMPTY, ...initialFilters })
  const [page, setPage] = useState(1)
  const [sort, setSort] = useState('publications')
  const q = useDebounce(filters.q, 300)
  const params = { ...filters, q, page, per_page: 20, sort, order: sort === 'publications' ? 'desc' : 'asc' }
  const { data, meta, error, loading, reload } = useApi(
    () => fetcher(params),
    [...deps, q, filters.ncrna_type, filters.evidence_level, filters.validation_status, filters.association_type,
      filters.source, filters.year_from, filters.year_to, page, sort],
  )
  const set = (k) => (e) => {
    setFilters((f) => ({ ...f, [k]: e.target.value }))
    setPage(1)
  }
  const active = Object.entries(filters).some(([k, v]) => v && !(k in initialFilters && initialFilters[k] === v))
  const show = (col) => !hide.includes(col)

  return (
    <div className="assoc-table">
      <div className="filters" role="group" aria-label="Association filters">
        <input
          type="search"
          placeholder={show('ncrna') && show('disease') ? 'Filter by ncRNA or disease name' : 'Filter by name'}
          value={filters.q}
          onChange={set('q')}
          aria-label="Filter by name"
          maxLength={100}
        />
        {show('ncrna_type') && (
          <select value={filters.ncrna_type} onChange={set('ncrna_type')} aria-label="RNA type">
            <option value="">All RNA types</option>
            <option value="miRNA">miRNA</option>
            <option value="lncRNA">lncRNA</option>
          </select>
        )}
        <select value={filters.evidence_level} onChange={set('evidence_level')} aria-label="Evidence level">
          <option value="">All evidence levels</option>
          {Object.entries(EVIDENCE_LEVELS).map(([k, v]) => (
            <option key={k} value={k}>
              {v}
            </option>
          ))}
        </select>
        <select value={filters.validation_status} onChange={set('validation_status')} aria-label="Validation status">
          <option value="">All review statuses</option>
          {Object.entries(VALIDATION_STATUSES).map(([k, v]) => (
            <option key={k} value={k}>
              {v}
            </option>
          ))}
        </select>
        <select value={filters.association_type} onChange={set('association_type')} aria-label="Association type">
          <option value="">All association types</option>
          {Object.entries(ASSOCIATION_TYPES).map(([k, v]) => (
            <option key={k} value={k}>
              {v}
            </option>
          ))}
        </select>
        <select value={filters.source} onChange={set('source')} aria-label="Source database">
          <option value="">All sources</option>
          {SOURCES.map((s) => (
            <option key={s} value={s}>
              {s}
            </option>
          ))}
        </select>
        <input
          type="number"
          placeholder="Year from"
          value={filters.year_from}
          onChange={set('year_from')}
          aria-label="Publication year from"
          min="1950"
          max="2100"
        />
        <input
          type="number"
          placeholder="Year to"
          value={filters.year_to}
          onChange={set('year_to')}
          aria-label="Publication year to"
          min="1950"
          max="2100"
        />
        <select value={sort} onChange={(e) => setSort(e.target.value)} aria-label="Sort by">
          <option value="publications">Most publications</option>
          <option value="ncrna">ncRNA name</option>
          <option value="disease">Disease name</option>
          <option value="evidence">Evidence level</option>
          <option value="type">Association type</option>
        </select>
        {active && (
          <button
            type="button"
            className="btn btn-small"
            onClick={() => {
              setFilters({ ...EMPTY, ...initialFilters })
              setPage(1)
            }}
          >
            <FilterX size={14} aria-hidden /> Clear filters
          </button>
        )}
      </div>

      {loading && <Loading text="Loading associations…" />}
      <ErrorState error={error} onRetry={reload} what="associations" />
      {!loading && !error && data && data.length === 0 && (
        <EmptyState title={active ? 'No associations match these filters' : 'No recorded associations'}>
          {active ? 'Try removing a filter.' : emptyText}
        </EmptyState>
      )}
      {!loading && !error && data && data.length > 0 && (
        <>
          <div className="table-wrap">
            <table className="table">
              <thead>
                <tr>
                  {show('ncrna') && <th scope="col">ncRNA</th>}
                  {show('disease') && <th scope="col">Disease</th>}
                  <th scope="col">Type</th>
                  <th scope="col">Direction</th>
                  <th scope="col">Evidence (source)</th>
                  <th scope="col">Curator review</th>
                  <th scope="col">Sources</th>
                  <th scope="col" className="num">
                    PMIDs
                  </th>
                  <th scope="col">
                    <span className="sr-only">Details</span>
                  </th>
                </tr>
              </thead>
              <tbody>
                {data.map((a) => (
                  <tr key={a.id}>
                    {show('ncrna') && (
                      <td>
                        <Link to={`/ncrnas/${a.ncrna.id}`} className="mono">
                          {a.ncrna.canonical_name}
                        </Link>{' '}
                        <TypeBadge type={a.ncrna.ncrna_type} />
                        {a.ncrna.organism !== 'Homo sapiens' && <span className="badge org">{a.ncrna.organism}</span>}
                      </td>
                    )}
                    {show('disease') && (
                      <td>
                        <Link to={`/diseases/${a.disease.id}`}>{a.disease.canonical_name}</Link>
                      </td>
                    )}
                    <td>{label(ASSOCIATION_TYPES, a.association_type)}</td>
                    <td>
                      <Direction value={a.regulation_direction} />
                    </td>
                    <td>
                      <EvidenceBadge level={a.evidence_level} />
                    </td>
                    <td>
                      <ValidationBadge status={a.validation_status} />
                    </td>
                    <td className="small">{a.source_databases.join(', ')}</td>
                    <td className="num">{a.publication_count}</td>
                    <td>
                      <Link to={`/associations/${a.id}`} className="btn btn-small">
                        Evidence
                      </Link>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
          <Pagination pagination={meta.pagination} onPage={setPage} />
        </>
      )}
    </div>
  )
}
