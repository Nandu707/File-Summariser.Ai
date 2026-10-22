import React, { useState, useEffect, useCallback, useRef } from 'react';
import axios from 'axios';
import { History, Plus, PanelLeftOpen } from 'lucide-react';
import ChatWindow from '../components/ChatWindow';
import DocumentSidebar from '../components/DocumentSidebar';
import DocumentPageModal from '../components/DocumentPageModal';
import { API_BASE_URL } from '../api';

export default function ChatPage({
  activeDocId = 'all',
  documents = [],
  onSelectDoc,
  onNavigateTab,
  isAnswering,
  setIsAnswering
}) {
  const [sessions, setSessions] = useState([]);
  const [draftSession, setDraftSession] = useState(null);
  const [activeSessionId, setActiveSessionId] = useState(() => {
    try {
      const justLoggedIn = localStorage.getItem('task_rag_just_logged_in');
      if (justLoggedIn) {
        localStorage.removeItem('task_rag_just_logged_in');
        return 'new';
      }
      return localStorage.getItem('task_rag_active_chat_id') || 'new';
    } catch {
      return 'new';
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

  // Collapsible Sidebar State
  const [isSidebarCollapsed, setIsSidebarCollapsed] = useState(() => {
    try {
      return localStorage.getItem('task_rag_sidebar_collapsed') === 'true';
    } catch {
      return false;
    }
  });

  // Resizable Sidebar Width State (in px, bounded between 220px and 500px)
  const [sidebarWidth, setSidebarWidth] = useState(() => {
    try {
      const saved = parseInt(localStorage.getItem('task_rag_sidebar_width'), 10);
      return !isNaN(saved) && saved >= 220 && saved <= 500 ? saved : 280;
    } catch {
      return 280;
    }
  });

  const [isResizing, setIsResizing] = useState(false);
  const containerRef = useRef(null);

  const toggleSidebar = () => {
    setIsSidebarCollapsed((prev) => {
      const next = !prev;
      try {
        localStorage.setItem('task_rag_sidebar_collapsed', String(next));
      } catch (e) {}
      return next;
    });
  };

  // Start resize dragging on mousedown
  const handleStartResize = (e) => {
    e.preventDefault();
    setIsResizing(true);
  };

  useEffect(() => {
    if (!isResizing) return;

    const handleMouseMove = (e) => {
      if (!containerRef.current) return;
      const rect = containerRef.current.getBoundingClientRect();
      const newWidth = Math.round(e.clientX - rect.left);
      const clampedWidth = Math.max(220, Math.min(500, newWidth));
      setSidebarWidth(clampedWidth);
    };

    const handleMouseUp = () => {
      setIsResizing(false);
      setSidebarWidth((w) => {
        try {
          localStorage.setItem('task_rag_sidebar_width', String(w));
        } catch (e) {}
        return w;
      });
    };

    document.body.style.cursor = 'col-resize';
    document.body.style.userSelect = 'none';

    window.addEventListener('mousemove', handleMouseMove);
    window.addEventListener('mouseup', handleMouseUp);

    return () => {
      document.body.style.cursor = '';
      document.body.style.userSelect = '';
      window.removeEventListener('mousemove', handleMouseMove);
      window.removeEventListener('mouseup', handleMouseUp);
    };
  }, [isResizing]);

  // Fetch all chat sessions
  const fetchSessions = useCallback(async (q = '') => {
    try {
      setLoadingSessions(true);
      const url = q ? `${API_BASE_URL}/api/chats?q=${encodeURIComponent(q)}` : `${API_BASE_URL}/api/chats`;
      const res = await axios.get(url);
      if (Array.isArray(res.data)) {
        setSessions(res.data);

        // If user is on a new chat or draft, stay on new chat
        setActiveSessionId((currentId) => {
          if (currentId === 'new') return 'new';
          if (draftSession && draftSession.id === currentId) return currentId;
          if (res.data.length === 0) return 'new';
          const exists = res.data.some((s) => s.id === currentId);
          if (!exists) {
            return 'new';
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

    if (draftSession && draftSession.id !== sessionId) {
      setDraftSession(null);
    }

    // Find session to also update activeDocId for legacy compatibility
    const found = sessions.find((s) => s.id === sessionId) || (draftSession?.id === sessionId ? draftSession : null);
    if (found && onSelectDoc) {
      onSelectDoc(found.scope === 'file' ? found.file_id : 'all');
    }
  };

  const handleCreateSession = async ({ scope = 'all', file_id = null, file_name = null, title = null }) => {
    try {
      const res = await axios.post(`${API_BASE_URL}/api/chats`, {
        scope,
        file_id,
        file_name,
        title
      });
      if (res.data && res.data.id) {
        setDraftSession(res.data);
        await fetchSessions(searchQuery);
        handleSelectSession(res.data.id);
      }
    } catch (err) {
      alert('Failed to create new chat: ' + (err.response?.data?.detail || err.message));
    }
  };

  const handleRenameSession = async (sessionId, newTitle) => {
    try {
      await axios.patch(`${API_BASE_URL}/api/chats/${sessionId}`, { title: newTitle });
      setSessions((prev) =>
        prev.map((s) => (s.id === sessionId ? { ...s, title: newTitle } : s))
      );
    } catch (err) {
      alert('Failed to rename chat: ' + (err.response?.data?.detail || err.message));
    }
  };

  const handleUpdateSessionScope = async (sessionId, { scope, file_id, file_name, title }) => {
    try {
      if (sessionId && sessionId !== 'all') {
        await axios.patch(`${API_BASE_URL}/api/chats/${sessionId}`, {
          title,
          scope,
          file_id,
          file_name
        });
        setSessions((prev) =>
          prev.map((s) =>
            s.id === sessionId
              ? {
                  ...s,
                  title: title || s.title,
                  scope,
                  file_id: scope === 'all' ? null : file_id,
                  file_name: scope === 'all' ? 'All files' : file_name
                }
              : s
          )
        );
        if (onSelectDoc) {
          onSelectDoc(scope === 'file' ? file_id : 'all');
        }
        await fetchSessions(searchQuery);
      } else {
        await handleCreateSession({ scope, file_id, file_name, title });
      }
    } catch (err) {
      console.warn('Failed to update chat scope, falling back to create session:', err);
      await handleCreateSession({ scope, file_id, file_name, title });
    }
  };

  const handleDeleteSession = async (sessionId) => {
    try {
      await axios.delete(`${API_BASE_URL}/api/chats/${sessionId}`);
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
    let targetFilename = filename;
    if (!targetDocId || targetDocId === 'all') {
      if (filename && Array.isArray(documents) && documents.length > 0) {
        const found = documents.find((d) => d.filename === filename);
        if (found) {
          targetDocId = found.doc_id;
          targetFilename = found.filename;
        }
      }
      if (!targetDocId && Array.isArray(documents) && documents.length > 0) {
        targetDocId = documents[0].doc_id;
        targetFilename = documents[0].filename;
      }
    }

    if (targetDocId) {
      const page = pageNum || 1;
      setModalState({
        isOpen: true,
        docId: targetDocId,
        page: page,
        filename: targetFilename || 'Document'
      });
    }
  };

  const handleClosePageModal = () => {
    setModalState((prev) => ({ ...prev, isOpen: false }));
  };

  const activeSession =
    (activeSessionId !== 'new' && sessions.find((s) => s.id === activeSessionId)) ||
    (draftSession && draftSession.id === activeSessionId ? draftSession : null) || {
      id: 'new',
      title: 'New chat',
      scope: 'all',
      file_id: null,
      file_name: 'All files',
      is_file_deleted: false,
      message_count: 0
    };

  const startedSessionsCount = sessions.filter((s) => (s.message_count || 0) > 0).length;

  return (
    <div
      ref={containerRef}
      className={`flex-1 min-h-0 flex flex-col lg:flex-row h-full w-full p-2 sm:p-3 gap-0 overflow-hidden ${
        isResizing ? 'select-none' : ''
      }`}
    >
      {/* Separate Left Margin Rail for Chat History Logo when collapsed */}
      {isSidebarCollapsed && (
        <aside
          aria-label="Chat history navigation margin"
          className="flex lg:flex-col items-center justify-between lg:justify-start py-2 px-3 lg:py-3.5 lg:px-1.5 bg-white rounded-2xl border border-slate-200/90 shadow-2xs flex-shrink-0 w-full lg:w-12 sm:lg:w-14 mb-2 lg:mb-0 mr-0 lg:mr-2 select-none animate-in fade-in slide-in-from-left-2 duration-300 z-10"
        >
          {/* Chat History Drawer Button with Collapse Logo */}
          <button
            type="button"
            onClick={toggleSidebar}
            className="w-9 h-9 sm:w-10 sm:h-10 rounded-xl bg-indigo-50/80 hover:bg-indigo-100 text-indigo-600 border border-indigo-200/80 transition-all duration-200 flex items-center justify-center cursor-pointer shadow-2xs hover:shadow-sm active:scale-95 group relative"
            title="Open chat history"
            aria-label="Open chat history"
          >
            <PanelLeftOpen className="w-4 h-4 sm:w-5 sm:h-5 text-indigo-600 group-hover:scale-110 transition-transform duration-200" />
            <div className="hidden lg:flex absolute left-full ml-3 px-2.5 py-1.5 bg-slate-900/95 backdrop-blur-sm text-white text-xs font-medium rounded-lg shadow-xl opacity-0 group-hover:opacity-100 pointer-events-none transition-all duration-200 whitespace-nowrap z-50 items-center space-x-1.5">
              <span>Chat History</span>
              <span className="text-[10px] text-slate-400 font-normal">({startedSessionsCount})</span>
            </div>
          </button>

          <div className="hidden lg:block w-5 h-[1px] bg-slate-200 my-2.5" />

          <button
            type="button"
            onClick={() => handleCreateSession({ scope: 'all', title: 'New chat' })}
            className="w-9 h-9 sm:w-10 sm:h-10 rounded-xl bg-slate-50 hover:bg-slate-100 text-slate-600 hover:text-slate-900 border border-slate-200/80 transition-all duration-200 flex items-center justify-center cursor-pointer active:scale-95 group relative"
            title="Start new chat"
            aria-label="Start new chat"
          >
            <Plus className="w-4 h-4 text-slate-600 group-hover:rotate-90 transition-transform duration-300" />
            <div className="hidden lg:block absolute left-full ml-3 px-2.5 py-1.5 bg-slate-900/95 backdrop-blur-sm text-white text-xs font-medium rounded-lg shadow-xl opacity-0 group-hover:opacity-100 pointer-events-none transition-all duration-200 whitespace-nowrap z-50">
              <span>New Chat</span>
            </div>
          </button>
        </aside>
      )}

      {/* Collapsible & Resizable Chat History Sidebar with smooth spring drawer animation */}
      <div
        style={{
          width: isSidebarCollapsed ? 0 : `${sidebarWidth}px`,
        }}
        className={`h-full flex-shrink-0 flex flex-col overflow-hidden will-change-[width] ${
          isResizing ? 'transition-none' : 'transition-all duration-300 ease-[cubic-bezier(0.25,1,0.5,1)]'
        } ${isSidebarCollapsed ? 'pointer-events-none' : ''}`}
      >
        <div
          style={{
            width: `${sidebarWidth}px`,
          }}
          className={`h-full flex flex-col transition-all duration-300 ease-[cubic-bezier(0.25,1,0.5,1)] ${
            isSidebarCollapsed ? '-translate-x-6 opacity-0 pointer-events-none' : 'translate-x-0 opacity-100'
          } ${isResizing ? 'transition-none' : ''}`}
        >
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
            onToggleCollapse={toggleSidebar}
          />
        </div>
      </div>

      {/* Resize Drag Divider with smooth fade and width transition */}
      <div
        onMouseDown={!isSidebarCollapsed ? handleStartResize : undefined}
        className={`hidden lg:flex cursor-col-resize z-20 items-center justify-center group flex-shrink-0 transition-all duration-300 ease-[cubic-bezier(0.25,1,0.5,1)] select-none ${
          isSidebarCollapsed
            ? 'w-0 opacity-0 pointer-events-none -mx-0'
            : 'w-2.5 hover:w-3 opacity-100 mx-0.5 hover:bg-indigo-100/60 active:bg-indigo-200 rounded-full'
        }`}
        title="Drag to resize chat history"
      >
        <div className={`w-1 h-8 bg-slate-300 group-hover:bg-indigo-500 rounded-full transition-colors ${
          isSidebarCollapsed ? 'opacity-0' : 'opacity-100'
        }`} />
      </div>

      {/* Main Chat Window (expands to full remaining screen area) */}
      <div className="flex-1 min-w-0 h-full overflow-hidden flex flex-col">
        <ChatWindow
          activeSessionId={activeSessionId}
          activeSession={activeSession}
          documents={documents}
          sessions={sessions}
          onSelectSession={handleSelectSession}
          onCreateSession={handleCreateSession}
          onUpdateSessionScope={handleUpdateSessionScope}
          onRenameSession={handleRenameSession}
          onDeleteSession={handleDeleteSession}
          onNavigateTab={onNavigateTab}
          onLoadingChange={setIsAnswering}
          onViewPage={handleOpenPageModal}
          onSessionActivity={() => fetchSessions(searchQuery)}
          isSidebarCollapsed={isSidebarCollapsed}
          onToggleSidebar={toggleSidebar}
        />
      </div>

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
