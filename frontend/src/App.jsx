import React, { useCallback, useEffect, useRef, useState } from 'react';
import { Navigate, Route, Routes, useNavigate } from 'react-router-dom';
import api from './services/api';

// Ingestion runs in the background on the server: QUEUED -> EXTRACTING -> INDEXING -> ANALYZING -> PROCESSED (or FAILED)
const PIPELINE = ['QUEUED', 'EXTRACTING', 'INDEXING', 'ANALYZING', 'PROCESSED'];
const STATUS_TEXT = {
  QUEUED: 'Queued',
  EXTRACTING: 'Reading the file…',
  INDEXING: 'Building the search index…',
  ANALYZING: 'Finding dates and amounts…',
  PROCESSED: 'Ready',
  FAILED: 'Failed',
};
const isWorking = (status) => !['PROCESSED', 'FAILED'].includes(status);
const EMBEDDABLE = /\.(pdf|png|jpe?g|gif|bmp)$/i;
const MODES = [
  { value: 'hybrid', label: 'Hybrid (recommended)' },
  { value: 'vector', label: 'Semantic only (embeddings)' },
  { value: 'lexical', label: 'Keyword only (BM25)' },
];

// The API sends timestamps in UTC without a zone suffix; without this the browser would read them as local time.
const parseUtc = (value) => new Date(/[zZ]$|[+-]\d\d:\d\d$/.test(value) ? value : `${value}Z`);
const formatDeadline = (iso) => new Date(`${iso}T00:00:00`).toLocaleDateString(undefined, { day: 'numeric', month: 'short', year: 'numeric' });
const prettify = (key) => key.replace(/_/g, ' ').replace(/^./, (c) => c.toUpperCase());

function Login() {
  const [username, setUsername] = useState('admin');
  const [password, setPassword] = useState('');
  const [error, setError] = useState('');
  const navigate = useNavigate();

  async function login(event) {
    event.preventDefault();
    setError('');
    try {
      const response = await api.post('/auth/login', { username, password });
      localStorage.setItem('doclock_jwt', response.data.token);
      navigate('/');
    } catch (requestError) {
      setError(requestError.response?.data?.message || 'Login failed. Check the backend and your credentials.');
    }
  }

  return (
    <main className="login">
      <form onSubmit={login} className="panel">
        <div className="logo">🔐 DocLock</div>
        <h1>Welcome back</h1>
        <p>Your personal document intelligence workspace</p>
        <label>Username</label>
        <input value={username} onChange={(event) => setUsername(event.target.value)} required />
        <label>Password</label>
        <input type="password" value={password} onChange={(event) => setPassword(event.target.value)} required />
        {error && <p className="error">{error}</p>}
        <button type="submit">Sign in</button>
      </form>
    </main>
  );
}

function StatusLine({ doc }) {
  if (doc.status === 'FAILED') return <small className="error">Failed: {doc.errorMessage || 'unknown error'}</small>;
  if (doc.status === 'PROCESSED') {
    return doc.errorMessage ? <small className="warn">{doc.errorMessage}</small> : null;
  }
  const step = Math.max(PIPELINE.indexOf(doc.status), 0);
  return (
    <div className="progress-wrap">
      <div className="progress"><div className="bar" style={{ width: `${((step + 1) / PIPELINE.length) * 100}%` }} /></div>
      <small>{STATUS_TEXT[doc.status] || doc.status}</small>
    </div>
  );
}

