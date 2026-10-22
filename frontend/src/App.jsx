import React, { useState, useEffect, useCallback } from 'react';
import axios from 'axios';
import Sidebar from './components/Sidebar';
import { ChatPage, DocumentsPage, UsersPage } from './pages';
import LoginPage from './pages/LoginPage';
import SignupPage from './pages/SignupPage';
import { AuthProvider, useAuth } from './context/AuthContext';
import { ThemeProvider } from './context/ThemeContext';
import { API_BASE_URL } from './api';

function MainApp() {
  const { user, loading, isAuthenticated } = useAuth();
  const [authMode, setAuthMode] = useState('login'); // 'login' | 'signup'
  const [activeTab, setActiveTab] = useState('chat'); // 'chat' | 'documents' | 'users'
  const [documents, setDocuments] = useState([]);
  const [pendingCount, setPendingCount] = useState(0);
  const [activeDocId, setActiveDocId] = useState(() => {
    try {
      return localStorage.getItem('task_rag_active_doc_id') || 'all';
    } catch {
      return 'all';
    }
  });
  const [backendStatus, setBackendStatus] = useState('checking'); // 'healthy' | 'checking' | 'error'
  const [isAnswering, setIsAnswering] = useState(false);

  // Sidebar Collapsed State
  const [isSidebarCollapsed, setIsSidebarCollapsed] = useState(() => {
    try {
      return localStorage.getItem('task_rag_sidebar_collapsed') === 'true';
    } catch {
      return false;
    }
  });

  const toggleSidebar = () => {
    setIsSidebarCollapsed((prev) => {
      const next = !prev;
      try {
        localStorage.setItem('task_rag_sidebar_collapsed', String(next));
      } catch (e) {}
      return next;
    });
  };

  // Chat Sessions State (hoisted to App level so Sidebar has global access)
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

  // Fetch all chat sessions
  const fetchSessions = useCallback(async (q = '') => {
    if (!isAuthenticated) return;
    try {
      setLoadingSessions(true);
      const url = q ? `${API_BASE_URL}/api/chats?q=${encodeURIComponent(q)}` : `${API_BASE_URL}/api/chats`;
      const res = await axios.get(url);
      if (Array.isArray(res.data)) {
        setSessions(res.data);

        // Keep active session if it exists, or 'new'
        setActiveSessionId((currentId) => {
          if (currentId === 'new') return 'new';
          if (draftSession && draftSession.id === currentId) return currentId;
          if (res.data.length === 0) return 'new';
          const exists = res.data.some((s) => s.id === currentId);
          if (!exists) return 'new';
          return currentId;
        });
      }
    } catch (err) {
      console.warn('Failed to fetch chat sessions:', err);
    } finally {
      setLoadingSessions(false);
    }
  }, [isAuthenticated, draftSession]);

  useEffect(() => {
    if (isAuthenticated) {
      fetchSessions(searchQuery);
    }
  }, [isAuthenticated, fetchSessions, searchQuery]);

  const handleSelectSession = (sessionId) => {
    setActiveSessionId(sessionId);
    try {
      localStorage.setItem('task_rag_active_chat_id', sessionId);
    } catch (e) {}

    if (draftSession && draftSession.id !== sessionId) {
      setDraftSession(null);
    }

    const found = sessions.find((s) => s.id === sessionId) || (draftSession?.id === sessionId ? draftSession : null);
    if (found) {
      handleSelectDoc(found.scope === 'file' ? found.file_id : 'all');
    }
  };

  const handleCreateSession = async ({ scope = 'all', file_id = null, file_name = null, title = null }) => {
    try {
      const res = await axios.post(`${API_BASE_URL}/api/chats`, {
        scope,
        file_id,
        file_name,
        title,
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
      if (sessionId && sessionId !== 'all' && sessionId !== 'new') {
        await axios.patch(`${API_BASE_URL}/api/chats/${sessionId}`, {
          title,
          scope,
          file_id,
          file_name,
        });
        setSessions((prev) =>
          prev.map((s) =>
            s.id === sessionId
              ? {
                  ...s,
                  title: title || s.title,
                  scope,
                  file_id: scope === 'all' ? null : file_id,
                  file_name: scope === 'all' ? 'All files' : file_name,
                }
              : s
          )
        );
        handleSelectDoc(scope === 'file' ? file_id : 'all');
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
        const nextId = remaining.length > 0 ? remaining[0].id : 'new';
        handleSelectSession(nextId);
      }
      await fetchSessions(searchQuery);
    } catch (err) {
      alert('Failed to delete chat: ' + (err.response?.data?.detail || err.message));
    }
  };

  // Clear or reset state when user changes
  useEffect(() => {
    if (!isAuthenticated) {
      setDocuments([]);
      setActiveDocId('all');
      setSessions([]);
    }
  }, [isAuthenticated]);

  // Fetch documents and user stats from backend API
  const fetchDocuments = useCallback(async () => {
    if (!isAuthenticated) return;
    try {
      const res = await axios.get(`${API_BASE_URL}/api/health`);
      if (res.status === 200) {
        setBackendStatus('healthy');
      }

      const docsRes = await axios.get(`${API_BASE_URL}/api/documents`);
      if (Array.isArray(docsRes.data)) {
        setDocuments(docsRes.data);
      }

      // If current user is admin, fetch pending user count
      if (user?.role === 'admin') {
        try {
          const usersRes = await axios.get(`${API_BASE_URL}/api/auth/admin/users`);
          if (Array.isArray(usersRes.data)) {
            const pending = usersRes.data.filter((u) => u.status === 'pending').length;
            setPendingCount(pending);
          }
        } catch (e) {
          console.debug('Failed to fetch admin users count:', e);
        }
      }
    } catch (err) {
      if (err.response?.status !== 401) {
        setBackendStatus('error');
      }
    }
  }, [isAuthenticated, user?.role]);

  useEffect(() => {
    if (isAuthenticated) {
      fetchDocuments();
      const timer = setInterval(fetchDocuments, 8000);
      return () => clearInterval(timer);
    }
  }, [isAuthenticated, fetchDocuments]);

  const handleSelectDoc = (docOrId) => {
    if (isAnswering) return;
    let targetId = 'all';
    if (typeof docOrId === 'string') {
      targetId = docOrId;
    } else if (docOrId && docOrId.doc_id) {
      targetId = docOrId.doc_id;
    }
    setActiveDocId(targetId);
    try {
      localStorage.setItem('task_rag_active_doc_id', targetId);
    } catch (e) {}
  };

  const handleDocumentCountChange = () => {
    fetchDocuments();
  };

  // Loading Screen while verifying session
  if (loading) {
    return (
      <div className="h-screen w-screen flex flex-col items-center justify-center bg-[#171717] text-neutral-300 font-sans">
        <div className="w-12 h-12 rounded-2xl bg-gradient-to-tr from-indigo-600 via-blue-600 to-sky-500 flex items-center justify-center mb-4 shadow-xl shadow-indigo-500/20 animate-bounce">
          <svg className="w-6 h-6 text-white" fill="none" viewBox="0 0 24 24" stroke="currentColor">
            <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M12 15v2m-6 4h12a2 2 0 002-2v-6a2 2 0 00-2-2H6a2 2 0 00-2 2v6a2 2 0 002 2zm10-10V7a4 4 0 00-8 0v4h8z" />
          </svg>
        </div>
        <p className="text-sm font-medium text-neutral-400">Verifying session...</p>
      </div>
    );
  }

  // Unauthenticated Views
  if (!isAuthenticated) {
    if (authMode === 'signup') {
      return <SignupPage onNavigateToLogin={() => setAuthMode('login')} />;
    }
    return <LoginPage onNavigateToSignup={() => setAuthMode('signup')} />;
  }

  // Authenticated Main Workspace: ChatGPT-style full-height layout with Collapsible Sidebar
  return (
    <div className="h-screen w-screen flex bg-white dark:bg-[#171717] text-slate-800 dark:text-neutral-200 overflow-hidden font-sans transition-colors duration-200">
      {/* Left Collapsible Area (ChatGPT Style - containing all header options) */}
      <Sidebar
        isCollapsed={isSidebarCollapsed}
        onToggleCollapse={toggleSidebar}
        activeTab={activeTab}
        onSelectTab={setActiveTab}
        docCount={documents.length}
        pendingCount={pendingCount}
        backendStatus={backendStatus}
        sessions={sessions}
        activeSessionId={activeSessionId}
        documents={documents}
        onSelectSession={handleSelectSession}
        onCreateSession={handleCreateSession}
        onRenameSession={handleRenameSession}
        onDeleteSession={handleDeleteSession}
        searchQuery={searchQuery}
        onSearchChange={setSearchQuery}
        loading={loadingSessions}
      />

      {/* Main Content Area - Expands to 100% remaining width and height (no top navbar) */}
      <main className="flex-1 min-w-0 h-full flex flex-col overflow-hidden bg-gradient-to-b from-white via-slate-50/50 to-slate-100/30 dark:from-[#212121] dark:via-[#1a1a1a] dark:to-[#171717] transition-colors duration-200">
        <div key={activeTab} className="flex-1 min-h-0 w-full h-full flex flex-col overflow-hidden page-enter-animation">
          {activeTab === 'chat' && (
            <ChatPage
              key={user?.id || 'chat'}
              activeSessionId={activeSessionId}
              sessions={sessions}
              draftSession={draftSession}
              onSelectSession={handleSelectSession}
              onCreateSession={handleCreateSession}
              onRenameSession={handleRenameSession}
              onDeleteSession={handleDeleteSession}
              onUpdateSessionScope={handleUpdateSessionScope}
              onSessionActivity={() => fetchSessions(searchQuery)}
              activeDocId={activeDocId}
              documents={documents}
              onSelectDoc={handleSelectDoc}
              onNavigateTab={setActiveTab}
              isAnswering={isAnswering}
              setIsAnswering={setIsAnswering}
              isSidebarCollapsed={isSidebarCollapsed}
              onToggleSidebar={toggleSidebar}
            />
          )}

          {activeTab === 'documents' && (
            <DocumentsPage
              key={user?.id || 'docs'}
              onSelectDoc={handleSelectDoc}
              onNavigateTab={setActiveTab}
              onDocumentCountChange={handleDocumentCountChange}
            />
          )}

          {activeTab === 'users' && user?.role === 'admin' && (
            <UsersPage
              key="users-admin"
              onPendingCountChange={setPendingCount}
            />
          )}
        </div>
      </main>
    </div>
  );
}

export default function App() {
  return (
    <ThemeProvider>
      <AuthProvider>
        <MainApp />
      </AuthProvider>
    </ThemeProvider>
  );
}
