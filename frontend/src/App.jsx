import React, { useState, useEffect, useCallback } from 'react';
import axios from 'axios';
import Navbar from './components/Navbar';
import { ChatPage, DocumentsPage } from './pages';
import LoginPage from './pages/LoginPage';
import SignupPage from './pages/SignupPage';
import { AuthProvider, useAuth } from './context/AuthContext';
import { API_BASE_URL } from './api';

function MainApp() {
  const { user, loading, isAuthenticated } = useAuth();
  const [authMode, setAuthMode] = useState('login'); // 'login' | 'signup'
  const [activeTab, setActiveTab] = useState('chat'); // 'chat' | 'documents'
  const [documents, setDocuments] = useState([]);
  const [activeDocId, setActiveDocId] = useState(() => {
    try {
      return localStorage.getItem('task_rag_active_doc_id') || 'all';
    } catch {
      return 'all';
    }
  });
  const [backendStatus, setBackendStatus] = useState('checking'); // 'healthy' | 'checking' | 'error'
  const [isAnswering, setIsAnswering] = useState(false);

  // Clear or reset state when user changes
  useEffect(() => {
    if (!isAuthenticated) {
      setDocuments([]);
      setActiveDocId('all');
    }
  }, [isAuthenticated]);

  // Fetch documents from backend API for current authenticated user
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
    } catch (err) {
      if (err.response?.status !== 401) {
        setBackendStatus('error');
      }
    }
  }, [isAuthenticated]);

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

  const handleDocumentCountChange = (count) => {
    fetchDocuments();
  };

  // Loading Screen while verifying session
  if (loading) {
    return (
      <div className="h-screen w-screen flex flex-col items-center justify-center bg-gradient-to-br from-indigo-50/70 via-slate-50 to-violet-50/60 text-slate-700 font-sans">
        <div className="w-12 h-12 rounded-2xl bg-gradient-to-tr from-indigo-600 to-violet-600 flex items-center justify-center mb-4 shadow-lg shadow-indigo-500/20 animate-bounce">
          <svg className="w-6 h-6 text-white" fill="none" viewBox="0 0 24 24" stroke="currentColor">
            <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M12 15v2m-6 4h12a2 2 0 002-2v-6a2 2 0 00-2-2H6a2 2 0 00-2 2v6a2 2 0 002 2zm10-10V7a4 4 0 00-8 0v4h8z" />
          </svg>
        </div>
        <p className="text-sm font-medium text-slate-500">Verifying session...</p>
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

  // Authenticated Main Workspace
  return (
    <div className="h-screen flex flex-col bg-white text-slate-800 overflow-hidden font-sans">
      {/* Top Navbar with user profile & logout */}
      <Navbar
        activeTab={activeTab}
        onSelectTab={setActiveTab}
        backendStatus={backendStatus}
        docCount={documents.length}
      />

      {/* Main Content Area */}
      <main className="flex-1 min-h-0 flex flex-col overflow-hidden bg-gradient-to-b from-white via-slate-50/50 to-slate-100/30">
        {activeTab === 'chat' && (
          <ChatPage
            key={user?.id || 'chat'}
            activeDocId={activeDocId}
            documents={documents}
            onSelectDoc={handleSelectDoc}
            onNavigateTab={setActiveTab}
            isAnswering={isAnswering}
            setIsAnswering={setIsAnswering}
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
      </main>
    </div>
  );
}

export default function App() {
  return (
    <AuthProvider>
      <MainApp />
    </AuthProvider>
  );
}