function AlertsPanel({ data, showAll, setShowAll, onToggle, onExport }) {
  const { alerts, summary } = data;
  return (
    <section className="alerts" aria-label="Deadlines and expiries">
      <div className="sectionhead">
        <div><h2>Deadlines &amp; expiries</h2><p>Found automatically in your documents. Always check the original before acting.</p></div>
        <div className="summary">
          {summary.overdue > 0 && <span className="chip overdue">{summary.overdue} overdue</span>}
          {summary.dueSoon > 0 && <span className="chip soon">{summary.dueSoon} due soon</span>}
          {summary.upcoming > 0 && <span className="chip upcoming">{summary.upcoming} upcoming</span>}
        </div>
      </div>
      {alerts.length > 0 && <button type="button" className="secondary calbtn" onClick={onExport}>📅 Add to my calendar (.ics)</button>}
      <label className="check"><input type="checkbox" checked={showAll} onChange={(event) => setShowAll(event.target.checked)} /> Show dismissed</label>
      {alerts.length === 0 && <div className="empty small">No deadlines found yet. Upload a policy, lease or circular to see them here.</div>}
      {alerts.map((alert) => (
        <article className={`alert ${alert.status.toLowerCase()} ${alert.acknowledged ? 'done' : ''}`} key={alert.id}>
          <div className="alert-date">
            <b>{formatDeadline(alert.deadline)}</b>
            <span className={`chip ${alert.status === 'OVERDUE' ? 'overdue' : alert.status === 'DUE_SOON' ? 'soon' : 'upcoming'}`}>
              {alert.daysLeft < 0 ? `${-alert.daysLeft} days overdue` : alert.daysLeft === 0 ? 'today' : `in ${alert.daysLeft} days`}
            </span>
          </div>
          <div className="alert-body">
            <b>{alert.title}</b>
            <small>{alert.filename}</small>
            {alert.description && <small className="quote">“{alert.description}”</small>}
          </div>
          <button type="button" className="secondary" onClick={() => onToggle(alert)}>{alert.acknowledged ? 'Restore' : 'Dismiss'}</button>
        </article>
      ))}
    </section>
  );
}

function FactsTab({ facts }) {
  if (!facts) return <p>Loading…</p>;
  if (!facts.length) return <p className="muted">No dates, amounts or other facts were detected in this document.</p>;
  const groups = facts.reduce((acc, fact) => { (acc[fact.type] = acc[fact.type] || []).push(fact); return acc; }, {});
  return (
    <div className="facts">
      <p className="muted">Detected automatically from the text. Verify against the original before relying on them.</p>
      {Object.entries(groups).map(([type, rows]) => (
        <div key={type}>
          <h3>{type.charAt(0) + type.slice(1).toLowerCase()}s</h3>
          <table><tbody>{rows.map((fact) => <tr key={fact.id}><th>{prettify(fact.name)}</th><td>{fact.value}</td></tr>)}</tbody></table>
        </div>
      ))}
    </div>
  );
}

const VERDICTS = {
  VERIFIED: { cls: 'ok', icon: '✔', text: 'All figures and dates in this answer were found in your documents.' },
  PARTIAL: { cls: 'warn', icon: '⚠', text: 'Some figures in this answer were NOT found in the retrieved text. Check the original.' },
  UNVERIFIED: { cls: 'bad', icon: '✖', text: 'None of the figures in this answer appear in the retrieved text. Do not rely on it.' },
};

function VerificationBadge({ verification }) {
  const info = verification && VERDICTS[verification.verdict];
  if (!info) return null; // NO_FIGURES: nothing numeric to check
  const missing = verification.claims.filter((claim) => !claim.supported);
  return (
    <div className={`verify ${info.cls}`}>
      <b>{info.icon} Answer check: {verification.supported} of {verification.total} figures verified</b>
      <span>{info.text}</span>
      {missing.length > 0 && <small>Not found in sources: {missing.map((claim) => claim.text).join(', ')}</small>}
    </div>
  );
}

