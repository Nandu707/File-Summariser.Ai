import React, { useState, useEffect, useCallback } from 'react';
import axios from 'axios';
import ChatWindow from '../components/ChatWindow';
import DocumentSidebar from '../components/DocumentSidebar';
import DocumentPageModal from '../components/DocumentPageModal';

export default function ChatPage({
  activeDocId = 'all',
  documents = [],
  onSelectDoc,
  onNavigateTab,
  isAnswering,
  setIsAnswering
}) {
  const [sessions, setSessions] = useState([]);
  const [activeSessionId, setActiveSessionId] = useState(() => {
    try {
      return localStorage.getItem('task_rag_active_chat_id') || 'all';
    } catch {
      return 'all';
    }
  });
  const [searchQuery, setSearchQuery] = useState('');
  const [loadingSessions, setLoadingSessions] = useState(false);
  const [modalState, setModalState] = useState({
    isOpen: false,
    page: 1,
    docId: null,
    filename: ''
  });

  // Fetch all chat sessions (ChatGPT-style single list)
  const fetchSessions = useCallback(async (q = '') => {
    try {
      setLoadingSessions(true);
      const url = q ? `http://localhost:8000/api/chats?q=${encodeURIComponent(q)}` : 'http://localhost:8000/api/chats';
      const res = await axios.get(url);
      if (Array.isArray(res.data)) {
        setSessions(res.data);

        // If no active session or active session not found in list, select first available
        setActiveSessionId((currentId) => {
          if (res.data.length === 0) return 'all';
          const exists = res.data.some((s) => s.id === currentId);
          if (!exists) {
            const nextId = res.data[0].id;
            try {
              localStorage.setItem('task_rag_active_chat_id', nextId);
            } catch (e) {}
            return nextId;
          }
          return currentId;
        });
      }
    } catch (err) {
      console.warn('Failed to fetch chat sessions:', err);
    } finally {
      setLoadingSessions(false);
    }
  }, []);

  useEffect(() => {
    fetchSessions(searchQuery);
  }, [fetchSessions, searchQuery]);

  const handleSelectSession = (sessionId) => {
    setActiveSessionId(sessionId);
    try {
      localStorage.setItem('task_rag_active_chat_id', sessionId);
    } catch (e) {}

    // Find session to also update activeDocId for legacy compatibility
    const found = sessions.find((s) => s.id === sessionId);
    if (found && onSelectDoc) {
      onSelectDoc(found.scope === 'file' ? found.file_id : 'all');
    }
  };

  const handleCreateSession = async ({ scope = 'all', file_id = null, file_name = null, title = null }) => {
    try {
      const res = await axios.post('http://localhost:8000/api/chats', {
        scope,
        file_id,
        file_name,
        title
      });
      if (res.data && res.data.id) {
        await fetchSessions(searchQuery);
        handleSelectSession(res.data.id);
      }
    } catch (err) {
      alert('Failed to create new chat: ' + (err.response?.data?.detail || err.message));
    }
  };

  const handleRenameSession = async (sessionId, newTitle) => {
    try {
      await axios.patch(`http://localhost:8000/api/chats/${sessionId}`, { title: newTitle });
      setSessions((prev) =>
        prev.map((s) => (s.id === sessionId ? { ...s, title: newTitle } : s))
      );
    } catch (err) {
      alert('Failed to rename chat: ' + (err.response?.data?.detail || err.message));
    }
  };

  const handleDeleteSession = async (sessionId) => {
    try {
      await axios.delete(`http://localhost:8000/api/chats/${sessionId}`);
      const remaining = sessions.filter((s) => s.id !== sessionId);
      setSessions(remaining);
      if (activeSessionId === sessionId) {
        const nextId = remaining.length > 0 ? remaining[0].id : 'all';
        handleSelectSession(nextId);
      }
      await fetchSessions(searchQuery);
    } catch (err) {
      alert('Failed to delete chat: ' + (err.response?.data?.detail || err.message));
    }
  };

  const handleOpenPageModal = (pageDocId, pageNum, filename) => {
    let targetDocId = pageDocId;
    if (!targetDocId || targetDocId === 'all') {
      if (filename && Array.isArray(documents) && documents.length > 0) {
        const found = documents.find((d) => d.filename === filename);
        if (found) targetDocId = found.doc_id;
      }
      if (!targetDocId && Array.isArray(documents) && documents.length > 0) {
        targetDocId = documents[0].doc_id;
      }
    }

    if (targetDocId) {
      const page = pageNum || 1;
      const pdfUrl = `http://localhost:8000/api/documents/${targetDocId}/file#page=${page}`;
      window.open(pdfUrl, '_blank', 'noopener,noreferrer');
    }
  };

  const handleClosePageModal = () => {
    setModalState((prev) => ({ ...prev, isOpen: false }));
  };

  const activeSession = sessions.find((s) => s.id === activeSessionId) || {
    id: activeSessionId,
    title: activeSessionId === 'all' ? 'All files' : 'Chat',
    scope: activeSessionId === 'all' ? 'all' : 'file',
    file_id: activeSessionId === 'all' ? null : activeSessionId,
    file_name: activeSessionId === 'all' ? 'All files' : 'Document',
    is_file_deleted: false
  };

  return (
    <div className="flex-1 min-h-0 flex flex-col lg:flex-row h-full max-w-7xl w-full mx-auto p-3 sm:p-5 lg:p-6 gap-4 sm:gap-6 overflow-hidden">
      {/* ChatGPT-Style History Sidebar */}
      <DocumentSidebar
        sessions={sessions}
        activeSessionId={activeSessionId}
        documents={documents}
        onSelectSession={handleSelectSession}
        onCreateSession={handleCreateSession}
        onRenameSession={handleRenameSession}
        onDeleteSession={handleDeleteSession}
        onOpenUpload={() => onNavigateTab && onNavigateTab('documents')}
        searchQuery={searchQuery}
        onSearchChange={setSearchQuery}
        loading={loadingSessions}
      />

      {/* Main Chat Window */}
      <ChatWindow
        activeSessionId={activeSessionId}
        activeSession={activeSession}
        documents={documents}
        sessions={sessions}
        onSelectSession={handleSelectSession}
        onCreateSession={handleCreateSession}
        onRenameSession={handleRenameSession}
        onDeleteSession={handleDeleteSession}
        onNavigateTab={onNavigateTab}
        onLoadingChange={setIsAnswering}
        onViewPage={handleOpenPageModal}
        onSessionActivity={() => fetchSessions(searchQuery)}
      />

      {/* Document Page Modal for viewing cited source pages & documents */}
      <DocumentPageModal
        isOpen={modalState.isOpen}
        onClose={handleClosePageModal}
        docId={modalState.docId}
        initialPage={modalState.page}
        filename={modalState.filename}
      />
    </div>
  );
}
