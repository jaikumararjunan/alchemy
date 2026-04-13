/**
 * Extract readable error message from API error responses.
 */
export function getErrorMessage(error, fallback = 'Something went wrong') {
  if (!error) return fallback
  const data = error?.response?.data
  if (data) {
    if (typeof data === 'string') return data
    if (typeof data.detail === 'string') return data.detail
    if (typeof data.detail?.message === 'string') return data.detail.message
    if (typeof data.message === 'string') return data.message
    if (data.detail && typeof data.detail === 'object') {
      return JSON.stringify(data.detail).replace(/[{}"]/g, '').slice(0, 100)
    }
  }
  if (typeof error.message === 'string' && !error.message.startsWith('Request failed')) return error.message
  const status = error?.response?.status
  if (status === 401) return 'Session expired. Please log in again.'
  if (status === 403) return 'Access denied.'
  if (status === 422) return 'Invalid input. Check your data.'
  if (status === 429) return 'Too many requests. Wait a moment.'
  if (status === 502) return 'Exchange connection failed.'
  return fallback
}
