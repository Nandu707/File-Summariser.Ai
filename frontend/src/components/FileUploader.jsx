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
    <aside className="w-full lg:w-88 flex flex-col bg-white rounded-2xl border border-slate-200/90 shadow-sm p-4 sm:p-5 h-full overflow-hidden">
      {/* Header */}
      <div className="pb-3.5 border-b border-slate-200/80 flex items-center justify-between">
        <div className="flex items-center space-x-2.5">
          <div className="w-8 h-8 rounded-xl bg-indigo-50 text-indigo-600 border border-indigo-200/80 flex items-center justify-center shadow-2xs">
            <UploadCloud className="w-4 h-4" />
          </div>
          <div>
            <h2 className="text-sm font-bold text-slate-900 tracking-tight">Documents</h2>
            <p className="text-[11px] text-slate-500">Vector Knowledge Base</p>
          </div>
        </div>
        <span className="text-[11px] font-semibold px-2 py-0.5 rounded-full bg-slate-100 text-slate-700 border border-slate-200">
          {documents.length} {documents.length === 1 ? 'doc' : 'docs'}
        </span>
      </div>

      <div className="flex-1 min-h-0 overflow-y-auto custom-scrollbar space-y-4 pr-1 mt-4">
        {/* Answering indicator / File switching locked */}
        {disabled && (
          <div className="p-3 rounded-xl bg-amber-50 border border-amber-200 flex items-center space-x-2.5 text-xs text-amber-800 animate-fade-in shadow-2xs">
            <Loader2 className="w-4 h-4 animate-spin text-amber-600 flex-shrink-0" />
            <div>
              <p className="font-semibold text-amber-900">Answering question...</p>
              <p className="text-[11px] text-amber-700">File changing locked while generating answer</p>
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
          className={`relative flex flex-col items-center justify-center p-4 sm:p-5 rounded-xl border-2 border-dashed transition-all ${
            disabled
              ? 'opacity-40 cursor-not-allowed border-slate-200 bg-slate-50'
              : loading
              ? 'opacity-60 cursor-not-allowed border-slate-300 bg-slate-50'
              : dragActive
              ? 'border-indigo-500 bg-indigo-50/70 scale-[1.01] cursor-pointer'
              : 'border-slate-300/80 hover:border-indigo-400 bg-slate-50/50 hover:bg-indigo-50/30 cursor-pointer shadow-2xs'
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

          <div className="w-10 h-10 rounded-full bg-white border border-slate-200 flex items-center justify-center mb-2 shadow-xs">
            <FileText className={`w-5 h-5 ${dragActive ? 'text-indigo-600' : 'text-slate-500'}`} />
          </div>

          <p className="text-xs font-semibold text-slate-800 text-center">
            Drop <span className="text-indigo-600">PDF</span>, <span className="text-indigo-600">TXT</span>, or <span className="text-indigo-600">DOCX</span> here
          </p>
          <p className="text-[11px] text-slate-500 mt-0.5">or click to browse files</p>

          <div className="mt-2.5 flex items-center space-x-1.5 flex-wrap justify-center gap-y-1">
            <span className="px-1.5 py-0.5 rounded text-[10px] font-mono bg-white text-slate-600 border border-slate-200">.pdf</span>
            <span className="px-1.5 py-0.5 rounded text-[10px] font-mono bg-white text-slate-600 border border-slate-200">.txt</span>
            <span className="px-1.5 py-0.5 rounded text-[10px] font-mono bg-white text-slate-600 border border-slate-200">.docx</span>
            <span className="px-1.5 py-0.5 rounded text-[10px] font-mono bg-white text-slate-600 border border-slate-200">.doc</span>
          </div>
        </div>

        {/* Loading State during indexing */}
        {loading && (
          <div className="p-3.5 rounded-xl bg-indigo-50/70 border border-indigo-200 space-y-2 animate-fade-in shadow-2xs">
            <div className="flex items-center space-x-2 text-xs font-semibold text-indigo-900">
              <Loader2 className="w-4 h-4 animate-spin text-indigo-600" />
              <span>{uploadStatus}</span>
            </div>
            <div className="w-full bg-indigo-100 h-1.5 rounded-full overflow-hidden">
              <div className="bg-gradient-to-r from-indigo-600 to-blue-600 h-full w-3/4 animate-pulse rounded-full" />
            </div>
            <p className="text-[10px] text-slate-500">
              Splitting into 1,000-char chunks • Indexing into ChromaDB
            </p>
          </div>
        )}

        {/* Error message */}
        {error && (
          <div className="p-3 rounded-xl bg-rose-50 border border-rose-200 flex items-start space-x-2 text-xs text-rose-700 animate-fade-in">
            <AlertCircle className="w-4 h-4 text-rose-500 flex-shrink-0 mt-0.5" />
            <span>{error}</span>
          </div>
        )}

        {/* Active Document Card */}
        {activeDoc && (
          <div className="p-3.5 rounded-xl bg-indigo-50/70 border border-indigo-200 space-y-2 animate-slide-up shadow-2xs">
            <div className="flex items-center justify-between">
              <span className="text-[10px] font-bold uppercase tracking-wider text-emerald-700 flex items-center space-x-1">
                <CheckCircle2 className="w-3.5 h-3.5 text-emerald-600" />
                <span>Active File</span>
              </span>
              <span className="text-[10px] font-mono font-medium px-2 py-0.5 rounded bg-white text-indigo-700 border border-indigo-200">
                {activeDoc.chunks} chunks
              </span>
            </div>
            <p className="text-xs font-bold text-slate-900 truncate" title={activeDoc.filename}>
              {activeDoc.filename}
            </p>
            <div className="flex items-center justify-between text-[10px] text-slate-500 pt-1 border-t border-indigo-100">
              <span className="text-emerald-700 font-medium">Ready for Q&A</span>
              <span className="w-2 h-2 rounded-full bg-emerald-500 animate-pulse" />
            </div>
          </div>
        )}

        {/* Document List / Switcher */}
        {documents.length > 0 && (
          <div className="space-y-2 pt-2 border-t border-slate-200">
            <p className="text-[11px] font-bold text-slate-500 uppercase tracking-wider">Indexed Documents</p>
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
                        ? 'opacity-40 cursor-not-allowed border-slate-200 bg-slate-50'
                        : isActive
                        ? 'bg-indigo-50/90 border-indigo-300 text-indigo-950 font-medium shadow-2xs cursor-pointer'
                        : 'bg-white hover:bg-slate-50 border-slate-200 text-slate-700 hover:text-slate-900 cursor-pointer shadow-2xs'
                    }`}
                    title={disabled ? 'File switching is disabled while generating an answer' : undefined}
                  >
                    <div className="flex items-center space-x-2 overflow-hidden pr-2">
                      <span className={`text-[9px] font-bold px-1.5 py-0.5 rounded uppercase ${
                        ext === 'PDF'
                          ? 'bg-rose-50 text-rose-700 border border-rose-200'
                          : ext === 'DOCX' || ext === 'DOC'
                          ? 'bg-blue-50 text-blue-700 border border-blue-200'
                          : 'bg-emerald-50 text-emerald-700 border border-emerald-200'
                        }`}>
                        {ext}
                      </span>
                      <div className="truncate">
                        <p className="text-xs truncate">{doc.filename}</p>
                        <span className="text-[10px] text-slate-400 font-mono">{doc.chunks} chunks</span>
                      </div>
                    </div>

                    {!disabled && (
                      <button
                        type="button"
                        onClick={(e) => handleDelete(e, doc.doc_id)}
                        className="opacity-0 group-hover:opacity-100 p-1 text-slate-400 hover:text-rose-600 rounded transition-all"
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
