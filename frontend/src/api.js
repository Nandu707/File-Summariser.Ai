const API_BASE_URL = import.meta.env.VITE_API_URL || 'http://localhost:8000';

function getAuthHeaders(extraHeaders = {}) {
  const headers = { ...extraHeaders };
  try {
    const token = localStorage.getItem('auth_token');
    if (token) {
      headers['Authorization'] = `Bearer ${token}`;
    }
  } catch {}
  return headers;
}

export async function checkHealth() {
  const res = await fetch(`${API_BASE_URL}/api/health`, {
    credentials: 'include',
  });
  if (!res.ok) throw new Error(`Health check failed: ${res.statusText}`);
  return res.json();
}

export async function uploadDocument(file) {
  const formData = new FormData();
  formData.append('file', file);

  const res = await fetch(`${API_BASE_URL}/api/upload`, {
    method: 'POST',
    headers: getAuthHeaders(),
    credentials: 'include',
    body: formData,
  });

  if (!res.ok) {
    const errorData = await res.json().catch(() => ({ detail: res.statusText }));
    throw new Error(errorData.detail || 'Upload failed');
  }

  return res.json();
}

export async function askQuestion(docId, question, chatId = null) {
  const res = await fetch(`${API_BASE_URL}/api/ask`, {
    method: 'POST',
    headers: getAuthHeaders({
      'Content-Type': 'application/json',
    }),
    credentials: 'include',
    body: JSON.stringify({
      doc_id: docId,
      chat_id: chatId,
      question: question,
    }),
  });

  if (!res.ok) {
    const errorData = await res.json().catch(() => ({ detail: res.statusText }));
    throw new Error(errorData.detail || 'Query failed');
  }

  return res.json();
}

export async function getDocuments() {
  const res = await fetch(`${API_BASE_URL}/api/documents`, {
    headers: getAuthHeaders(),
    credentials: 'include',
  });
  if (!res.ok) throw new Error('Failed to fetch documents');
  return res.json();
}

export async function deleteDocument(docId) {
  const res = await fetch(`${API_BASE_URL}/api/documents/${docId}`, {
    method: 'DELETE',
    headers: getAuthHeaders(),
    credentials: 'include',
  });
  if (!res.ok) throw new Error('Failed to delete document');
  return res.json();
}

export async function getSuggestedQuestions(docId) {
  const res = await fetch(`${API_BASE_URL}/api/documents/${docId}/suggested-questions`, {
    headers: getAuthHeaders(),
    credentials: 'include',
  });
  if (!res.ok) throw new Error('Failed to fetch suggested questions');
  return res.json();
}

export async function getSequentialQuestions(docId, question, answer = '') {
  const res = await fetch(`${API_BASE_URL}/api/sequential-questions`, {
    method: 'POST',
    headers: getAuthHeaders({
      'Content-Type': 'application/json',
    }),
    credentials: 'include',
    body: JSON.stringify({
      doc_id: docId,
      question: question,
      answer: answer,
    }),
  });
  if (!res.ok) throw new Error('Failed to generate sequential questions');
  return res.json();
}

export async function getDocumentChat(docId) {
  const res = await fetch(`${API_BASE_URL}/api/documents/${docId}/chat`, {
    headers: getAuthHeaders(),
    credentials: 'include',
  });
  if (!res.ok) throw new Error('Failed to fetch chat history');
  return res.json();
}

export async function clearDocumentChat(docId) {
  const res = await fetch(`${API_BASE_URL}/api/documents/${docId}/chat`, {
    method: 'DELETE',
    headers: getAuthHeaders(),
    credentials: 'include',
  });
  if (!res.ok) throw new Error('Failed to clear chat history');
  return res.json();
}

export async function getDocumentPage(docId, pageNum) {
  const res = await fetch(`${API_BASE_URL}/api/documents/${docId}/pages/${pageNum}`, {
    headers: getAuthHeaders(),
    credentials: 'include',
  });
  if (!res.ok) throw new Error(`Failed to load page ${pageNum}`);
  return res.json();
}

export function getDocumentFileUrl(docId, pageNum = null) {
  const base = `${API_BASE_URL}/api/documents/${docId}/file`;
  return pageNum ? `${base}#page=${pageNum}` : base;
}

export async function runManualChatCleanup(retentionDays = 30) {
  const res = await fetch(`${API_BASE_URL}/api/auth/run-cleanup`, {
    method: 'POST',
    headers: getAuthHeaders({
      'Content-Type': 'application/json',
    }),
    credentials: 'include',
    body: JSON.stringify({ retention_days: retentionDays }),
  });
  if (!res.ok) throw new Error('Failed to run chat cleanup');
  return res.json();
}
