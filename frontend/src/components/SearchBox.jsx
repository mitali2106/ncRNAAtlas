import { Search } from 'lucide-react'
import { useEffect, useId, useRef, useState } from 'react'
import { useNavigate } from 'react-router-dom'
import { useDebounce } from '../hooks/useApi'
import { api } from '../services/api'

const TYPE_PATH = { ncrna: '/ncrnas', disease: '/diseases', gene: '/genes', publication: '/publications' }
const TYPE_LABEL = { ncrna: 'ncRNA', disease: 'Disease', gene: 'Gene', publication: 'PMID' }

/** Global search with debounced autocomplete drawn from real database records. */
export default function SearchBox({ compact = false, initial = '', autoFocus = false }) {
  const [q, setQ] = useState(initial)
  const [items, setItems] = useState([])
  const [open, setOpen] = useState(false)
  const [active, setActive] = useState(-1)
  const [status, setStatus] = useState('idle')
  const debounced = useDebounce(q.trim(), 250)
  const navigate = useNavigate()
  const listId = useId()
  const boxRef = useRef(null)

  useEffect(() => {
    if (debounced.length < 2) {
      setItems([])
      setStatus('idle')
      return undefined
    }
    const controller = new AbortController()
    setStatus('loading')
    api
      .suggest(debounced, controller.signal)
      .then((json) => {
        setItems(json.data)
        setActive(-1)
        setStatus('done')
      })
      .catch((err) => {
        if (err.name !== 'AbortError') {
          setItems([])
          setStatus('error')
        }
      })
    return () => controller.abort()
  }, [debounced])

  useEffect(() => {
    const close = (e) => boxRef.current && !boxRef.current.contains(e.target) && setOpen(false)
    document.addEventListener('mousedown', close)
    return () => document.removeEventListener('mousedown', close)
  }, [])

  const go = (item) => {
    setOpen(false)
    navigate(`${TYPE_PATH[item.type]}/${item.id}`)
  }

  const submit = (e) => {
    e.preventDefault()
    if (active >= 0 && items[active]) return go(items[active])
    if (q.trim().length >= 2) {
      setOpen(false)
      navigate(`/search?q=${encodeURIComponent(q.trim())}`)
    }
    return undefined
  }

  const onKey = (e) => {
    if (!open || !items.length) return
    if (e.key === 'ArrowDown') {
      e.preventDefault()
      setActive((a) => Math.min(a + 1, items.length - 1))
    } else if (e.key === 'ArrowUp') {
      e.preventDefault()
      setActive((a) => Math.max(a - 1, -1))
    } else if (e.key === 'Escape') {
      setOpen(false)
    }
  }

  return (
    <form className={`searchbox ${compact ? 'compact' : ''}`} onSubmit={submit} role="search" ref={boxRef}>
      <Search size={compact ? 16 : 20} className="searchbox-icon" aria-hidden />
      <input
        type="search"
        value={q}
        maxLength={100}
        autoFocus={autoFocus}
        placeholder={compact ? 'Search…' : 'Search ncRNAs (hsa-mir-21, MALAT1, MI0000077), diseases, genes, PMIDs…'}
        aria-label="Search ncRNAs, diseases, genes and publications"
        role="combobox"
        aria-expanded={open && items.length > 0}
        aria-controls={listId}
        aria-autocomplete="list"
        aria-activedescendant={active >= 0 ? `${listId}-${active}` : undefined}
        onChange={(e) => {
          setQ(e.target.value)
          setOpen(true)
        }}
        onFocus={() => setOpen(true)}
        onKeyDown={onKey}
      />
      {!compact && (
        <button type="submit" className="btn btn-primary">
          Search
        </button>
      )}
      {open && debounced.length >= 2 && (
        <ul className="suggestions" id={listId} role="listbox">
          {status === 'loading' && !items.length && <li className="muted">Searching…</li>}
          {status === 'error' && <li className="muted">Suggestions unavailable</li>}
          {status === 'done' && !items.length && <li className="muted">No matching records in the database</li>}
          {items.map((item, i) => (
            <li
              key={`${item.type}-${item.id}`}
              id={`${listId}-${i}`}
              role="option"
              aria-selected={i === active}
              className={i === active ? 'active' : ''}
              onMouseDown={(e) => {
                e.preventDefault()
                go(item)
              }}
            >
              <span className={`sugg-type t-${item.type}`}>{TYPE_LABEL[item.type]}</span>
              <span className="sugg-label">{item.label}</span>
              <span className="sugg-detail">{item.detail}</span>
            </li>
          ))}
        </ul>
      )}
    </form>
  )
}
