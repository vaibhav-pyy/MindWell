// Thin fetch wrapper for the Flask API.
// Session = HttpOnly cookie; writes carry the CSRF token in X-CSRF-Token.

let csrfToken = null;

export class ApiError extends Error {
  constructor(message, status, code, details) {
    super(message);
    this.status = status;
    this.code = code;
    this.details = details || {};
  }
}

export function setCsrf(token) {
  if (token) csrfToken = token;
}

async function ensureCsrf() {
  if (csrfToken) return csrfToken;
  const res = await fetch('/api/auth/csrf', { credentials: 'same-origin' });
  const body = await res.json();
  csrfToken = body?.data?.csrf_token;
  return csrfToken;
}

let onUnauthenticated = () => {};
export function setUnauthenticatedHandler(fn) {
  onUnauthenticated = fn;
}

async function request(method, url, body, { retry = true } = {}) {
  const headers = { Accept: 'application/json' };
  if (method !== 'GET') {
    headers['Content-Type'] = 'application/json';
    headers['X-CSRF-Token'] = await ensureCsrf();
  }
  let res;
  try {
    res = await fetch(url, {
      method,
      headers,
      credentials: 'same-origin',
      body: method === 'GET' || body === undefined ? undefined : JSON.stringify(body),
    });
  } catch {
    throw new ApiError("Can't reach the MindWell server. Check your connection and try again.", 0, 'network');
  }
  let payload = null;
  try {
    payload = await res.json();
  } catch {
    /* non-JSON */
  }
  if (payload?.data?.csrf_token) setCsrf(payload.data.csrf_token);
  if (!res.ok || !payload?.ok) {
    const err = payload?.error || {};
    if (err.code === 'csrf_failed' && retry) {
      csrfToken = null;
      return request(method, url, body, { retry: false });
    }
    if (res.status === 401 && err.code === 'unauthenticated') onUnauthenticated();
    throw new ApiError(err.message || `Request failed (${res.status})`, res.status, err.code, err.details);
  }
  return payload.data;
}

export const api = {
  get: (url) => request('GET', url),
  post: (url, body = {}) => request('POST', url, body),
  put: (url, body = {}) => request('PUT', url, body),
  patch: (url, body = {}) => request('PATCH', url, body),
  del: (url, body) => request('DELETE', url, body),
};

export function newRequestId() {
  if (crypto?.randomUUID) return crypto.randomUUID();
  return `req-${Date.now()}-${Math.random().toString(36).slice(2, 10)}`;
}
