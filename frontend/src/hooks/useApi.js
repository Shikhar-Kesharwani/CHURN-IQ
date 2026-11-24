import { useCallback, useEffect, useRef, useState } from 'react'

/**
 * Runs `loader(signal)` (which must resolve to { data, error }) whenever `deps`
 * change, and exposes { data, error, loading, reload }.
 *
 * - State is cleared when deps change, so a page never shows the previous
 *   item's data while the next one loads (CHURN-28).
 * - Responses from an outdated request are ignored, and the request is aborted
 *   on unmount or when deps change.
 */
export function useApi(loader, deps) {
  const [state, setState] = useState({ data: null, error: null, loading: true })
  const [attempt, setAttempt] = useState(0)
  const loaderRef = useRef(loader)
  loaderRef.current = loader

  useEffect(() => {
    const controller = new AbortController()
    let active = true
    setState({ data: null, error: null, loading: true })
    loaderRef.current(controller.signal).then(({ data, error }) => {
      if (!active) return
      setState({ data: error ? null : data, error: error || null, loading: false })
    })
    return () => { active = false; controller.abort() }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [...deps, attempt])

  const reload = useCallback(() => setAttempt(a => a + 1), [])
  return { ...state, reload }
}
