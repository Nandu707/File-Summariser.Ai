import React from 'react';
import { Database, FileText, Cpu, ExternalLink, Sparkles, CheckCircle2, AlertCircle } from 'lucide-react';

export default function Navbar({ backendStatus, docCount, onOpenUpload }) {
  return (
    <header className="sticky top-0 z-40 border-b border-slate-800/80 bg-surface-950/80 backdrop-blur-md">
      <div className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8">
        <div className="flex items-center justify-between h-16">
          {/* Logo & Title */}
          <div className="flex items-center space-x-3">
            <div className="w-10 h-10 rounded-xl bg-gradient-to-tr from-brand-600 via-indigo-500 to-cyan-400 p-[1px] shadow-lg shadow-brand-500/20">
              <div className="w-full h-full bg-surface-950 rounded-[11px] flex items-center justify-center">
                <Database className="w-5 h-5 text-brand-400" />
              </div>
            </div>
            <div>
              <div className="flex items-center space-x-2">
                <span className="font-extrabold text-xl tracking-tight bg-gradient-to-r from-white via-slate-200 to-brand-300 bg-clip-text text-transparent">
                  Task-RAG
                </span>
                <span className="text-[10px] uppercase font-bold tracking-wider px-2 py-0.5 rounded-full bg-brand-500/10 text-brand-400 border border-brand-500/20">
                  Vector Engine
                </span>
              </div>
              <p className="text-xs text-slate-400 hidden sm:block">
                PyMuPDF <span className="text-slate-600">•</span> ChromaDB <span className="text-slate-600">•</span> FastAPI
              </p>
            </div>
          </div>

          {/* System Indicators */}
          <div className="flex items-center space-x-3">
            {/* Backend Health Badge */}
            <div 
              className={`flex items-center space-x-1.5 px-2.5 py-1 rounded-full text-xs font-medium border transition-colors ${
                backendStatus === 'healthy'
                  ? 'bg-emerald-500/10 text-emerald-400 border-emerald-500/30'
                  : backendStatus === 'checking'
                  ? 'bg-amber-500/10 text-amber-400 border-amber-500/30'
                  : 'bg-rose-500/10 text-rose-400 border-rose-500/30'
              }`}
              title={backendStatus === 'healthy' ? 'FastAPI Backend Connected' : 'Checking Backend'}
            >
              <span className={`w-2 h-2 rounded-full ${
                backendStatus === 'healthy' ? 'bg-emerald-400 animate-pulse' : 'bg-rose-400'
              }`} />
              <span className="hidden md:inline">
                {backendStatus === 'healthy' ? 'API Online' : backendStatus === 'checking' ? 'Connecting...' : 'API Offline'}
              </span>
            </div>

            {/* ChromaDB Document Count */}
            <div className="hidden sm:flex items-center space-x-1.5 px-3 py-1 rounded-lg bg-slate-900 border border-slate-800 text-xs text-slate-300">
              <FileText className="w-3.5 h-3.5 text-brand-400" />
              <span>{docCount} {docCount === 1 ? 'Doc' : 'Docs'} Indexed</span>
            </div>

            {/* FastAPI Docs Link */}
            <a
              href="http://localhost:8000/docs"
              target="_blank"
              rel="noreferrer"
              className="hidden lg:flex items-center space-x-1 px-3 py-1.5 rounded-lg text-xs font-medium text-slate-400 hover:text-white hover:bg-slate-800/80 transition-all border border-transparent hover:border-slate-700"
              title="Open Swagger API documentation"
            >
              <span>Swagger Docs</span>
              <ExternalLink className="w-3 h-3" />
            </a>

            {/* Upload Button */}
            <button
              onClick={onOpenUpload}
              className="flex items-center space-x-2 px-3.5 py-1.5 rounded-lg text-xs font-semibold text-white bg-gradient-to-r from-brand-600 to-indigo-600 hover:from-brand-500 hover:to-indigo-500 shadow-md shadow-brand-600/20 hover:shadow-brand-500/30 transition-all active:scale-95"
            >
              <Sparkles className="w-3.5 h-3.5" />
              <span>Upload Document</span>
            </button>
          </div>
        </div>
      </div>
    </header>
  );
}
