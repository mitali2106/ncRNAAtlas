import { useCallback, useEffect, useRef, useState } from 'react'

/**
 * Run an API call when its dependencies change.
 * Returns { data, meta, error, loading, reload } where `meta` is the full JSON
 * envelope (pagination, notes ...) and `data` is its `data` member.
 */
export function useApi(fn, deps = [], { enabled = true } = {}) {
  const [state, setState] = useState({ data: null, meta: null, error: null, loading: enabled })
  const [tick, setTick] = useState(0)
  const fnRef = useRef(fn)
  fnRef.current = fn

  useEffect(() => {
    if (!enabled) {
      setState({ data: null, meta: null, error: null, loading: false })
      return undefined
    }
    let cancelled = false
    setState((s) => ({ ...s, loading: true, error: null }))
    fnRef
      .current()
      .then((json) => {
        if (!cancelled) setState({ data: json?.data ?? null, meta: json, error: null, loading: false })
      })
      .catch((error) => {
        if (!cancelled) setState({ data: null, meta: null, error, loading: false })
      })
    return () => {
      cancelled = true
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [...deps, tick, enabled])

  const reload = useCallback(() => setTick((t) => t + 1), [])
  return { ...state, reload }
}

export function useDebounce(value, delay = 250) {
  const [debounced, setDebounced] = useState(value)
  useEffect(() => {
    const t = setTimeout(() => setDebounced(value), delay)
    return () => clearTimeout(t)
  }, [value, delay])
  return debounced
}
