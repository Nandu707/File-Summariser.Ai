import React, { useState, useEffect, useCallback } from 'react';
import axios from 'axios';
import Navbar from './components/Navbar';
import { ChatPage, DocumentsPage } from './pages';

export default function App() {
  const [activeTab, setActiveTab] = useState('chat'); // 'chat' | 'documents'
  const [documents, setDocuments] = useState([]);
  const [activeDocId, setActiveDocId] = useState('all'); // 'all' or specific doc_id
  const [backendStatus, setBackendStatus] = useState('checking'); // 'healthy' | 'checking' | 'error'
  const [isAnswering, setIsAnswering] = useState(false);

  // Fetch documents from backend API to keep count and list fresh
  const fetchDocuments = useCallback(async () => {
    try {
      const res = await axios.get('http://localhost:8000/api/health');
      if (res.status === 200) {
        setBackendStatus('healthy');
      }

      const docsRes = await axios.get('http://localhost:8000/api/documents');
      if (Array.isArray(docsRes.data)) {
        setDocuments(docsRes.data);
      }
    } catch (err) {
      setBackendStatus('error');
    }
  }, []);

  useEffect(() => {
    fetchDocuments();
    const timer = setInterval(fetchDocuments, 8000);
    return () => clearInterval(timer);
  }, [fetchDocuments]);

  const handleSelectDoc = (docOrId) => {
    if (isAnswering) return;
    if (typeof docOrId === 'string') {
      setActiveDocId(docOrId);
    } else if (docOrId && docOrId.doc_id) {
      setActiveDocId(docOrId.doc_id);
    } else {
      setActiveDocId('all');
    }
  };

  const handleDocumentCountChange = (count) => {
    fetchDocuments();
  };

  return (
    <div className="h-screen flex flex-col bg-white text-slate-800 overflow-hidden font-sans">
      {/* Top Navbar with 2 clean tabs: Chat & Q&A, Documents & Upload */}
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
            onSelectDoc={handleSelectDoc}
            onNavigateTab={setActiveTab}
            onDocumentCountChange={handleDocumentCountChange}
          />
        )}
      </main>
    </div>
  );
}
