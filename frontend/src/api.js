async function req(method, url, body) {
  const r = await fetch(url, {
    method,
    headers: body ? { 'content-type': 'application/json' } : undefined,
    body: body ? JSON.stringify(body) : undefined,
  })
  if (!r.ok) {
    let msg = `${r.status}`
    try { msg = (await r.json()).detail || msg } catch { /* ignore */ }
    throw new Error(typeof msg === 'string' ? msg : JSON.stringify(msg))
  }
  return r.json()
}

export const api = {
  users: () => req('GET', '/api/users'),
  createUser: (b) => req('POST', '/api/users', b),
  deleteUser: (uid) => req('DELETE', `/api/users/${uid}`),
  projects: () => req('GET', '/api/projects'),
  project: (pid) => req('GET', `/api/projects/${pid}`),
  createProject: (b) => req('POST', '/api/projects', b),
  updateProject: (pid, b) => req('PATCH', `/api/projects/${pid}`, b),
  deleteProject: (pid) => req('DELETE', `/api/projects/${pid}`),
  jobs: (pid) => req('GET', `/api/projects/${pid}/jobs`),
  createJob: (pid, b) => req('POST', `/api/projects/${pid}/jobs`, b),
  updateJob: (jid, b) => req('PATCH', `/api/jobs/${jid}`, b),
  deleteJob: (jid) => req('DELETE', `/api/jobs/${jid}`),
  datasets: (pid) => req('GET', `/api/projects/${pid}/datasets`),
  imports: (pid) => req('GET', `/api/projects/${pid}/imports`),
  createImport: (pid, b) => req('POST', `/api/projects/${pid}/imports`, b),
  episodes: (pid, params = {}) => {
    const q = new URLSearchParams(
      Object.entries(params).filter(([, v]) => v !== undefined && v !== '')).toString()
    return req('GET', `/api/projects/${pid}/episodes${q ? '?' + q : ''}`)
  },
  episode: (eid) => req('GET', `/api/episodes/${eid}`),
  timeseries: (eid) => req('GET', `/api/episodes/${eid}/timeseries`),
  saveLabels: (eid, b) => req('PUT', `/api/episodes/${eid}/labels`, b),
  review: (eid, b) => req('POST', `/api/episodes/${eid}/review`, b),
  exportDataset: (did) => req('POST', `/api/datasets/${did}/export`),
  dashboard: (pid) => req('GET', `/api/dashboard${pid ? `?project_id=${pid}` : ''}`),
  trainingDatasets: () => req('GET', '/api/training-datasets'),
  createTrainingDataset: (b) => req('POST', '/api/training-datasets', b),
  updateTrainingDataset: (tid, b) => req('PATCH', `/api/training-datasets/${tid}`, b),
  deleteTrainingDataset: (tid) => req('DELETE', `/api/training-datasets/${tid}`),
  tdsPreview: (tid) => req('GET', `/api/training-datasets/${tid}/preview`),
  tdsExports: (tid) => req('GET', `/api/training-datasets/${tid}/exports`),
  startExport: (tid) => req('POST', `/api/training-datasets/${tid}/exports`),
}
