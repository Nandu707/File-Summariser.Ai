import React, { useState, useEffect, useRef } from 'react';
import axios from 'axios';
import {
  FileText,
  Search,
  MessageSquare,
  Eye,
  Download,
  Trash2,
  Sparkles,
  Layers,
  CheckCircle2,
  AlertCircle,
  UploadCloud,
  Loader2,
  RefreshCw,
  FileCheck,
  ArrowRight
} from 'lucide-react';
import DocumentPageModal from '../components/DocumentPageModal';
import { API_BASE_URL } from '../api';

export default function DocumentsPage({ onSelectDoc, onNavigateTab, onDocumentCountChange }) {
  const [documents, setDocuments] = useState([]);
  const [searchQuery, setSearchQuery] = useState('');
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(null);
  const [deletingId, setDeletingId] = useState(null);
  
  // Upload states
  const [dragActive, setDragActive] = useState(false);
  const [uploading, setUploading] = useState(false);
  const [uploadProgress, setUploadProgress] = useState(0);
  const [uploadStatus, setUploadStatus] = useState('');
  const [uploadError, setUploadError] = useState(null);
  const [lastUploaded, setLastUploaded] = useState(null);
  const fileInputRef = useRef(null);

  // Preview modal state
  const [previewState, setPreviewState] = useState({
    isOpen: false,
    docId: null,
    filename: '',
    page: 1
  });

  const fetchDocuments = async () => {
    setLoading(true);
    setError(null);
    try {
      const res = await axios.get(`${API_BASE_URL}/api/documents`);
      if (Array.isArray(res.data)) {
        setDocuments(res.data);
        if (onDocumentCountChange) {
          onDocumentCountChange(res.data.length);
        }
      }
    } catch (err) {
      console.error('Failed to fetch documents:', err);
      setError('Failed to fetch documents from server. Make sure the backend is running.');
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    fetchDocuments();
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

  const handleDrop = (e) => {
    e.preventDefault();
    e.stopPropagation();
    setDragActive(false);
    if (e.dataTransfer.files && e.dataTransfer.files[0]) {
      processUpload(e.dataTransfer.files[0]);
    }
  };

  const handleFileInputChange = (e) => {
    if (e.target.files && e.target.files[0]) {
      processUpload(e.target.files[0]);
    }
  };

  const processUpload = async (file) => {
    if (!file) return;

    setUploadError(null);
    setLastUploaded(null);

    const ext = file.name.split('.').pop().toLowerCase();
    if (!['pdf', 'txt', 'docx', 'doc'].includes(ext)) {
      setUploadError('Unsupported file type. Please upload a .pdf, .txt, .docx, or .doc file.');
      return;
    }

    const MAX_FILE_SIZE = 500 * 1024 * 1024; // 500MB Maximum
    if (file.size > MAX_FILE_SIZE) {
      setUploadError('File exceeds 500MB maximum upload limit.');
      return;
    }

    const formData = new FormData();
    formData.append('file', file);

    setUploading(true);
    setUploadStatus('Uploading file to server...');
    setUploadProgress(20);

    try {
      const response = await axios.post(`${API_BASE_URL}/api/upload`, formData, {
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
      setUploadStatus('Document successfully indexed in ChromaDB!');
      setLastUploaded(response.data);

      // Refresh documents list
      await fetchDocuments();

      // Ensure global search scope is updated so newly uploaded files are immediately queried
      if (onSelectDoc) {
        onSelectDoc('all');
      }

      // Reset file input
      if (fileInputRef.current) {
        fileInputRef.current.value = '';
      }
    } catch (err) {
      const msg = err.response?.data?.detail || err.message || 'Failed to upload and index document.';
      setUploadError(msg);
    } finally {
      setUploading(false);
    }
  };

  const handleDelete = async (docId, filename) => {
    const confirmed = window.confirm(`Are you sure you want to delete "${filename || 'this document'}" from the vector database? All associated chunks and chat history will be removed.`);
    if (!confirmed) return;

    setDeletingId(docId);
    try {
      await axios.delete(`${API_BASE_URL}/api/documents/${docId}`);
      if (onSelectDoc) {
        onSelectDoc('all');
      }
      setDocuments((prev) => {
        const updated = prev.filter((d) => d.doc_id !== docId);
        if (onDocumentCountChange) {
          onDocumentCountChange(updated.length);
        }
        return updated;
      });
    } catch (err) {
      alert('Failed to delete document: ' + (err.response?.data?.detail || err.message));
    } finally {
      setDeletingId(null);
    }
  };

  const handleOpenChat = (doc) => {
    if (onSelectDoc) {
      onSelectDoc(doc);
    }
    if (onNavigateTab) {
      onNavigateTab('chat');
    }
  };

  const handlePreview = (doc) => {
    setPreviewState({
      isOpen: true,
      docId: doc.doc_id,
      filename: doc.filename,
      page: 1
    });
  };

  const filteredDocs = documents.filter((d) =>
    (d.filename || '').toLowerCase().includes(searchQuery.toLowerCase())
  );

  const totalChunks = documents.reduce((sum, d) => sum + (d.chunks || 0), 0);

  return (
    <div className="flex-1 min-h-0 overflow-y-auto custom-scrollbar max-w-7xl w-full mx-auto p-4 sm:p-6 lg:p-8 space-y-6">
      {/* Top Header & Navigation */}
      <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-4 pb-4 border-b border-slate-200">
        <div>
          <h1 className="text-xl font-bold text-slate-900 tracking-tight flex items-center space-x-2">
            <Layers className="w-5 h-5 text-indigo-600" />
            <span>Document Upload & Management</span>
          </h1>
        </div>

        <div className="flex items-center space-x-3">
          <button
            onClick={() => fetchDocuments()}
            disabled={loading}
            className="flex items-center space-x-1.5 px-3 py-1.5 rounded-xl text-xs font-medium text-slate-600 hover:text-slate-900 bg-white border border-slate-200 hover:border-slate-300 shadow-2xs transition-all active:scale-95"
            title="Refresh document list"
          >
            <RefreshCw className={`w-3.5 h-3.5 ${loading ? 'animate-spin text-indigo-600' : ''}`} />
            <span>Refresh</span>
          </button>
        </div>
      </div>

      {/* Integrated Upload Box / Dropzone */}
      <div className="bg-white rounded-2xl border border-slate-200/90 p-5 shadow-sm space-y-4">
        <div className="flex items-center space-x-2">
          <div className="w-8 h-8 rounded-lg bg-indigo-50 text-indigo-600 flex items-center justify-center">
            <UploadCloud className="w-4 h-4" />
          </div>
          <div>
            <h2 className="text-sm font-bold text-slate-900">Upload New File</h2>
            <p className="text-[11px] text-slate-500">Supports PDF, DOCX, DOC, and TXT (large files up to 500MB)</p>
          </div>
        </div>

        <div
          onDragEnter={handleDrag}
          onDragLeave={handleDrag}
          onDragOver={handleDrag}
          onDrop={handleDrop}
          onClick={() => !uploading && fileInputRef.current?.click()}
          className={`relative border-2 border-dashed rounded-2xl p-6 sm:p-8 text-center cursor-pointer transition-all ${
            dragActive
              ? 'border-indigo-600 bg-indigo-50/70 scale-[0.99]'
              : uploading
              ? 'border-slate-300 bg-slate-50/80 cursor-not-allowed'
              : 'border-slate-300 hover:border-indigo-400 hover:bg-indigo-50/20'
          }`}
        >
          <input
            ref={fileInputRef}
            type="file"
            accept=".pdf,.docx,.doc,.txt"
            onChange={handleFileInputChange}
            className="hidden"
            disabled={uploading}
          />

          <div className="flex flex-col items-center justify-center space-y-3">
            <div className={`w-12 h-12 rounded-2xl flex items-center justify-center transition-colors ${
              dragActive ? 'bg-indigo-600 text-white' : 'bg-indigo-50 text-indigo-600'
            }`}>
              {uploading ? (
                <Loader2 className="w-6 h-6 animate-spin text-indigo-600" />
              ) : (
                <UploadCloud className="w-6 h-6" />
              )}
            </div>

            <div>
              <p className="text-sm font-semibold text-slate-800">
                {uploading
                  ? 'Processing Document...'
                  : dragActive
                  ? 'Drop your file here to upload'
                  : 'Click to select or drag & drop document here'}
              </p>
              <p className="text-xs text-slate-400 mt-1">
                PDF (PyMuPDF with page segmentation), Word (.docx), or plain text (.txt)
              </p>
            </div>

            {!uploading && (
              <button
                type="button"
                className="mt-1 px-4 py-1.5 rounded-xl text-xs font-semibold text-indigo-700 bg-indigo-50 border border-indigo-200 hover:bg-indigo-100 transition-colors pointer-events-none"
              >
                Browse Files
              </button>
            )}
          </div>

          {/* Progress Bar */}
          {uploading && (
            <div className="mt-4 max-w-md mx-auto space-y-2">
              <div className="w-full bg-slate-200 rounded-full h-2 overflow-hidden">
                <div
                  className="bg-gradient-to-r from-indigo-600 to-blue-600 h-2 rounded-full transition-all duration-300"
                  style={{ width: `${uploadProgress}%` }}
                />
              </div>
              <p className="text-xs font-medium text-slate-600 flex items-center justify-center space-x-1.5">
                <Loader2 className="w-3.5 h-3.5 animate-spin text-indigo-600" />
                <span>{uploadStatus}</span>
              </p>
            </div>
          )}
        </div>

        {/* Upload Success Alert */}
        {lastUploaded && (
          <div className="p-3.5 rounded-xl bg-emerald-50 border border-emerald-200 text-xs text-emerald-800 flex flex-col sm:flex-row sm:items-center justify-between gap-3">
            <div className="flex items-center space-x-2">
              <CheckCircle2 className="w-4 h-4 text-emerald-600 flex-shrink-0" />
              <span>
                Successfully indexed <strong>{lastUploaded.filename}</strong> ({lastUploaded.chunks} vector chunks). Ready for Q&A!
              </span>
            </div>
            <div className="flex items-center space-x-2">
              <button
                onClick={() => handleOpenChat(lastUploaded)}
                className="inline-flex items-center space-x-1 px-3 py-1.5 rounded-lg text-xs font-semibold text-emerald-800 bg-emerald-100 hover:bg-emerald-200 transition-colors"
                title="Ask questions specifically about this newly uploaded file"
              >
                <span>Chat with this File</span>
                <ArrowRight className="w-3.5 h-3.5" />
              </button>
              <button
                onClick={() => handleOpenChat('all')}
                className="inline-flex items-center space-x-1 px-3 py-1.5 rounded-lg text-xs font-semibold text-white bg-indigo-600 hover:bg-indigo-500 shadow-2xs transition-colors"
                title="Search across all uploaded files including this new one"
              >
                <span>Search All Files</span>
                <ArrowRight className="w-3.5 h-3.5" />
              </button>
            </div>
          </div>
        )}

        {/* Upload Error Alert */}
        {uploadError && (
          <div className="p-3.5 rounded-xl bg-rose-50 border border-rose-200 text-xs text-rose-800 flex items-center justify-between">
            <div className="flex items-center space-x-2">
              <AlertCircle className="w-4 h-4 text-rose-600 flex-shrink-0" />
              <span>{uploadError}</span>
            </div>
            <button
              onClick={() => setUploadError(null)}
              className="text-xs font-semibold text-rose-600 hover:text-rose-800 underline ml-2"
            >
              Dismiss
            </button>
          </div>
        )}
      </div>

      {/* Stats Cards */}
      <div className="grid grid-cols-1 sm:grid-cols-2 gap-4">
        <div className="bg-white rounded-2xl border border-slate-200/90 p-4 shadow-sm flex items-center space-x-3">
          <div className="w-10 h-10 rounded-xl bg-indigo-50 border border-indigo-100 text-indigo-600 flex items-center justify-center">
            <FileText className="w-5 h-5" />
          </div>
          <div>
            <p className="text-[11px] font-medium text-slate-500">Total Indexed Files</p>
            <p className="text-lg font-bold text-slate-900">{documents.length}</p>
          </div>
        </div>

        <div className="bg-white rounded-2xl border border-slate-200/90 p-4 shadow-sm flex items-center space-x-3">
          <div className="w-10 h-10 rounded-xl bg-blue-50 border border-blue-100 text-blue-600 flex items-center justify-center">
            <Layers className="w-5 h-5" />
          </div>
          <div>
            <p className="text-[11px] font-medium text-slate-500">Vector Chunks in ChromaDB</p>
            <p className="text-lg font-bold text-slate-900">{totalChunks.toLocaleString()}</p>
          </div>
        </div>
      </div>

      {/* Search and Manage Header */}
      <div className="space-y-3">
        <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-3">
          <h2 className="text-sm font-bold text-slate-900 flex items-center space-x-2">
            <span>Manage Uploaded Files</span>
            <span className="text-xs font-normal text-slate-500">({filteredDocs.length} of {documents.length})</span>
          </h2>

          <div className="relative w-full sm:w-80">
            <Search className="w-4 h-4 text-slate-400 absolute left-3 top-1/2 -translate-y-1/2" />
            <input
              type="text"
              value={searchQuery}
              onChange={(e) => setSearchQuery(e.target.value)}
              placeholder="Search files by name..."
              className="w-full bg-white border border-slate-200 focus:border-indigo-500 focus:ring-2 focus:ring-indigo-100 rounded-xl pl-9 pr-3 py-1.5 text-xs text-slate-900 placeholder:text-slate-400 shadow-2xs transition-all"
            />
          </div>
        </div>

        {/* Documents Grid */}
        {loading ? (
          <div className="py-16 text-center text-xs text-slate-500 bg-white rounded-2xl border border-slate-200/90">
            <Loader2 className="w-6 h-6 animate-spin text-indigo-600 mx-auto mb-2" />
            <span>Loading indexed documents...</span>
          </div>
        ) : error ? (
          <div className="p-4 rounded-xl bg-rose-50 border border-rose-200 text-xs text-rose-700 flex items-center space-x-2">
            <AlertCircle className="w-4 h-4 text-rose-500 flex-shrink-0" />
            <span>{error}</span>
          </div>
        ) : filteredDocs.length === 0 ? (
          <div className="bg-white rounded-2xl border border-slate-200 p-12 text-center max-w-md mx-auto shadow-sm">
            <div className="w-12 h-12 rounded-2xl bg-indigo-50 border border-indigo-100 text-indigo-600 flex items-center justify-center mx-auto mb-3">
              <FileText className="w-6 h-6" />
            </div>
            <h3 className="text-sm font-bold text-slate-900">No documents found</h3>
            <p className="text-xs text-slate-500 mt-1 mb-4">
              {searchQuery ? `No files matching "${searchQuery}"` : 'Upload your first document using the dropzone above.'}
            </p>
            {searchQuery && (
              <button
                onClick={() => setSearchQuery('')}
                className="px-3.5 py-1.5 rounded-xl text-xs font-semibold text-slate-600 bg-slate-100 hover:bg-slate-200"
              >
                Clear Search
              </button>
            )}
          </div>
        ) : (
          <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-4">
            {filteredDocs.map((doc) => {
              const ext = (doc.filename || '').split('.').pop().toUpperCase();
              const isDeleting = deletingId === doc.doc_id;

              return (
                <div
                  key={doc.doc_id}
                  className="bg-white rounded-2xl border border-slate-200/90 hover:border-indigo-300 p-4 shadow-sm hover:shadow-md transition-all flex flex-col justify-between group"
                >
                  <div>
                    {/* Card Header with Badges */}
                    <div className="flex items-start justify-between gap-2 mb-3">
                      <span className={`text-[10px] font-bold px-2 py-0.5 rounded uppercase tracking-wider ${
                        ext === 'PDF'
                          ? 'bg-rose-50 text-rose-700 border border-rose-200'
                          : ext === 'DOCX' || ext === 'DOC'
                          ? 'bg-blue-50 text-blue-700 border border-blue-200'
                          : 'bg-emerald-50 text-emerald-700 border border-emerald-200'
                      }`}>
                        {ext}
                      </span>
                      <span className="text-[10px] font-mono px-2 py-0.5 rounded-full bg-slate-100 text-slate-600 border border-slate-200">
                        {doc.chunks} chunks
                      </span>
                    </div>

                    {/* Title */}
                    <h3 className="text-sm font-bold text-slate-900 line-clamp-2 mb-1 group-hover:text-indigo-600 transition-colors" title={doc.filename}>
                      {doc.filename}
                    </h3>

                    {doc.pages_count ? (
                      <div className="flex items-center space-x-3 text-[11px] text-slate-400 mb-4">
                        <span>{doc.pages_count} pages</span>
                      </div>
                    ) : (
                      <div className="mb-4" />
                    )}
                  </div>

                  {/* Actions Bar */}
                  <div className="pt-3 border-t border-slate-100 flex items-center justify-between gap-1">
                    <div className="flex items-center space-x-1">
                      <button
                        onClick={() => handlePreview(doc)}
                        title="Preview Document Pages"
                        className="p-1.5 rounded-lg text-slate-500 hover:text-indigo-600 hover:bg-indigo-50 transition-colors"
                      >
                        <Eye className="w-4 h-4" />
                      </button>
                      <a
                        href={`${API_BASE_URL}/api/documents/${doc.doc_id}/file`}
                        target="_blank"
                        rel="noreferrer"
                        title="Download / View original file"
                        className="p-1.5 rounded-lg text-slate-500 hover:text-indigo-600 hover:bg-indigo-50 transition-colors"
                      >
                        <Download className="w-4 h-4" />
                      </a>
                      <button
                        onClick={() => handleDelete(doc.doc_id, doc.filename)}
                        disabled={isDeleting}
                        title="Delete from ChromaDB"
                        className="p-1.5 rounded-lg text-slate-400 hover:text-rose-600 hover:bg-rose-50 transition-colors"
                      >
                        {isDeleting ? (
                          <Loader2 className="w-4 h-4 animate-spin text-rose-500" />
                        ) : (
                          <Trash2 className="w-4 h-4" />
                        )}
                      </button>
                    </div>

                    <button
                      onClick={() => handleOpenChat(doc)}
                      className="flex items-center space-x-1 px-3 py-1.5 rounded-lg text-xs font-semibold text-indigo-700 bg-indigo-50 hover:bg-indigo-100 border border-indigo-200/80 transition-colors active:scale-95"
                    >
                      <MessageSquare className="w-3.5 h-3.5" />
                      <span>Chat</span>
                    </button>
                  </div>
                </div>
              );
            })}
          </div>
        )}
      </div>

      {/* Document Page Modal for Viewing Pages & Raw Files */}
      <DocumentPageModal
        isOpen={previewState.isOpen}
        onClose={() => setPreviewState((prev) => ({ ...prev, isOpen: false }))}
        docId={previewState.docId}
        initialPage={previewState.page}
        filename={previewState.filename}
      />
    </div>
  );
}