function PrivacyCard({ report }) {
  if (!report || report.documentsScanned === 0) return null;
  const parts = Object.entries(report.totals).map(([kind, n]) => `${n} ${report.labels[kind] || kind}`);
  return (
    <section className="privacy" aria-label="Privacy scan">
      <div className="sectionhead"><div><h2>🛡️ Privacy scan</h2>
        <p>{report.documentsWithPii === 0
          ? `No personal identifiers found in your ${report.documentsScanned} documents.`
          : `${report.documentsWithPii} of ${report.documentsScanned} documents contain personal identifiers: ${parts.join(', ')}.`}</p></div></div>
      {report.documents.map((item) => (
        <small key={item.documentId} className="pii-row"><b>{item.filename}</b> {Object.entries(item.counts).map(([kind, n]) => `${n} ${kind}`).join(' · ')}</small>
      ))}
      {report.documentsWithPii > 0 && <small className="muted">Detected locally (Aadhaar via checksum). Values are never shown in full; open a document's “Insights” tab to view or copy a redacted version.</small>}
    </section>
  );
}

function InsightsTab({ insights, redacted }) {
  if (!insights) return <p>Loading…</p>;
  const missing = insights.checklist.filter((row) => !row.found);
  return (
    <div className="facts">
      <h3>Document type</h3>
      <p><b>{insights.typeLabel}</b>{insights.confidence > 0 && <span className="muted"> · confidence {Math.round(insights.confidence * 100)}%</span>}</p>
      {insights.matched.length > 0 && <small className="muted">Decided by: {insights.matched.join(', ')}</small>}
      {insights.checklist.length > 0 && (
        <>
          <h3>Checklist: is anything important missing?</h3>
          <table><tbody>{insights.checklist.map((row) => <tr key={row.item}><th>{row.item}</th><td className={row.found ? 'okc' : 'badc'}>{row.found ? '✔ found' : '✖ not found'}</td></tr>)}</tbody></table>
          {missing.length > 0 && <p className="muted">Not found in the text: {missing.map((row) => row.item).join(', ')}. Check the original, the file may be incomplete or scanned.</p>}
        </>
      )}
      <h3>Personal identifiers</h3>
      {insights.pii.total === 0 ? <p className="muted">None detected.</p> : (
        <table><tbody>{insights.pii.items.map((item, index) => <tr key={index}><th>{item.label}</th><td>{item.masked}</td></tr>)}</tbody></table>
      )}
      <h3>Redacted copy</h3>
      <pre>{redacted ?? 'Loading…'}</pre>
    </div>
  );
}

function Dashboard() {
  const [documents, setDocuments] = useState([]);
  const [alertData, setAlertData] = useState({ alerts: [], summary: { overdue: 0, dueSoon: 0, upcoming: 0 } });
  const [showAllAlerts, setShowAllAlerts] = useState(false);
  const [search, setSearch] = useState('');
  const [file, setFile] = useState(null);
  const [busy, setBusy] = useState(false);
  const [notice, setNotice] = useState('');
  const [question, setQuestion] = useState('');
  const [answer, setAnswer] = useState('');
  const [citations, setCitations] = useState([]);
  const [verification, setVerification] = useState(null);
  const [privacy, setPrivacy] = useState(null);
  const [conversationId, setConversationId] = useState(null);
  const [scope, setScope] = useState('all');
  const [mode, setMode] = useState('hybrid');
  const [preview, setPreview] = useState(null);
  const previewUrl = useRef(null);
  const navigate = useNavigate();

  const loadDocuments = useCallback(async () => {
    try {
      const response = await api.get('/documents', { params: { q: search } });
      setDocuments(response.data);
    } catch (error) {
      setNotice(error.response?.data?.message || 'Could not load documents. Check that the backend is running.');
    }
  }, [search]);

  const loadAlerts = useCallback(async () => {
    try {
      const response = await api.get('/alerts', { params: { includeAcknowledged: showAllAlerts } });
      setAlertData(response.data);
    } catch {
      /* alerts are a bonus panel: never block the page if they fail to load */
    }
  }, [showAllAlerts]);

  useEffect(() => { loadDocuments(); }, [loadDocuments]);
  useEffect(() => { loadAlerts(); }, [loadAlerts]);

  const loadPrivacy = useCallback(async () => {
    try { setPrivacy((await api.get('/privacy')).data); } catch { /* optional panel */ }
  }, []);
  const processedCount = documents.filter((item) => item.status === 'PROCESSED').length;
  useEffect(() => { loadPrivacy(); }, [loadPrivacy, processedCount]);

  async function exportCalendar() {
    try {
      const response = await api.get('/alerts/calendar.ics', { responseType: 'blob' });
      const url = URL.createObjectURL(response.data);
      const link = document.createElement('a');
      link.href = url;
      link.download = 'doclock-deadlines.ics';
      link.click();
      URL.revokeObjectURL(url);
    } catch {
      setNotice('Could not export the calendar file.');
    }
  }

  // Poll only while at least one file is still being processed in the background.
  const anyWorking = documents.some((item) => isWorking(item.status));
  useEffect(() => {
    if (!anyWorking) return undefined;
    const timer = window.setInterval(() => { loadDocuments(); loadAlerts(); }, 2500);
    return () => window.clearInterval(timer);
  }, [anyWorking, loadDocuments, loadAlerts]);

  async function uploadDocument(event) {
    event.preventDefault();
    if (!file) return;
    setBusy(true);
    setNotice('Uploading…');
    try {
      const formData = new FormData();
      formData.append('file', file);
      await api.post('/documents', formData);
      setFile(null);
      event.target.reset();
      setNotice('Upload accepted. Processing continues in the background; this page updates by itself.');
      await loadDocuments();
    } catch (error) {
      setNotice(error.response?.data?.message || 'Upload failed. Check file type, size and backend logs.');
    } finally {
      setBusy(false);
    }
  }

  function closePreview() {
    if (previewUrl.current) URL.revokeObjectURL(previewUrl.current);
    previewUrl.current = null;
    setPreview(null);
  }

  async function viewDocument(doc, tab = 'facts') {
    try {
      setPreview({ name: doc.originalFilename, tab, content: null, facts: null, insights: null, redacted: null, url: null, embeddable: EMBEDDABLE.test(doc.originalFilename) });
      const [textResponse, factsResponse, insightsResponse, redactedResponse] = await Promise.all([
        api.get(`/documents/${doc.id}/content`), api.get(`/documents/${doc.id}/facts`),
        api.get(`/documents/${doc.id}/insights`), api.get(`/documents/${doc.id}/redacted`)]);
      let url = null;
      if (EMBEDDABLE.test(doc.originalFilename)) {
        // Only PDFs and images are embedded; everything else is shown as extracted text and never executed.
        const fileResponse = await api.get(`/documents/${doc.id}/view`, { responseType: 'blob' });
        url = URL.createObjectURL(fileResponse.data);
        previewUrl.current = url;
      }
      setPreview({
        name: doc.originalFilename, tab, url, embeddable: EMBEDDABLE.test(doc.originalFilename),
        content: textResponse.data.content || '(No readable text was extracted from this file.)',
        facts: factsResponse.data.facts, insights: insightsResponse.data, redacted: redactedResponse.data.text,
      });
    } catch (error) {
      setPreview(null);
      setNotice(error.response?.data?.message || 'Could not open this document.');
    }
  }

  async function downloadDocument(doc) {
    try {
      const response = await api.get(`/documents/${doc.id}/download`, { responseType: 'blob' });
      const url = URL.createObjectURL(response.data);
      const link = window.document.createElement('a');
      link.href = url;
      link.download = doc.originalFilename;
      window.document.body.appendChild(link);
      link.click();
      link.remove();
      URL.revokeObjectURL(url);
    } catch (error) {
      setNotice(error.response?.data?.message || 'Download failed.');
    }
  }

  async function deleteDocument(id) {
    if (!window.confirm('Permanently delete this document, its indexed passages and its alerts?')) return;
    try {
      await api.delete(`/documents/${id}`);
      setNotice('Document, search index and alerts were deleted.');
      if (String(scope) === String(id)) setScope('all');
      await Promise.all([loadDocuments(), loadAlerts()]);
    } catch (error) {
      setNotice(error.response?.data?.message || 'Delete failed.');
    }
  }

  async function toggleAlert(alert) {
    try {
      await api.patch(`/alerts/${alert.id}`, { acknowledged: !alert.acknowledged });
      await loadAlerts();
    } catch (error) {
      setNotice(error.response?.data?.message || 'Could not update the alert.');
    }
  }

  async function askQuestion(event) {
    event.preventDefault();
    if (!question.trim()) return;
    setBusy(true);
    setAnswer('Searching your documents and generating an answer…');
    setCitations([]);
    setVerification(null);
    try {
      const response = await api.post('/chat', {
        conversationId,
        documentId: scope === 'all' ? null : Number(scope),
        message: question.trim(),
        retrievalMode: mode,
      }, { timeout: 330000 });
      setConversationId(response.data.conversationId);
      setAnswer(response.data.answer);
      setCitations(response.data.citations || []);
      setVerification(response.data.verification || null);
      setQuestion('');
    } catch (error) {
      setAnswer(error.response?.data?.message || 'Chat request failed. Check the backend and Ollama service.');
    } finally {
      setBusy(false);
    }
  }

  function newChat() {
    setConversationId(null);
    setAnswer('New chat started. Ask a question about your documents.');
    setCitations([]);
  }

  function logout() {
    localStorage.removeItem('doclock_jwt');
    navigate('/login');
  }

  const readyDocs = documents.filter((item) => item.status === 'PROCESSED');
  const urgent = alertData.summary.overdue + alertData.summary.dueSoon;

  return (
    <div className="app">
      <header>
        <div className="logo">🔐 DocLock</div>
        <div className="headright">
          {urgent > 0 && <span className="chip soon" title="Overdue or due within 30 days">⏰ {urgent} need attention</span>}
          Personal Document Intelligence <button type="button" className="secondary" onClick={logout}>Logout</button>
        </div>
      </header>

      <main className="layout">
        <div className="leftcol">
          <AlertsPanel data={alertData} showAll={showAllAlerts} setShowAll={setShowAllAlerts} onToggle={toggleAlert} onExport={exportCalendar} />

          <PrivacyCard report={privacy} />

          <section>
            <div className="sectionhead">
              <div><h1>Your documents</h1><p>Upload, view, download and manage your files</p></div>
              <span className="count">{documents.length} files</span>
            </div>

            <form className="upload" onSubmit={uploadDocument}>
              <input type="file" onChange={(event) => setFile(event.target.files?.[0] || null)}
                accept=".pdf,.doc,.docx,.txt,.ppt,.pptx,.xls,.xlsx,.csv,.rtf,.html,.htm,.xml,.odt,.ods,.odp,.png,.jpg,.jpeg,.gif,.bmp,.tif,.tiff" />
              <button disabled={busy || !file}>{busy ? 'Please wait…' : 'Upload document'}</button>
            </form>
            {notice && <div className="notice">{notice}</div>}
            <input className="search" placeholder="Search documents by filename…" value={search} onChange={(event) => setSearch(event.target.value)} />

            <div className="doclist">
              {documents.map((doc) => (
                <article className="doc" key={doc.id}>
                  <div className="fileicon">📄</div>
                  <div className="docinfo">
                    <b>{doc.originalFilename}</b>
                    <small>{(doc.size / 1024).toFixed(1)} KB · {STATUS_TEXT[doc.status] || doc.status} · {parseUtc(doc.uploadedAt).toLocaleString()}</small>
                    <StatusLine doc={doc} />
                  </div>
                  <button type="button" className="secondary" disabled={doc.status === 'QUEUED'} onClick={() => viewDocument(doc)}>View</button>
                  <button type="button" className="secondary" onClick={() => downloadDocument(doc)}>Download</button>
                  <button type="button" className="danger" onClick={() => deleteDocument(doc.id)}>Delete</button>
                </article>
              ))}
              {!documents.length && <div className="empty">No documents found. Upload a file to get started.</div>}
            </div>
          </section>
        </div>

        <aside>
          <div className="chat-heading"><div><h2>DocLock AI</h2><p>Ask questions grounded in your documents.</p></div><button type="button" className="secondary" onClick={newChat}>New chat</button></div>
          <label>Search scope</label>
          <select value={scope} onChange={(event) => setScope(event.target.value)}>
            <option value="all">All documents</option>
            {readyDocs.map((doc) => <option key={doc.id} value={doc.id}>{doc.originalFilename}</option>)}
          </select>
          <label>Retrieval strategy</label>
          <select value={mode} onChange={(event) => setMode(event.target.value)}>
            {MODES.map((item) => <option key={item.value} value={item.value}>{item.label}</option>)}
          </select>
          <div className="answer">{answer || 'Your RAG-powered answers and source references will appear here.'}</div>
          <VerificationBadge verification={verification} />
          {citations.length > 0 && (
            <div className="citations"><b>Retrieved sources</b>
              {citations.map((source, index) => (
                <details key={`${source.documentId}-${source.chunk}-${index}`}>
                  <summary>{source.filename} · passage {source.chunk}{source.score != null ? ` · score ${source.score}` : ''}</summary>
                  <small className="quote">{source.snippet}…</small>
                </details>
              ))}
            </div>
          )}
          <form onSubmit={askQuestion}>
            <textarea value={question} onChange={(event) => setQuestion(event.target.value)} placeholder="Example: When does my insurance policy expire, and what is the premium?" rows="4" />
            <button disabled={busy || !question.trim()}>{busy ? 'Generating…' : 'Ask DocLock AI'}</button>
          </form>
          <small>Answers use only passages found in your documents. If nothing relevant is found, DocLock says so instead of guessing.</small>
        </aside>
      </main>

      {preview && (
        <div className="modal-backdrop" onClick={closePreview}>
          <section className="preview-modal" onClick={(event) => event.stopPropagation()}>
            <div className="preview-title"><h2>{preview.name}</h2><button className="secondary" onClick={closePreview}>Close</button></div>
            <div className="tabs">
              {['facts', 'insights', 'text', ...(preview.embeddable ? ['file'] : [])].map((tab) => (
                <button key={tab} type="button" className={preview.tab === tab ? 'tab active' : 'tab'} onClick={() => setPreview({ ...preview, tab })}>
                  {tab === 'facts' ? 'Extracted facts' : tab === 'insights' ? 'Insights & privacy' : tab === 'text' ? 'Text' : 'Original file'}
                </button>
              ))}
            </div>
            {preview.tab === 'facts' && <FactsTab facts={preview.facts} />}
            {preview.tab === 'insights' && <InsightsTab insights={preview.insights} redacted={preview.redacted} />}
            {preview.tab === 'text' && <pre>{preview.content ?? 'Loading…'}</pre>}
            {preview.tab === 'file' && (preview.url ? <iframe className="file-preview" title={preview.name} src={preview.url} /> : <p>Loading…</p>)}
          </section>
        </div>
      )}
    </div>
  );
}

// The token must be checked when the route is *shown*. (Evaluating localStorage inside <Route element=...> runs only when
// App first renders, so right after login the stale "no token" result sent you back to /login until a manual refresh.)
function RequireAuth() {
  return localStorage.getItem('doclock_jwt') ? <Dashboard /> : <Navigate to="/login" replace />;
}

export default function App() {
  return (
    <Routes>
      <Route path="/login" element={<Login />} />
      <Route path="*" element={<RequireAuth />} />
    </Routes>
  );
}
