import React, { useEffect, useState } from 'react';
import { Navigate, Route, Routes, useNavigate } from 'react-router-dom';
import api from './services/api';

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
        <input value={username} onChange={event => setUsername(event.target.value)} required />
        <label>Password</label>
        <input type="password" value={password} onChange={event => setPassword(event.target.value)} required />
        {error && <p className="error">{error}</p>}
        <button type="submit">Sign in</button>
      </form>
    </main>
  );
}

function Dashboard() {
  const [documents, setDocuments] = useState([]);
  const [search, setSearch] = useState('');
  const [file, setFile] = useState(null);
  const [busy, setBusy] = useState(false);
  const [notice, setNotice] = useState('');
  const [question, setQuestion] = useState('');
  const [answer, setAnswer] = useState('');
  const [citations, setCitations] = useState([]);
  const [conversationId, setConversationId] = useState(null);
  const [scope, setScope] = useState('all');
  const [preview, setPreview] = useState(null);
  const navigate = useNavigate();

  async function loadDocuments() {
    try {
      const response = await api.get('/documents', { params: { q: search } });
      setDocuments(response.data);
    } catch (error) {
      setNotice(error.response?.data?.message || 'Could not load documents. Check that the backend is running.');
    }
  }

  useEffect(() => { loadDocuments(); }, [search]);

  async function uploadDocument(event) {
    event.preventDefault();
    if (!file) return;
    setBusy(true);
    setNotice('Uploading and processing your document…');
    try {
      const formData = new FormData();
      formData.append('file', file);
      const response = await api.post('/documents', formData);
      setFile(null);
      event.target.reset();
      setNotice(response.data.status === 'PROCESSED'
        ? 'Document uploaded and indexed successfully.'
        : `Upload saved, but processing status is ${response.data.status}. ${response.data.errorMessage || ''}`);
      await loadDocuments();
    } catch (error) {
      setNotice(error.response?.data?.message || 'Upload failed. Check file type, size and backend logs.');
    } finally {
      setBusy(false);
    }
  }

  async function viewDocument(document) {
    try {
      const [fileResponse, textResponse] = await Promise.all([
        api.get(`/documents/${document.id}/view`, { responseType: 'blob' }),
        api.get(`/documents/${document.id}/content`)
      ]);
      const contentType = fileResponse.headers['content-type'] || document.contentType || '';
      // Only PDF and images are embedded. HTML/SVG files are shown as extracted text, never executed in an iframe.
      const canPreviewInBrowser = contentType.includes('pdf') || contentType.startsWith('image/');
      const previewUrl = canPreviewInBrowser ? URL.createObjectURL(fileResponse.data) : null;
      setPreview({
        name: document.originalFilename,
        content: textResponse.data.content || '(No readable text was extracted from this file.)',
        url: previewUrl
      });
    } catch (error) {
      setNotice(error.response?.data?.message || 'Could not open this document.');
    }
  }

  async function downloadDocument(document) {
    try {
      const response = await api.get(`/documents/${document.id}/download`, { responseType: 'blob' });
      const url = URL.createObjectURL(response.data);
      const link = window.document.createElement('a');
      link.href = url;
      link.download = document.originalFilename;
      window.document.body.appendChild(link);
      link.click();
      link.remove();
      URL.revokeObjectURL(url);
    } catch (error) {
      setNotice(error.response?.data?.message || 'Download failed.');
    }
  }

  async function deleteDocument(id) {
    if (!window.confirm('Permanently delete this document and its indexed passages?')) return;
    try {
      await api.delete(`/documents/${id}`);
      setNotice('Document and its AI index were deleted successfully.');
      if (String(scope) === String(id)) setScope('all');
      await loadDocuments();
    } catch (error) {
      setNotice(error.response?.data?.message || 'Delete failed.');
    }
  }

  async function askQuestion(event) {
    event.preventDefault();
    if (!question.trim()) return;
    setBusy(true);
    setAnswer('Searching your documents and generating an answer…');
    setCitations([]);
    try {
      const response = await api.post('/chat', {
        conversationId,
        documentId: scope === 'all' ? null : Number(scope),
        message: question.trim()
      });
      setConversationId(response.data.conversationId);
      setAnswer(response.data.answer);
      setCitations(response.data.citations || []);
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

  return (
    <div className="app">
      <header>
        <div className="logo">🔐 DocLock</div>
        <div className="headright">Personal Document Intelligence <button type="button" className="secondary" onClick={logout}>Logout</button></div>
      </header>

      <main className="layout">
        <section>
          <div className="sectionhead">
            <div><h1>Your documents</h1><p>Upload, view, download and manage your files</p></div>
            <span className="count">{documents.length} files</span>
          </div>

          <form className="upload" onSubmit={uploadDocument}>
            <input type="file" onChange={event => setFile(event.target.files?.[0] || null)}
              accept=".pdf,.doc,.docx,.txt,.ppt,.pptx,.xls,.xlsx,.csv,.rtf,.html,.htm,.xml,.odt,.ods,.odp,.png,.jpg,.jpeg,.gif,.bmp,.tif,.tiff" />
            <button disabled={busy || !file}>{busy ? 'Please wait…' : 'Upload document'}</button>
          </form>
          {notice && <div className="notice">{notice}</div>}
          <input className="search" placeholder="Search documents by filename…" value={search} onChange={event => setSearch(event.target.value)} />

          <div className="doclist">
            {documents.map(document => (
              <article className="doc" key={document.id}>
                <div className="fileicon">📄</div>
                <div className="docinfo">
                  <b>{document.originalFilename}</b>
                  <small>{(document.size / 1024).toFixed(1)} KB · {document.status} · {new Date(document.uploadedAt).toLocaleString()}</small>
                  {document.errorMessage && <small className="error">{document.errorMessage}</small>}
                </div>
                <button type="button" className="secondary" onClick={() => viewDocument(document)}>View</button>
                <button type="button" className="secondary" onClick={() => downloadDocument(document)}>Download</button>
                <button type="button" className="danger" onClick={() => deleteDocument(document.id)}>Delete</button>
              </article>
            ))}
            {!documents.length && <div className="empty">No documents found. Upload a file to get started.</div>}
          </div>
        </section>

        <aside>
          <div className="chat-heading"><div><h2>DocLock AI</h2><p>Ask questions grounded in your documents.</p></div><button type="button" className="secondary" onClick={newChat}>New chat</button></div>
          <label>Search scope</label>
          <select value={scope} onChange={event => setScope(event.target.value)}>
            <option value="all">All documents</option>
            {documents.map(document => <option key={document.id} value={document.id}>{document.originalFilename}</option>)}
          </select>
          <div className="answer">{answer || 'Your RAG-powered answers and source references will appear here.'}</div>
          {citations.length > 0 && <div className="citations"><b>Retrieved sources</b>{citations.map((source, index) => <small key={`${source.documentId}-${source.chunk}-${index}`}>{source.filename} · passage {source.chunk}</small>)}</div>}
          <form onSubmit={askQuestion}>
            <textarea value={question} onChange={event => setQuestion(event.target.value)} placeholder="Example: Summarize my resume or explain the AWS services in my document…" rows="4" />
            <button disabled={busy || !question.trim()}>{busy ? 'Generating…' : 'Ask DocLock AI'}</button>
          </form>
          <small>RAG retrieves relevant passages using embeddings and keyword matching. Ollama generates the grounded answer.</small>
        </aside>
      </main>

      {preview && <div className="modal-backdrop" onClick={() => { if (preview.url) URL.revokeObjectURL(preview.url); setPreview(null); }}>
        <section className="preview-modal" onClick={event => event.stopPropagation()}>
          <div className="preview-title"><h2>{preview.name}</h2><button className="secondary" onClick={() => { if (preview.url) URL.revokeObjectURL(preview.url); setPreview(null); }}>Close</button></div>
          {preview.url ? <iframe className="file-preview" title={preview.name} src={preview.url} /> : <pre>{preview.content}</pre>}
        </section>
      </div>}
    </div>
  );
}

export default function App() {
  return <Routes>
    <Route path="/login" element={<Login />} />
    <Route path="*" element={localStorage.getItem('doclock_jwt') ? <Dashboard /> : <Navigate to="/login" replace />} />
  </Routes>;
}
