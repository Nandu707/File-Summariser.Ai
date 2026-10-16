import React, { useState, useEffect } from 'react';
import axios from 'axios';
import { Database, ExternalLink } from 'lucide-react';
import FileUploader from './components/FileUploader';
import ChatWindow from './components/ChatWindow';

export default function App() {
  const [docId, setDocId] = useState(null);
  const [documentInfo, setDocumentInfo] = useState(null);
  const [backendStatus, setBackendStatus] = useState('checking'); // 'healthy' | 'checking' | 'error'
  const [isAnswering, setIsAnswering] = useState(false);

  useEffect(() => {
    const checkApi = async () => {
      try {
        const res = await axios.get('http://localhost:8000/api/health');
        if (res.status === 200) {
          setBackendStatus('healthy');
        }

        // Fetch documents to initialize active document if none selected
        const docsRes = await axios.get('http://localhost:8000/api/documents');
        if (Array.isArray(docsRes.data) && docsRes.data.length > 0) {
          setDocId((currentId) => {
            if (!currentId) {
              const latest = docsRes.data[0];
              setDocumentInfo(latest);
              return latest.doc_id;
            }
            return currentId;
          });
        }
      } catch (err) {
        setBackendStatus('error');
      }
    };

    checkApi();
    const timer = setInterval(checkApi, 8000);
    return () => clearInterval(timer);
  }, []);

  const handleUploadSuccess = (data) => {
    // data: { doc_id: str, filename: str, chunks: int }
    setDocId(data.doc_id);
    setDocumentInfo(data);
  };

  const handleSelectDoc = (doc) => {
    if (isAnswering) return;
    if (doc) {
      setDocId(doc.doc_id);
      setDocumentInfo(doc);
    } else {
      setDocId(null);
      setDocumentInfo(null);
    }
  };

  return (
    <div className="h-screen flex flex-col bg-surface-950 text-slate-100 overflow-hidden">
      {/* Top Navbar */}
      <header className="flex-shrink-0 border-b border-slate-800/80 bg-surface-950/80 backdrop-blur-md sticky top-0 z-30">
        <div className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8">
          <div className="flex items-center justify-between h-16">
            {/* Logo */}
            <div className="flex items-center space-x-3">
              <div className="w-9 h-9 rounded-xl bg-gradient-to-tr from-brand-600 via-indigo-500 to-cyan-400 p-[1px] shadow-lg shadow-brand-500/20">
                <div className="w-full h-full bg-surface-950 rounded-[11px] flex items-center justify-center">
                  <Database className="w-4 h-4 text-brand-400" />
                </div>
              </div>
              <div>
                <div className="flex items-center space-x-2">
                  <span className="font-extrabold text-lg tracking-tight bg-gradient-to-r from-white via-slate-200 to-brand-300 bg-clip-text text-transparent">
                    File Summariser.Ai
                  </span>
                  <span className="text-[10px] font-bold px-2 py-0.5 rounded-full bg-brand-500/10 text-brand-400 border border-brand-500/20">
                    Split-Screen RAG
                  </span>
                </div>
                <p className="text-[11px] text-slate-400">FastAPI • PyMuPDF • ChromaDB • React + Vite</p>
              </div>
            </div>

            {/* Health & Docs */}
            <div className="flex items-center space-x-3">
              <div className={`flex items-center space-x-1.5 px-3 py-1 rounded-full text-xs font-medium border ${
                backendStatus === 'healthy'
                  ? 'bg-emerald-500/10 text-emerald-400 border-emerald-500/30'
                  : backendStatus === 'checking'
                  ? 'bg-amber-500/10 text-amber-400 border-amber-500/30'
                  : 'bg-rose-500/10 text-rose-400 border-rose-500/30'
              }`}>
                <span className={`w-2 h-2 rounded-full ${
                  backendStatus === 'healthy' ? 'bg-emerald-400 animate-pulse' : 'bg-rose-400'
                }`} />
                <span>{backendStatus === 'healthy' ? 'API Online' : 'Connecting...'}</span>
              </div>

              <a
                href="http://localhost:8000/docs"
                target="_blank"
                rel="noreferrer"
                className="hidden sm:flex items-center space-x-1 px-3 py-1 rounded-lg text-xs font-medium text-slate-400 hover:text-white hover:bg-slate-800 transition-colors border border-transparent hover:border-slate-700"
              >
                <span>Docs</span>
                <ExternalLink className="w-3 h-3" />
              </a>
            </div>
          </div>
        </div>
      </header>

      {/* Main Split-Screen Layout */}
      <main className="flex-1 min-h-0 max-w-7xl w-full mx-auto p-4 sm:p-6 lg:p-8 flex flex-col lg:flex-row gap-6 h-[calc(100vh-4rem)]">
        {/* Left Sidebar: FileUploader */}
        <FileUploader
          onUploadSuccess={handleUploadSuccess}
          activeDocId={docId}
          onSelectDoc={handleSelectDoc}
          disabled={isAnswering}
        />

        {/* Right Panel: ChatWindow */}
        <ChatWindow
          docId={docId}
          documentInfo={documentInfo}
          onLoadingChange={setIsAnswering}
        />
      </main>
    </div>
  );
}
