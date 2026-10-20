import React, { useState, useRef } from 'react';
import axios from 'axios';
import {
  UploadCloud,
  FileText,
  CheckCircle2,
  AlertCircle,
  Loader2,
  Sparkles,
  ArrowRight,
  ShieldCheck,
  Zap,
  Layers,
  HelpCircle
} from 'lucide-react';

export default function UploadPage({ onUploadSuccess, onNavigateTab, onSelectDoc }) {
  const [dragActive, setDragActive] = useState(false);
  const [loading, setLoading] = useState(false);
  const [uploadStatus, setUploadStatus] = useState('');
  const [uploadProgress, setUploadProgress] = useState(0);
  const [error, setError] = useState(null);
  const [lastUploaded, setLastUploaded] = useState(null);
  const fileInputRef = useRef(null);

  const handleDrag = (e) => {
    e.preventDefault();
    e.stopPropagation();
    if (e.type === 'dragenter' || e.type === 'dragover') {
      setDragActive(true);
    } else if (e.type === 'dragleave') {
      setDragActive(false);
    }
  };

  const processFile = async (file) => {
    if (!file) return;

    setError(null);
    setLastUploaded(null);

    const ext = file.name.split('.').pop().toLowerCase();
    if (!['pdf', 'txt', 'docx', 'doc'].includes(ext)) {
      setError('Unsupported file type. Please upload a .pdf, .txt, .docx, or .doc file.');
      return;
    }

    const MAX_FILE_SIZE = 500 * 1024 * 1024; // 500MB Maximum
    if (file.size > MAX_FILE_SIZE) {
      setError('File exceeds 500MB maximum upload limit.');
      return;
    }

    const formData = new FormData();
    formData.append('file', file);

    setLoading(true);
    setUploadStatus('Uploading file to server...');
    setUploadProgress(20);

    try {
      const response = await axios.post('http://localhost:8000/api/upload', formData, {
        headers: {
          'Content-Type': 'multipart/form-data',
        },
        timeout: 180000,
        onUploadProgress: (progressEvent) => {
          if (progressEvent.total) {
            const percent = Math.round((progressEvent.loaded * 100) / progressEvent.total);
            if (percent < 95) {
              setUploadProgress(percent);
              setUploadStatus(`Uploading document (${percent}%)...`);
            } else {
              setUploadProgress(95);
              setUploadStatus('Extracting text & generating ChromaDB vector embeddings...');
            }
          }
        },
      });

      setUploadProgress(100);
      setUploadStatus('Document successfully indexed!');
      setLastUploaded(response.data);

      if (onUploadSuccess) {
        onUploadSuccess(response.data);
      }
      if (onSelectDoc) {
        onSelectDoc(response.data);
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
    if (loading) return;
    if (e.dataTransfer.files && e.dataTransfer.files[0]) {
      processFile(e.dataTransfer.files[0]);
    }
  };

  const handleFileChange = (e) => {
    if (e.target.files && e.target.files[0]) {
      processFile(e.target.files[0]);
    }
  };

  return (
    <div className="flex-1 min-h-0 overflow-y-auto custom-scrollbar max-w-5xl w-full mx-auto p-4 sm:p-6 lg:p-8 space-y-6">
      {/* Header */}
      <div className="text-center max-w-xl mx-auto space-y-2">
        <h1 className="text-2xl font-extrabold text-slate-900 tracking-tight">
          Upload & Index Document
        </h1>
        <p className="text-xs sm:text-sm text-slate-500">
          Extract text with PyMuPDF, chunk content into 1,000-character segments, and store in persistent ChromaDB embeddings.
        </p>
      </div>

      {/* Main Drag-and-Drop Card */}
      <div className="bg-white rounded-2xl border border-slate-200/90 p-6 sm:p-8 shadow-sm space-y-6">
        <div
          onDragEnter={handleDrag}
          onDragLeave={handleDrag}
          onDragOver={handleDrag}
          onDrop={handleDrop}
          onClick={() => !loading && fileInputRef.current?.click()}
          className={`relative flex flex-col items-center justify-center p-8 sm:p-12 rounded-2xl border-2 border-dashed transition-all cursor-pointer ${
            loading
              ? 'opacity-60 cursor-not-allowed border-slate-300 bg-slate-50'
              : dragActive
              ? 'border-indigo-500 bg-indigo-50/70 scale-[1.01]'
              : 'border-slate-300 hover:border-indigo-400 bg-slate-50/40 hover:bg-indigo-50/30'
          }`}
        >
          <input
            ref={fileInputRef}
            type="file"
            accept=".pdf,.txt,.docx,.doc,application/pdf,text/plain,application/vnd.openxmlformats-officedocument.wordprocessingml.document,application/msword"
            disabled={loading}
            className="hidden"
            onChange={handleFileChange}
          />

          <div className="w-16 h-16 rounded-2xl bg-white border border-slate-200 shadow-sm flex items-center justify-center mb-4 group-hover:scale-105 transition-transform">
            <UploadCloud className={`w-8 h-8 ${dragActive ? 'text-indigo-600' : 'text-slate-500'}`} />
          </div>

          <p className="text-sm sm:text-base font-bold text-slate-800 text-center">
            Drag and drop your file here, or <span className="text-indigo-600 underline decoration-indigo-300">browse files</span>
          </p>
          <p className="text-xs text-slate-500 mt-1">
            Supports PDF, plain text (.txt), and Word (.docx, .doc) documents up to 500MB
          </p>

          <div className="mt-4 flex items-center space-x-2">
            <span className="px-2 py-1 rounded-md text-[11px] font-mono bg-white text-slate-600 border border-slate-200 shadow-2xs">.pdf</span>
            <span className="px-2 py-1 rounded-md text-[11px] font-mono bg-white text-slate-600 border border-slate-200 shadow-2xs">.txt</span>
            <span className="px-2 py-1 rounded-md text-[11px] font-mono bg-white text-slate-600 border border-slate-200 shadow-2xs">.docx</span>
            <span className="px-2 py-1 rounded-md text-[11px] font-mono bg-white text-slate-600 border border-slate-200 shadow-2xs">.doc</span>
          </div>
        </div>

        {/* Loading Progress Bar */}
        {loading && (
          <div className="p-4 rounded-xl bg-indigo-50/80 border border-indigo-200 space-y-2 animate-fade-in">
            <div className="flex items-center justify-between text-xs font-semibold text-indigo-900">
              <span className="flex items-center space-x-2">
                <Loader2 className="w-4 h-4 animate-spin text-indigo-600" />
                <span>{uploadStatus}</span>
              </span>
              <span>{uploadProgress}%</span>
            </div>
            <div className="w-full bg-indigo-100 h-2 rounded-full overflow-hidden">
              <div
                className="bg-gradient-to-r from-indigo-600 to-blue-600 h-full transition-all duration-300 rounded-full"
                style={{ width: `${uploadProgress}%` }}
              />
            </div>
          </div>
        )}

        {/* Error Notification */}
        {error && (
          <div className="p-4 rounded-xl bg-rose-50 border border-rose-200 flex items-start space-x-3 text-xs text-rose-700 animate-fade-in">
            <AlertCircle className="w-4 h-4 text-rose-500 flex-shrink-0 mt-0.5" />
            <div>
              <p className="font-bold">Upload Failed</p>
              <p>{error}</p>
            </div>
          </div>
        )}

        {/* Success Card */}
        {lastUploaded && (
          <div className="p-5 rounded-2xl bg-emerald-50 border border-emerald-200 space-y-3 animate-slide-up">
            <div className="flex items-center justify-between">
              <div className="flex items-center space-x-2.5">
                <div className="w-8 h-8 rounded-full bg-emerald-100 text-emerald-600 flex items-center justify-center">
                  <CheckCircle2 className="w-5 h-5" />
                </div>
                <div>
                  <h3 className="text-sm font-bold text-slate-900">{lastUploaded.filename}</h3>
                  <p className="text-xs text-emerald-700 font-medium">Successfully processed and indexed into ChromaDB</p>
                </div>
              </div>
              <span className="text-xs font-mono font-bold px-2.5 py-1 rounded-full bg-white text-emerald-800 border border-emerald-200">
                {lastUploaded.chunks} chunks
              </span>
            </div>

            <div className="pt-2 border-t border-emerald-200/60 flex items-center justify-end space-x-3">
              <button
                onClick={() => onNavigateTab && onNavigateTab('chat')}
                className="flex items-center space-x-1.5 px-4 py-2 rounded-xl text-xs font-semibold text-white bg-indigo-600 hover:bg-indigo-500 shadow-xs transition-all active:scale-95"
              >
                <span>Start Chatting Now</span>
                <ArrowRight className="w-3.5 h-3.5" />
              </button>
            </div>
          </div>
        )}
      </div>

      {/* RAG Information Cards */}
      <div className="grid grid-cols-1 sm:grid-cols-3 gap-4">
        <div className="bg-white rounded-2xl border border-slate-200/90 p-4 shadow-sm space-y-2">
          <div className="w-8 h-8 rounded-lg bg-indigo-50 text-indigo-600 flex items-center justify-center">
            <Zap className="w-4 h-4" />
          </div>
          <h4 className="text-xs font-bold text-slate-900">PyMuPDF Text Parser</h4>
          <p className="text-[11px] text-slate-500 leading-relaxed">
            Extracts native text, fonts, and page structures accurately with multi-page bookmarking.
          </p>
        </div>

        <div className="bg-white rounded-2xl border border-slate-200/90 p-4 shadow-sm space-y-2">
          <div className="w-8 h-8 rounded-lg bg-blue-50 text-blue-600 flex items-center justify-center">
            <Layers className="w-4 h-4" />
          </div>
          <h4 className="text-xs font-bold text-slate-900">Text Chunking</h4>
          <p className="text-[11px] text-slate-500 leading-relaxed">
            Splits text into 1,000-character chunks with a 200-character overlap for complete contextual continuity.
          </p>
        </div>

        <div className="bg-white rounded-2xl border border-slate-200/90 p-4 shadow-sm space-y-2">
          <div className="w-8 h-8 rounded-lg bg-emerald-50 text-emerald-600 flex items-center justify-center">
            <ShieldCheck className="w-4 h-4" />
          </div>
          <h4 className="text-xs font-bold text-slate-900">ChromaDB Persistent Store</h4>
          <p className="text-[11px] text-slate-500 leading-relaxed">
            Embeddings are persisted to disk in the vector database and can be queried instantly at any time.
          </p>
        </div>
      </div>
    </div>
  );
}
