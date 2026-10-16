const API_BASE_URL = import.meta.env.VITE_API_URL || 'http://localhost:8000';

export async function checkHealth() {
  const res = await fetch(`${API_BASE_URL}/api/health`);
  if (!res.ok) throw new Error(`Health check failed: ${res.statusText}`);
  return res.json();
}

export async function uploadDocument(file) {
  const formData = new FormData();
  formData.append('file', file);

  const res = await fetch(`${API_BASE_URL}/api/upload`, {
    method: 'POST',
    body: formData,
  });

  if (!res.ok) {
    const errorData = await res.json().catch(() => ({ detail: res.statusText }));
    throw new Error(errorData.detail || 'Upload failed');
  }

  // Contract: { doc_id: str, filename: str, chunks: int }
  return res.json();
}

export async function askQuestion(docId, question) {
  const res = await fetch(`${API_BASE_URL}/api/ask`, {
    method: 'POST',
    headers: {
      'Content-Type': 'application/json',
    },
    body: JSON.stringify({
      doc_id: docId,
      question: question,
    }),
  });

  if (!res.ok) {
    const errorData = await res.json().catch(() => ({ detail: res.statusText }));
    throw new Error(errorData.detail || 'Query failed');
  }

  // Contract: { answer: str, sources: list[int] }
  return res.json();
}

export async function getDocuments() {
  const res = await fetch(`${API_BASE_URL}/api/documents`);
  if (!res.ok) throw new Error('Failed to fetch documents');
  return res.json();
}

export async function deleteDocument(docId) {
  const res = await fetch(`${API_BASE_URL}/api/documents/${docId}`, {
    method: 'DELETE',
  });
  if (!res.ok) throw new Error('Failed to delete document');
  return res.json();
}

export async function getSuggestedQuestions(docId) {
  const res = await fetch(`${API_BASE_URL}/api/documents/${docId}/suggested-questions`);
  if (!res.ok) throw new Error('Failed to fetch suggested questions');
  return res.json();
}

export async function getDocumentChat(docId) {
  const res = await fetch(`${API_BASE_URL}/api/documents/${docId}/chat`);
  if (!res.ok) throw new Error('Failed to fetch chat history');
  return res.json();
}

export async function clearDocumentChat(docId) {
  const res = await fetch(`${API_BASE_URL}/api/documents/${docId}/chat`, {
    method: 'DELETE',
  });
  if (!res.ok) throw new Error('Failed to clear chat history');
  return res.json();
}

export async function getDocumentPage(docId, pageNum) {
  const res = await fetch(`${API_BASE_URL}/api/documents/${docId}/pages/${pageNum}`);
  if (!res.ok) throw new Error(`Failed to load page ${pageNum}`);
  return res.json();
}

export function getDocumentFileUrl(docId, pageNum = null) {
  const base = `${API_BASE_URL}/api/documents/${docId}/file`;
  return pageNum ? `${base}#page=${pageNum}` : base;
}
