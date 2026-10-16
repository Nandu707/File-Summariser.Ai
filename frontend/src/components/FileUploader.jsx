import React, { useState, useEffect, useRef } from 'react';
import axios from 'axios';
import { UploadCloud, FileText, CheckCircle2, AlertCircle, Loader2, Sparkles, Layers, Trash2 } from 'lucide-react';

export default function FileUploader({ onUploadSuccess, activeDocId, onSelectDoc, disabled = false }) {
  const [dragActive, setDragActive] = useState(false);
  const [loading, setLoading] = useState(false);
  const [uploadStatus, setUploadStatus] = useState('Extracting & Chunking Document...');
  const [error, setError] = useState(null);
  const [documents, setDocuments] = useState([]);
  const fileInputRef = useRef(null);

  // Fetch document list from backend
  const fetchDocuments = async () => {
    try {
      const res = await axios.get('http://localhost:8000/api/documents');
      if (Array.isArray(res.data)) {
        setDocuments(res.data);
      }
    } catch (err) {
      // Backend might still be starting
    }
  };

  useEffect(() => {
    fetchDocuments();
    const interval = setInterval(fetchDocuments, 8000);
    return () => clearInterval(interval);
  }, []);

  const handleDrag = (e) => {
    e.preventDefault();
    e.stopPropagation();
    if (e.type === 'dragenter' || e.type === 'dragover') {
      setDragActive(true);
    } else if (e.type === 'dragleave') {
      setDragActive(false);
    }
  };

  const validateAndUpload = async (file) => {
    if (!file || disabled) return;

    setError(null);
    const ext = file.name.split('.').pop().toLowerCase();
    if (!['pdf', 'txt', 'docx', 'doc'].includes(ext)) {
      setError('Only .pdf, .txt, .docx, and .doc files are supported.');
      return;
    }

    const formData = new FormData();
    formData.append('file', file);

    setLoading(true);
    setUploadStatus('Uploading document...');

    try {
      // POST FormData to http://localhost:8000/api/upload using axios with 3-minute timeout for large files
      const response = await axios.post('http://localhost:8000/api/upload', formData, {
        headers: {
          'Content-Type': 'multipart/form-data',
        },
        timeout: 180000,
        onUploadProgress: (progressEvent) => {
          if (progressEvent.total) {
            const percent = Math.round((progressEvent.loaded * 100) / progressEvent.total);
            if (percent < 100) {
              setUploadStatus(`Uploading file (${percent}%)...`);
            } else {
              setUploadStatus('Extracting text with PyMuPDF & indexing chunks...');
            }
          }
        },
      });

      const data = response.data; // { doc_id, filename, chunks }
      await fetchDocuments();

      if (onUploadSuccess) {
        onUploadSuccess(data);
      }
    } catch (err) {
      const msg = err.response?.data?.detail || err.message || 'Failed to upload and index document.';
      setError(msg);
    } finally {
      setLoading(false);
    }
  };

  const handleDrop = (e) => {
    e.preventDefault();
    e.stopPropagation();
    setDragActive(false);
    if (disabled || loading) return;
    if (e.dataTransfer.files && e.dataTransfer.files[0]) {
      validateAndUpload(e.dataTransfer.files[0]);
    }
  };

  const handleFileChange = (e) => {
    if (e.target.files && e.target.files[0]) {
      validateAndUpload(e.target.files[0]);
    }
  };

  const handleDelete = async (e, docId) => {
    e.stopPropagation();
    if (disabled) return;
    try {
      await axios.delete(`http://localhost:8000/api/documents/${docId}`);
      await fetchDocuments();
      if (activeDocId === docId && onSelectDoc) {
        const remaining = documents.filter((d) => d.doc_id !== docId);
        onSelectDoc(remaining.length > 0 ? remaining[0] : null);
      }
    } catch (err) {
      console.error('Delete failed:', err);
    }
  };

  const activeDoc = documents.find((d) => d.doc_id === activeDocId);

  return (
    <aside className="w-full lg:w-96 flex flex-col glass-card rounded-2xl border border-slate-800/80 p-5 h-full overflow-hidden">
      {/* Header */}
      <div className="pb-4 border-b border-slate-800/80 flex items-center justify-between">
        <div className="flex items-center space-x-2.5">
          <div className="w-8 h-8 rounded-lg bg-brand-500/10 text-brand-400 border border-brand-500/20 flex items-center justify-center">
            <UploadCloud className="w-4 h-4" />
          </div>
          <div>
            <h2 className="text-sm font-bold text-white tracking-tight">Document Uploader</h2>
            <p className="text-[11px] text-slate-400"></p>
          </div>
        </div>
        <span className="text-[11px] font-semibold px-2 py-0.5 rounded-full bg-slate-800 text-slate-300">
          {documents.length} {documents.length === 1 ? 'doc' : 'docs'}
        </span>
      </div>

      <div className="flex-1 min-h-0 overflow-y-auto custom-scrollbar space-y-4 pr-1 mt-4">
        {/* Answering indicator / File switching locked */}
        {disabled && (
          <div className="p-3 rounded-xl bg-amber-500/10 border border-amber-500/30 flex items-center space-x-2.5 text-xs text-amber-300 animate-fade-in shadow-sm">
            <Loader2 className="w-4 h-4 animate-spin text-amber-400 flex-shrink-0" />
            <div>
              <p className="font-semibold text-amber-200">Answering question...</p>
              <p className="text-[11px] text-amber-400/80">File changing is temporarily locked</p>
            </div>
          </div>
        )}

        {/* Drag & Drop Zone */}
        <div
          onDragEnter={(e) => !disabled && handleDrag(e)}
          onDragLeave={(e) => !disabled && handleDrag(e)}
          onDragOver={(e) => !disabled && handleDrag(e)}
          onDrop={handleDrop}
          onClick={() => !loading && !disabled && fileInputRef.current?.click()}
          className={`relative flex flex-col items-center justify-center p-5 rounded-xl border-2 border-dashed transition-all ${
            disabled
              ? 'opacity-40 cursor-not-allowed border-slate-800 bg-slate-900/20'
              : loading
              ? 'opacity-60 cursor-not-allowed border-slate-700 bg-slate-900/30'
              : dragActive
              ? 'border-brand-400 bg-brand-500/10 scale-[1.01] cursor-pointer'
              : 'border-slate-700/80 hover:border-slate-500 bg-slate-900/40 hover:bg-slate-900/70 cursor-pointer'
          }`}
        >
          <input
            ref={fileInputRef}
            type="file"
            accept=".pdf,.txt,.docx,.doc,application/pdf,text/plain,application/vnd.openxmlformats-officedocument.wordprocessingml.document,application/msword"
            disabled={loading || disabled}
            className="hidden"
            onChange={handleFileChange}
          />

          <div className="w-10 h-10 rounded-full bg-slate-800/80 flex items-center justify-center mb-2 shadow-inner">
            <FileText className={`w-5 h-5 ${dragActive ? 'text-brand-400' : 'text-slate-400'}`} />
          </div>

          <p className="text-xs font-semibold text-slate-200 text-center">
            Drop <span className="text-brand-400">PDF</span>, <span className="text-brand-400">TXT</span>, or <span className="text-brand-400">DOCX</span> here
          </p>
          <p className="text-[11px] text-slate-500 mt-0.5">or click to browse</p>

          <div className="mt-2.5 flex items-center space-x-1.5 flex-wrap justify-center gap-y-1">
            <span className="px-1.5 py-0.5 rounded text-[10px] font-mono bg-slate-800 text-slate-400 border border-slate-700">.pdf</span>
            <span className="px-1.5 py-0.5 rounded text-[10px] font-mono bg-slate-800 text-slate-400 border border-slate-700">.txt</span>
            <span className="px-1.5 py-0.5 rounded text-[10px] font-mono bg-slate-800 text-slate-400 border border-slate-700">.docx</span>
            <span className="px-1.5 py-0.5 rounded text-[10px] font-mono bg-slate-800 text-slate-400 border border-slate-700">.doc</span>
          </div>
        </div>

        {/* Loading State during indexing */}
        {loading && (
          <div className="p-3.5 rounded-xl bg-slate-900/90 border border-brand-500/30 space-y-2 animate-fade-in">
            <div className="flex items-center space-x-2 text-xs font-medium text-brand-300">
              <Loader2 className="w-4 h-4 animate-spin text-brand-400" />
              <span>{uploadStatus}</span>
            </div>
            <div className="w-full bg-slate-800 h-1.5 rounded-full overflow-hidden">
              <div className="bg-gradient-to-r from-brand-500 to-indigo-500 h-full w-3/4 animate-pulse" />
            </div>
            <p className="text-[10px] text-slate-400">
              RecursiveCharacterTextSplitter (1000/200) • ChromaDB persistent storage
            </p>
          </div>
        )}

        {/* Error message */}
        {error && (
          <div className="p-3 rounded-xl bg-rose-500/10 border border-rose-500/30 flex items-start space-x-2 text-xs text-rose-300 animate-fade-in">
            <AlertCircle className="w-4 h-4 text-rose-400 flex-shrink-0 mt-0.5" />
            <span>{error}</span>
          </div>
        )}

        {/* Active Document Card */}
        {activeDoc && (
          <div className="p-3.5 rounded-xl bg-brand-500/10 border border-brand-500/30 space-y-2 animate-slide-up">
            <div className="flex items-center justify-between">
              <span className="text-[10px] font-bold uppercase tracking-wider text-emerald-400 flex items-center space-x-1">
                <CheckCircle2 className="w-3.5 h-3.5" />
                <span>Active Document</span>
              </span>
              <span className="text-[10px] font-mono px-2 py-0.5 rounded bg-brand-500/20 text-brand-300 border border-brand-500/30">
                {activeDoc.chunks} chunks
              </span>
            </div>
            <p className="text-xs font-semibold text-white truncate" title={activeDoc.filename}>
              {activeDoc.filename}
            </p>
            <div className="flex items-center justify-between text-[10px] text-slate-400 pt-1 border-t border-brand-500/20">
              <span className="text-emerald-400 font-medium">Ready for questions</span>
              <span className="w-2 h-2 rounded-full bg-emerald-400 animate-pulse" />
            </div>
          </div>
        )}

        {/* Document List / Switcher */}
        {documents.length > 0 && (
          <div className="space-y-2 pt-2 border-t border-slate-800/80">
            <p className="text-[11px] font-bold text-slate-400 uppercase tracking-wider">Indexed Documents</p>
            <div className="space-y-1.5 max-h-56 overflow-y-auto pr-1">
              {documents.map((doc) => {
                const isActive = doc.doc_id === activeDocId;
                const ext = doc.filename.split('.').pop().toUpperCase();
                return (
                  <div
                    key={doc.doc_id}
                    onClick={() => !disabled && onSelectDoc && onSelectDoc(doc)}
                    className={`group flex items-center justify-between p-2.5 rounded-xl border text-left transition-all ${
                      disabled
                        ? 'opacity-40 cursor-not-allowed border-slate-800/60 bg-slate-900/30'
                        : isActive
                        ? 'bg-brand-500/15 border-brand-500/40 text-white cursor-pointer'
                        : 'bg-slate-900/40 hover:bg-slate-900/80 border-slate-800 text-slate-300 hover:text-white cursor-pointer'
                    }`}
                    title={disabled ? 'File switching is disabled while generating an answer' : undefined}
                  >
                    <div className="flex items-center space-x-2 overflow-hidden pr-2">
                      <span className={`text-[9px] font-bold px-1.5 py-0.5 rounded uppercase ${
                        ext === 'PDF'
                          ? 'bg-red-500/10 text-red-400 border border-red-500/20'
                          : ext === 'DOCX' || ext === 'DOC'
                          ? 'bg-blue-600/10 text-blue-300 border border-blue-500/30'
                          : 'bg-emerald-500/10 text-emerald-400 border border-emerald-500/20'
                        }`}>
                        {ext}
                      </span>
                      <div className="truncate">
                        <p className="text-xs font-medium truncate">{doc.filename}</p>
                        <span className="text-[10px] text-slate-500 font-mono">{doc.chunks} chunks</span>
                      </div>
                    </div>

                    {!disabled && (
                      <button
                        type="button"
                        onClick={(e) => handleDelete(e, doc.doc_id)}
                        className="opacity-0 group-hover:opacity-100 p-1 text-slate-500 hover:text-rose-400 rounded transition-all"
                        title="Delete document"
                      >
                        <Trash2 className="w-3.5 h-3.5" />
                      </button>
                    )}
                  </div>
                );
              })}
            </div>
          </div>
        )}
      </div>
    </aside>
  );
}
