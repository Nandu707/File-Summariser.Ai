import React, { useState, useEffect, useCallback } from 'react';
import axios from 'axios';
import {
  X,
  FileText,
  ChevronLeft,
  ChevronRight,
  ExternalLink,
  Copy,
  Check,
  Loader2,
  FileCode,
  BookOpen,
  Maximize2
} from 'lucide-react';

export default function DocumentPageModal({
  isOpen,
  onClose,
  docId,
  initialPage = 1,
  filename = 'Document'
}) {
  const [currentPage, setCurrentPage] = useState(initialPage);
  const [pageData, setPageData] = useState(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState(null);
  const [copied, setCopied] = useState(false);
  const [activeTab, setActiveTab] = useState('preview'); // 'preview' | 'text'

  // Update currentPage whenever modal opens or initialPage changes
  useEffect(() => {
    if (isOpen) {
      setCurrentPage(initialPage || 1);
    }
  }, [isOpen, initialPage]);

  // Fetch page data from backend
  const fetchPage = useCallback(async (pageToLoad) => {
    if (!docId) return;
    setLoading(true);
    setError(null);
    try {
      const res = await axios.get(`http://localhost:8000/api/documents/${docId}/pages/${pageToLoad}`);
      setPageData(res.data);
      if (res.data.file_type !== 'pdf') {
        setActiveTab('text');
      }
    } catch (err) {
      console.error('Failed to load document page:', err);
      setError(err.response?.data?.detail || 'Failed to load page details');
    } finally {
      setLoading(false);
    }
  }, [docId]);

  useEffect(() => {
    if (isOpen && docId && currentPage) {
      fetchPage(currentPage);
    }
  }, [isOpen, docId, currentPage, fetchPage]);

  // Handle keyboard navigation (Left/Right to change pages, Esc to close)
  useEffect(() => {
    if (!isOpen) return;
    const handleKeyDown = (e) => {
      if (e.key === 'Escape') {
        onClose();
      } else if (e.key === 'ArrowLeft' && currentPage > 1) {
        setCurrentPage((prev) => Math.max(1, prev - 1));
      } else if (e.key === 'ArrowRight' && pageData && currentPage < pageData.total_pages) {
        setCurrentPage((prev) => Math.min(pageData.total_pages, prev + 1));
      }
    };
    window.addEventListener('keydown', handleKeyDown);
    return () => window.removeEventListener('keydown', handleKeyDown);
  }, [isOpen, currentPage, pageData, onClose]);

  if (!isOpen) return null;

  const totalPages = pageData?.total_pages || 1;
  const isPdf = pageData ? pageData.file_type === 'pdf' : filename.toLowerCase().endsWith('.pdf');
  const fileUrl = pageData?.file_url || `http://localhost:8000/api/documents/${docId}/file#page=${currentPage}`;

  const handleCopyText = () => {
    if (!pageData?.content) return;
    navigator.clipboard.writeText(pageData.content);
    setCopied(true);
    setTimeout(() => setCopied(false), 2000);
  };

  const handleOpenExternal = () => {
    window.open(fileUrl, '_blank', 'noopener,noreferrer');
  };

  return (
    <div
      className="fixed inset-0 z-50 flex items-center justify-center p-3 sm:p-6 bg-slate-950/80 backdrop-blur-md animate-fadeIn"
      onClick={onClose}
    >
      <div
        className="w-full max-w-5xl h-[90vh] bg-surface-900 border border-slate-700/80 rounded-2xl shadow-2xl flex flex-col overflow-hidden text-slate-100"
        onClick={(e) => e.stopPropagation()}
      >
        {/* Top Header Bar */}
        <div className="flex-shrink-0 px-5 py-3.5 bg-surface-950/90 border-b border-slate-800 flex items-center justify-between">
          <div className="flex items-center space-x-3 min-w-0 mr-3">
            <div className="p-2 rounded-xl bg-brand-500/10 border border-brand-500/20 text-brand-400 flex-shrink-0">
              <BookOpen className="w-4 h-4" />
            </div>
            <div className="min-w-0">
              <div className="flex items-center space-x-2">
                <h3 className="text-sm font-bold text-white truncate max-w-[160px] sm:max-w-[240px] md:max-w-sm">
                  {pageData?.filename || filename}
                </h3>
                <span className="text-[10px] uppercase font-bold tracking-wider px-2 py-0.5 rounded-full bg-slate-800 text-brand-300 border border-slate-700 flex-shrink-0">
                  {pageData?.file_type || (isPdf ? 'pdf' : 'doc')}
                </span>
              </div>
              <p className="text-[11px] text-slate-400">
                Viewing cited source page from ChromaDB index
              </p>
            </div>
          </div>

          {/* Navigation Controls */}
          <div className="flex items-center space-x-2">
            <div className="flex items-center bg-surface-900 border border-slate-700/80 rounded-xl px-1.5 py-1">
              <button
                type="button"
                onClick={() => setCurrentPage((p) => Math.max(1, p - 1))}
                disabled={currentPage <= 1 || loading}
                title="Previous page (Left arrow)"
                className="p-1 rounded-lg text-slate-400 hover:text-white hover:bg-slate-800 disabled:opacity-30 disabled:cursor-not-allowed transition-colors"
              >
                <ChevronLeft className="w-4 h-4" />
              </button>

              <div className="px-3 text-xs font-semibold text-slate-200">
                <span>Page </span>
                <span className="text-brand-400 font-bold">{currentPage}</span>
                <span className="text-slate-500"> / {totalPages}</span>
              </div>

              <button
                type="button"
                onClick={() => setCurrentPage((p) => Math.min(totalPages, p + 1))}
                disabled={currentPage >= totalPages || loading}
                title="Next page (Right arrow)"
                className="p-1 rounded-lg text-slate-400 hover:text-white hover:bg-slate-800 disabled:opacity-30 disabled:cursor-not-allowed transition-colors"
              >
                <ChevronRight className="w-4 h-4" />
              </button>
            </div>

            {/* View Mode Tabs (for PDF) */}
            {isPdf && (
              <div className="hidden sm:flex items-center bg-surface-900 border border-slate-700/80 rounded-xl p-0.5 text-xs">
                <button
                  type="button"
                  onClick={() => setActiveTab('preview')}
                  className={`px-3 py-1 rounded-lg font-medium transition-all ${
                    activeTab === 'preview'
                      ? 'bg-brand-600 text-white shadow-sm'
                      : 'text-slate-400 hover:text-slate-200'
                  }`}
                >
                  Document Viewer
                </button>
                <button
                  type="button"
                  onClick={() => setActiveTab('text')}
                  className={`px-3 py-1 rounded-lg font-medium transition-all ${
                    activeTab === 'text'
                      ? 'bg-brand-600 text-white shadow-sm'
                      : 'text-slate-400 hover:text-slate-200'
                  }`}
                >
                  Extracted Text
                </button>
              </div>
            )}

            {/* Open Raw File in New Tab Button */}
            <button
              type="button"
              onClick={handleOpenExternal}
              title="Open full file at this page in browser tab"
              className="flex items-center space-x-1 px-3 py-1.5 rounded-xl bg-slate-800/80 hover:bg-slate-700 border border-slate-700 text-xs font-semibold text-slate-200 hover:text-white transition-colors"
            >
              <ExternalLink className="w-3.5 h-3.5 text-brand-400" />
              <span className="hidden md:inline">Open in Tab</span>
            </button>

            {/* Close Modal Button */}
            <button
              type="button"
              onClick={onClose}
              title="Close viewer (Esc)"
              className="p-1.5 rounded-xl text-slate-400 hover:text-white hover:bg-slate-800 border border-transparent hover:border-slate-700 transition-colors"
            >
              <X className="w-4 h-4" />
            </button>
          </div>
        </div>

        {/* Content Area */}
        <div className="flex-1 min-h-0 bg-surface-950 p-4 overflow-hidden relative">
          {loading && (
            <div className="absolute inset-0 bg-surface-950/70 backdrop-blur-sm z-10 flex flex-col items-center justify-center space-y-3">
              <Loader2 className="w-8 h-8 text-brand-400 animate-spin" />
              <p className="text-xs font-medium text-slate-300">
                Loading Page {currentPage}...
              </p>
            </div>
          )}

          {error && (
            <div className="h-full flex flex-col items-center justify-center p-6 text-center">
              <div className="w-12 h-12 rounded-2xl bg-rose-500/10 border border-rose-500/20 text-rose-400 flex items-center justify-center mb-3">
                <FileText className="w-6 h-6" />
              </div>
              <h4 className="text-sm font-bold text-white mb-1">Unable to load page</h4>
              <p className="text-xs text-slate-400 max-w-md mb-4">{error}</p>
              <button
                type="button"
                onClick={() => fetchPage(currentPage)}
                className="px-4 py-2 rounded-xl text-xs font-semibold bg-slate-800 hover:bg-slate-700 text-white transition-colors"
              >
                Retry
              </button>
            </div>
          )}

          {!error && isPdf && activeTab === 'preview' ? (
            <div className="w-full h-full rounded-xl overflow-hidden border border-slate-800 bg-slate-900 shadow-inner">
              <iframe
                title={`Page ${currentPage} of ${filename}`}
                src={`http://localhost:8000/api/documents/${docId}/file#page=${currentPage}&toolbar=1&navpanes=0`}
                className="w-full h-full border-0"
              />
            </div>
          ) : !error ? (
            <div className="w-full h-full flex flex-col bg-surface-900/60 border border-slate-800 rounded-xl overflow-hidden">
              {/* Text Viewer Toolbar */}
              <div className="flex-shrink-0 px-4 py-2.5 bg-slate-950/60 border-b border-slate-800 flex items-center justify-between text-xs">
                <div className="flex items-center space-x-2 text-slate-400">
                  <FileCode className="w-3.5 h-3.5 text-brand-400" />
                  <span>
                    Indexed Text for <strong>Page {currentPage}</strong>
                  </span>
                  {pageData?.content && (
                    <span className="text-[11px] text-slate-500">
                      • {pageData.content.split(/\s+/).filter(Boolean).length} words
                    </span>
                  )}
                </div>

                <button
                  type="button"
                  onClick={handleCopyText}
                  className="flex items-center space-x-1.5 px-2.5 py-1 rounded-lg bg-slate-800 hover:bg-slate-700 text-slate-300 hover:text-white transition-colors text-xs font-medium"
                >
                  {copied ? (
                    <>
                      <Check className="w-3.5 h-3.5 text-emerald-400" />
                      <span className="text-emerald-400">Copied</span>
                    </>
                  ) : (
                    <>
                      <Copy className="w-3.5 h-3.5" />
                      <span>Copy Page Text</span>
                    </>
                  )}
                </button>
              </div>

              {/* Text View Body */}
              <div className="flex-1 p-5 overflow-y-auto custom-scrollbar font-mono text-xs leading-relaxed text-slate-200 select-text whitespace-pre-wrap">
                {pageData?.content ? (
                  pageData.content
                ) : (
                  <div className="h-full flex items-center justify-center text-slate-500 italic">
                    No text extracted for this page.
                  </div>
                )}
              </div>
            </div>
          ) : null}
        </div>

        {/* Bottom Status Footer */}
        <div className="flex-shrink-0 px-5 py-2.5 bg-surface-950/90 border-t border-slate-800/80 flex items-center justify-between text-[11px] text-slate-500">
          <div className="flex items-center space-x-2">
            <span className="w-1.5 h-1.5 rounded-full bg-emerald-400" />
            <span>ChromaDB Vector Verified Citation</span>
          </div>
          <div className="flex items-center space-x-4">
            <span>Use Left/Right arrow keys to flip pages</span>
            <span>Esc to close</span>
          </div>
        </div>
      </div>
    </div>
  );
}
