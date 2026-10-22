import React, { useState, useEffect, useRef } from 'react';
import { createPortal } from 'react-dom';
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
  ArrowRight,
  X
} from 'lucide-react';
import DocumentPageModal from '../components/DocumentPageModal';
import { API_BASE_URL } from '../api';
import { useAuth } from '../context/AuthContext';

export default function DocumentsPage({ onSelectDoc, onNavigateTab, onDocumentCountChange }) {
  const { user } = useAuth();
  const isAdmin = user?.role === 'admin';

  const [documents, setDocuments] = useState([]);
  const [searchQuery, setSearchQuery] = useState('');
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(null);
  const [deletingId, setDeletingId] = useState(null);
  const [replacingId, setReplacingId] = useState(null);
  const [replacingDoc, setReplacingDoc] = useState(null);
  const [fileToDelete, setFileToDelete] = useState(null);
  const [isDeletingFile, setIsDeletingFile] = useState(false);
  
  // Multi-file upload queue states
  const [uploadTasks, setUploadTasks] = useState([]);
  const [dragActive, setDragActive] = useState(false);
  const fileInputRef = useRef(null);
  const replaceFileInputRef = useRef(null);

  // Preview modal state
  const [previewState, setPreviewState] = useState({
    isOpen: false,
    docId: null,
    filename: '',
    page: 1
  });

  const formatFileSize = (bytes) => {
    if (!bytes || bytes === 0) return '0 B';
    const k = 1024;
    const sizes = ['B', 'KB', 'MB', 'GB'];
    const i = Math.floor(Math.log(bytes) / Math.log(k));
    return parseFloat((bytes / Math.pow(k, i)).toFixed(1)) + ' ' + sizes[i];
  };

  const updateUploadTask = (id, patch) => {
    setUploadTasks((prev) =>
      prev.map((t) => (t.id === id ? { ...t, ...patch } : t))
    );
  };

  const removeUploadTask = (id) => {
    setUploadTasks((prev) => prev.filter((t) => t.id !== id));
  };

  const clearFinishedTasks = () => {
    setUploadTasks((prev) =>
      prev.filter((t) => t.status === 'uploading' || t.status === 'indexing')
    );
  };

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
    if (e.dataTransfer.files && e.dataTransfer.files.length > 0) {
      handleIncomingFiles(Array.from(e.dataTransfer.files));
    }
  };

  const handleFileInputChange = (e) => {
    if (e.target.files && e.target.files.length > 0) {
      handleIncomingFiles(Array.from(e.target.files));
      e.target.value = '';
    }
  };

  const handleIncomingFiles = (incomingFiles) => {
    if (!incomingFiles || incomingFiles.length === 0) return;

    incomingFiles.forEach((file) => {
      const taskId = `task_${Date.now()}_${Math.random().toString(36).substring(2, 8)}`;
      const ext = file.name.split('.').pop().toLowerCase();
      const validExts = ['pdf', 'txt', 'docx', 'doc'];

      if (!validExts.includes(ext)) {
        setUploadTasks((prev) => [
          {
            id: taskId,
            file,
            filename: file.name,
            sizeFormatted: formatFileSize(file.size),
            progress: 0,
            status: 'error',
            statusText: 'Unsupported file type (.pdf, .txt, .docx, .doc only)',
            error: 'Unsupported file type (.pdf, .txt, .docx, .doc only)',
            docData: null,
            createdAt: Date.now(),
          },
          ...prev,
        ]);
        return;
      }

      const MAX_FILE_SIZE = 25 * 1024 * 1024; // 25MB Maximum
      if (file.size > MAX_FILE_SIZE) {
        setUploadTasks((prev) => [
          {
            id: taskId,
            file,
            filename: file.name,
            sizeFormatted: formatFileSize(file.size),
            progress: 0,
            status: 'error',
            statusText: 'File exceeds 25MB maximum upload limit',
            error: 'File exceeds 25MB maximum upload limit',
            docData: null,
            createdAt: Date.now(),
          },
          ...prev,
        ]);
        return;
      }

      const newTask = {
        id: taskId,
        file,
        filename: file.name,
        sizeFormatted: formatFileSize(file.size),
        progress: 15,
        status: 'uploading',
        statusText: 'Uploading file to server...',
        error: null,
        docData: null,
        createdAt: Date.now(),
      };

      setUploadTasks((prev) => [newTask, ...prev]);

      // Launch upload execution asynchronously without blocking other uploads
      executeFileUpload(taskId, file);
    });
  };

  const executeFileUpload = async (taskId, file) => {
    const formData = new FormData();
    formData.append('file', file);

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
              updateUploadTask(taskId, {
                progress: percent,
                status: 'uploading',
                statusText: `Uploading (${percent}%)...`,
              });
            } else {
              updateUploadTask(taskId, {
                progress: 95,
                status: 'indexing',
                statusText: 'Extracting text & vectorizing in ChromaDB...',
              });
            }
          }
        },
      });

      updateUploadTask(taskId, {
        progress: 100,
        status: 'success',
        statusText: `Indexed (${response.data.chunks} chunks)`,
        docData: response.data,
      });

      // Refresh documents list dynamically
      await fetchDocuments();

      if (onSelectDoc) {
        onSelectDoc('all');
      }
    } catch (err) {
      const msg = err.response?.data?.detail || err.message || 'Failed to upload and index document.';
      updateUploadTask(taskId, {
        progress: 100,
        status: 'error',
        statusText: msg,
        error: msg,
      });
    }
  };

  const handleReplaceClick = (doc) => {
    setReplacingDoc(doc);
    if (replaceFileInputRef.current) {
      replaceFileInputRef.current.value = '';
      replaceFileInputRef.current.click();
    }
  };

  const handleReplaceFileChange = async (e) => {
    const file = e.target.files && e.target.files[0];
    if (!file || !replacingDoc) return;

    const ext = file.name.split('.').pop().toLowerCase();
    if (!['pdf', 'txt', 'docx', 'doc'].includes(ext)) {
      alert('Unsupported file type. Please upload a .pdf, .txt, .docx, or .doc file.');
      return;
    }

    const MAX_FILE_SIZE = 25 * 1024 * 1024;
    if (file.size > MAX_FILE_SIZE) {
      alert('File exceeds 25MB maximum upload limit.');
      return;
    }

    const confirmed = window.confirm(`Replace contents of "${replacingDoc.filename}" with "${file.name}"? The vector index will be updated with the new content immediately.`);
    if (!confirmed) return;

    setReplacingId(replacingDoc.doc_id);
    const formData = new FormData();
    formData.append('file', file);

    try {
      await axios.post(`${API_BASE_URL}/api/documents/${replacingDoc.doc_id}/replace`, formData, {
        headers: { 'Content-Type': 'multipart/form-data' }
      });
      await fetchDocuments();
      if (onSelectDoc) {
        onSelectDoc('all');
      }
    } catch (err) {
      alert('Failed to replace document: ' + (err.response?.data?.detail || err.message));
    } finally {
      setReplacingId(null);
      setReplacingDoc(null);
      if (replaceFileInputRef.current) {
        replaceFileInputRef.current.value = '';
      }
    }
  };

  useEffect(() => {
    if (!fileToDelete) return;
    const handleKeyDown = (e) => {
      if (e.key === 'Escape' && !isDeletingFile) {
        setFileToDelete(null);
      }
    };
    window.addEventListener('keydown', handleKeyDown);
    return () => window.removeEventListener('keydown', handleKeyDown);
  }, [fileToDelete, isDeletingFile]);

  const confirmDeleteFile = async () => {
    if (!fileToDelete) return;
    const docId = fileToDelete.doc_id;
    setIsDeletingFile(true);
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
      setFileToDelete(null);
    } catch (err) {
      alert('Failed to delete document: ' + (err.response?.data?.detail || err.message));
    } finally {
      setIsDeletingFile(false);
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
    <div className="flex-1 min-h-0 overflow-y-auto custom-scrollbar w-full p-4 sm:p-6 lg:p-8 space-y-6">
      {/* Hidden File Input for Document Replacement (Admin Only) */}
      {isAdmin && (
        <input
          ref={replaceFileInputRef}
          type="file"
          accept=".pdf,.docx,.doc,.txt"
          onChange={handleReplaceFileChange}
          className="hidden"
          disabled={replacingId !== null}
        />
      )}

      {/* Top Header & Navigation */}
      <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-4 pb-4 border-b border-slate-200">
        <div>
          <h1 className="text-xl font-bold text-slate-900 tracking-tight flex items-center space-x-2">
            <Layers className="w-5 h-5 text-indigo-600" />
            <span>{isAdmin ? 'File Upload & Management' : 'Shared Knowledge Base'}</span>
          </h1>
          <p className="text-xs text-slate-500 mt-1">
            {isAdmin
              ? 'Upload, replace, and delete shared documents for all users.'
              : 'Explore and ask questions about documents uploaded by the administrator.'}
          </p>
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

      {/* Integrated Upload Box / Multi-File Queue (Admin Only) */}
      {isAdmin && (
        <div className="bg-white rounded-2xl border border-slate-200/90 p-5 shadow-sm space-y-4">
          <div className="flex items-center justify-between">
            <div className="flex items-center space-x-2">
              <div className="w-8 h-8 rounded-lg bg-indigo-50 text-indigo-600 flex items-center justify-center">
                <UploadCloud className="w-4 h-4" />
              </div>
              <div>
                <h2 className="text-sm font-bold text-slate-900">Upload Files</h2>
                <p className="text-[11px] text-slate-500">Supports PDF, DOCX, DOC, and TXT (up to 25MB each)</p>
              </div>
            </div>

            {uploadTasks.length > 0 && (
              <div className="flex items-center space-x-2">
                {uploadTasks.some((t) => t.status === 'success' || t.status === 'error') && (
                  <button
                    onClick={clearFinishedTasks}
                    className="text-[11px] font-semibold text-slate-500 hover:text-indigo-600 px-2.5 py-1 rounded-lg hover:bg-slate-100 transition-colors"
                  >
                    Clear Finished
                  </button>
                )}
                <span className="text-[11px] font-bold px-2 py-0.5 rounded-full bg-indigo-50 text-indigo-700 border border-indigo-200">
                  {uploadTasks.length} {uploadTasks.length === 1 ? 'file' : 'files'}
                </span>
              </div>
            )}
          </div>

          {/* Hidden File Input allowing multiple selection */}
          <input
            ref={fileInputRef}
            type="file"
            multiple
            accept=".pdf,.docx,.doc,.txt"
            onChange={handleFileInputChange}
            className="hidden"
          />

          {uploadTasks.length === 0 ? (
            /* Full Width Dropzone when no tasks are queued */
            <div
              onDragEnter={handleDrag}
              onDragLeave={handleDrag}
              onDragOver={handleDrag}
              onDrop={handleDrop}
              onClick={() => fileInputRef.current?.click()}
              className={`relative border-2 border-dashed rounded-2xl p-7 sm:p-9 text-center cursor-pointer transition-all ${
                dragActive
                  ? 'border-indigo-600 bg-indigo-50/70 scale-[0.99]'
                  : 'border-slate-300 hover:border-indigo-400 hover:bg-indigo-50/20'
              }`}
            >
              <div className="flex flex-col items-center justify-center space-y-3">
                <div className={`w-12 h-12 rounded-2xl flex items-center justify-center transition-colors ${
                  dragActive ? 'bg-indigo-600 text-white' : 'bg-indigo-50 text-indigo-600'
                }`}>
                  <UploadCloud className="w-6 h-6" />
                </div>
                <div>
                  <p className="text-sm font-semibold text-slate-800">
                    {dragActive ? 'Drop your files here to upload' : 'Click to select or drag & drop documents here'}
                  </p>
                  <p className="text-xs text-slate-400 mt-1">
                    Select multiple files to upload and index concurrently without waiting
                  </p>
                </div>
                <button
                  type="button"
                  className="mt-1 px-4 py-1.5 rounded-xl text-xs font-semibold text-indigo-700 bg-indigo-50 border border-indigo-200 hover:bg-indigo-100 transition-colors pointer-events-none"
                >
                  Browse Files
                </button>
              </div>
            </div>
          ) : (
            /* Side-by-Side: Left Side Progress Bars, Right Side Add More Files Dropzone */
            <div className="grid grid-cols-1 lg:grid-cols-12 gap-4 items-stretch">
              {/* Left Side: Uploading Progress Bar List */}
              <div className="lg:col-span-6 bg-slate-50/70 rounded-2xl border border-slate-200/90 p-4 flex flex-col justify-between">
                <div>
                  <div className="flex items-center justify-between pb-2.5 mb-2.5 border-b border-slate-200/80">
                    <div className="flex items-center space-x-2">
                      {!uploadTasks.some((t) => t.status === 'uploading' || t.status === 'indexing') && (
                        <CheckCircle2 className="w-4 h-4 text-emerald-600" />
                      )}
                      <span className="text-xs font-bold text-slate-800">
                        {uploadTasks.some((t) => t.status === 'uploading' || t.status === 'indexing')
                          ? `Uploading & Indexing (${uploadTasks.filter((t) => t.status === 'uploading' || t.status === 'indexing').length} active)...`
                          : 'Uploads Completed'}
                      </span>
                    </div>
                    <span className="text-[10px] text-slate-400 font-medium">
                      Live Queue
                    </span>
                  </div>

                  <div className="space-y-3 max-h-[340px] overflow-y-auto custom-scrollbar pr-1">
                    {uploadTasks.map((task) => {
                      const ext = (task.filename || '').split('.').pop().toUpperCase();
                      const isWorking = task.status === 'uploading' || task.status === 'indexing';

                      return (
                        <div
                          key={task.id}
                          className="bg-white rounded-xl border border-slate-200/80 p-3 shadow-2xs space-y-2 hover:border-slate-300 transition-colors"
                        >
                          <div className="flex items-center justify-between gap-2">
                            <div className="flex items-center space-x-2 min-w-0">
                              <span className={`text-[9px] font-bold px-1.5 py-0.2 rounded uppercase ${
                                ext === 'PDF'
                                  ? 'bg-rose-50 text-rose-700 border border-rose-200'
                                  : ext === 'DOCX' || ext === 'DOC'
                                  ? 'bg-blue-50 text-blue-700 border border-blue-200'
                                  : 'bg-emerald-50 text-emerald-700 border border-emerald-200'
                              }`}>
                                {ext}
                              </span>
                              <span className="text-xs font-semibold text-slate-800 truncate" title={task.filename}>
                                {task.filename}
                              </span>
                              <span className="text-[10px] text-slate-400 font-mono whitespace-nowrap">
                                ({task.sizeFormatted})
                              </span>
                            </div>

                            <div className="flex items-center space-x-1.5 flex-shrink-0">
                              {task.status === 'uploading' && (
                                <span className="text-[10px] font-bold text-indigo-700 bg-indigo-50 border border-indigo-200 px-2 py-0.5 rounded-full">
                                  {task.progress}%
                                </span>
                              )}
                              {task.status === 'indexing' && (
                                <span className="text-[10px] font-bold text-amber-700 bg-amber-50 border border-amber-200 px-2 py-0.5 rounded-full animate-pulse">
                                  Indexing
                                </span>
                              )}
                              {task.status === 'success' && (
                                <span className="text-[10px] font-bold text-emerald-700 bg-emerald-50 border border-emerald-200 px-2 py-0.5 rounded-full">
                                  Done
                                </span>
                              )}
                              {task.status === 'error' && (
                                <span className="text-[10px] font-bold text-rose-700 bg-rose-50 border border-rose-200 px-2 py-0.5 rounded-full">
                                  Failed
                                </span>
                              )}

                              <button
                                onClick={() => removeUploadTask(task.id)}
                                className="p-1 rounded text-slate-400 hover:text-slate-600 hover:bg-slate-100 transition-colors"
                                title="Dismiss"
                              >
                                <X className="w-3.5 h-3.5" />
                              </button>
                            </div>
                          </div>

                          {/* Progress Bar Container */}
                          <div className="w-full bg-slate-100 rounded-full h-2 overflow-hidden">
                            <div
                              className={`h-2 rounded-full transition-all duration-300 ${
                                task.status === 'uploading'
                                  ? 'bg-gradient-to-r from-indigo-600 to-blue-500'
                                  : task.status === 'indexing'
                                  ? 'bg-gradient-to-r from-amber-500 via-indigo-500 to-blue-600 animate-pulse'
                                  : task.status === 'success'
                                  ? 'bg-emerald-500'
                                  : 'bg-rose-500'
                              }`}
                              style={{ width: `${task.progress}%` }}
                            />
                          </div>

                          {/* Status Caption */}
                          <div className="flex items-center justify-between text-[11px] pt-0.5">
                            <div className="flex items-center space-x-1.5 truncate">
                              {isWorking ? (
                                <Loader2 className={`w-3.5 h-3.5 animate-spin flex-shrink-0 ${
                                  task.status === 'indexing' ? 'text-amber-600' : 'text-indigo-600'
                                }`} />
                              ) : task.status === 'success' ? (
                                <CheckCircle2 className="w-3.5 h-3.5 text-emerald-600 flex-shrink-0" />
                              ) : (
                                <AlertCircle className="w-3.5 h-3.5 text-rose-500 flex-shrink-0" />
                              )}
                              <span className={`truncate ${
                                task.status === 'error'
                                  ? 'text-rose-700 font-medium'
                                  : task.status === 'success'
                                  ? 'text-emerald-800 font-medium'
                                  : 'text-slate-600'
                              }`}>
                                {task.statusText}
                              </span>
                            </div>

                            {task.status === 'success' && task.docData && (
                              <button
                                onClick={() => handleOpenChat(task.docData)}
                                className="inline-flex items-center space-x-1 px-2 py-0.5 rounded text-[10px] font-semibold text-emerald-800 bg-emerald-50 hover:bg-emerald-100 border border-emerald-200 transition-colors whitespace-nowrap ml-2"
                              >
                                <span>Chat</span>
                                <ArrowRight className="w-3 h-3" />
                              </button>
                            )}
                          </div>
                        </div>
                      );
                    })}
                  </div>
                </div>

                <div className="pt-2 mt-2 border-t border-slate-200/60 text-[10px] text-slate-400 flex items-center justify-between">
                  <span>Files process concurrently in the background</span>
                  <span>Max 25MB each</span>
                </div>
              </div>

              {/* Right Side: Always Active Dropzone to select MORE files anytime */}
              <div
                onDragEnter={handleDrag}
                onDragLeave={handleDrag}
                onDragOver={handleDrag}
                onDrop={handleDrop}
                onClick={() => fileInputRef.current?.click()}
                className={`lg:col-span-6 relative border-2 border-dashed rounded-2xl p-6 sm:p-8 text-center cursor-pointer transition-all flex flex-col items-center justify-center min-h-[220px] ${
                  dragActive
                    ? 'border-indigo-600 bg-indigo-50/70 scale-[0.99]'
                    : 'border-slate-300 hover:border-indigo-400 hover:bg-indigo-50/20 bg-slate-50/30'
                }`}
              >
                <div className="flex flex-col items-center justify-center space-y-3">
                  <div className={`w-12 h-12 rounded-2xl flex items-center justify-center transition-colors ${
                    dragActive ? 'bg-indigo-600 text-white' : 'bg-indigo-50 text-indigo-600'
                  }`}>
                    <UploadCloud className="w-6 h-6" />
                  </div>
                  <div>
                    <p className="text-sm font-semibold text-slate-800">
                      {dragActive ? 'Drop more files here' : 'Select or drop more files'}
                    </p>
                    <p className="text-xs text-slate-400 mt-1 max-w-xs mx-auto">
                      You can add additional documents while other files are still uploading and indexing
                    </p>
                  </div>
                  <button
                    type="button"
                    className="mt-1 px-4 py-1.5 rounded-xl text-xs font-semibold text-indigo-700 bg-indigo-50 border border-indigo-200 hover:bg-indigo-100 transition-colors pointer-events-none"
                  >
                    Browse More Files
                  </button>
                </div>
              </div>
            </div>
          )}
        </div>
      )}

      {/* Non-Admin Notice Banner */}
      {!isAdmin && (
        <div className="bg-indigo-50/60 border border-indigo-100/90 rounded-2xl p-4 sm:p-5 flex items-start space-x-3 text-xs text-indigo-950">
          <div className="w-8 h-8 rounded-xl bg-indigo-600 text-white flex items-center justify-center flex-shrink-0 mt-0.5 shadow-xs">
            <Layers className="w-4 h-4" />
          </div>
          <div>
            <h3 className="font-bold text-indigo-900 text-sm">Centralized Document Library</h3>
            <p className="text-slate-600 mt-1 leading-relaxed">
              All documents listed below have been provided and indexed by the system administrator. You can view or chat with any individual document, or ask questions across the entire knowledge base in <span className="font-semibold text-indigo-700">All files</span> chat mode.
            </p>
          </div>
        </div>
      )}

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
              {searchQuery
                ? `No files matching "${searchQuery}"`
                : isAdmin
                ? 'Upload your first document using the dropzone above.'
                : 'No documents have been uploaded by the administrator yet.'}
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
              const isReplacing = replacingId === doc.doc_id;

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
                      {isAdmin && (
                        <>
                          <button
                            onClick={() => handleReplaceClick(doc)}
                            disabled={isReplacing}
                            title="Replace document file with updated version"
                            className="p-1.5 rounded-lg text-slate-400 hover:text-indigo-600 hover:bg-indigo-50 transition-colors"
                          >
                            {isReplacing ? (
                              <Loader2 className="w-4 h-4 animate-spin text-indigo-500" />
                            ) : (
                              <RefreshCw className="w-4 h-4" />
                            )}
                          </button>
                          <button
                            onClick={() => setFileToDelete(doc)}
                            disabled={isDeleting || isDeletingFile}
                            title="Delete from shared library"
                            className="p-1.5 rounded-lg text-slate-400 hover:text-rose-600 hover:bg-rose-50 transition-colors"
                          >
                            {isDeleting ? (
                              <Loader2 className="w-4 h-4 animate-spin text-rose-500" />
                            ) : (
                              <Trash2 className="w-4 h-4" />
                            )}
                          </button>
                        </>
                      )}
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

      {/* File Deletion Confirmation Modal Dialog */}
      {fileToDelete && typeof document !== 'undefined' && createPortal(
        <div
          role="dialog"
          aria-modal="true"
          aria-labelledby="delete-file-dialog-title"
          className="fixed inset-0 z-[9999] flex items-center justify-center p-4 bg-slate-900/60 backdrop-blur-sm animate-in fade-in duration-200"
          onClick={(e) => {
            if (e.target === e.currentTarget && !isDeletingFile) setFileToDelete(null);
          }}
        >
          <div
            className="w-full max-w-md bg-white rounded-2xl border border-slate-200/90 shadow-2xl p-6 sm:p-7 relative overflow-hidden animate-in zoom-in-95 duration-200"
            onClick={(e) => e.stopPropagation()}
          >
            {/* Close Button */}
            <button
              type="button"
              onClick={() => !isDeletingFile && setFileToDelete(null)}
              disabled={isDeletingFile}
              className="absolute top-4 right-4 p-1.5 rounded-xl text-slate-400 hover:text-slate-700 hover:bg-slate-100 transition-colors cursor-pointer disabled:opacity-50"
              aria-label="Close dialog"
            >
              <X className="w-4 h-4" />
            </button>

            <div className="flex items-start space-x-4">
              <div className="w-12 h-12 rounded-2xl bg-rose-50 border border-rose-200/80 flex items-center justify-center flex-shrink-0 text-rose-600 shadow-2xs">
                <Trash2 className="w-6 h-6 text-rose-600" />
              </div>

              <div className="flex-1 min-w-0 pt-0.5">
                <h3 id="delete-file-dialog-title" className="text-base font-bold text-slate-900 tracking-tight">
                  Are you sure want to delete the file
                </h3>
                <p className="mt-1.5 text-xs text-slate-500 leading-relaxed">
                  This file will be permanently removed from the vector database. All associated chunks and chat history will be deleted.
                </p>

                {fileToDelete && (
                  <div className="mt-3.5 py-2.5 px-3 rounded-xl bg-slate-50 border border-slate-200/80 flex items-center space-x-2.5">
                    <div className="w-7 h-7 rounded-lg bg-rose-50 text-rose-700 border border-rose-200 flex items-center justify-center font-bold text-[10px] uppercase flex-shrink-0">
                      {(fileToDelete.filename || '').split('.').pop()}
                    </div>
                    <div className="min-w-0 flex-1">
                      <p className="text-xs font-semibold text-slate-800 truncate" title={fileToDelete.filename}>
                        {fileToDelete.filename}
                      </p>
                      <p className="text-[11px] text-slate-500 truncate">
                        {fileToDelete.chunks} chunks{fileToDelete.pages_count ? ` • ${fileToDelete.pages_count} pages` : ''}
                      </p>
                    </div>
                  </div>
                )}
              </div>
            </div>

            {/* Actions */}
            <div className="mt-6 flex items-center justify-end space-x-2.5 pt-4 border-t border-slate-100">
              <button
                type="button"
                onClick={() => setFileToDelete(null)}
                disabled={isDeletingFile}
                className="px-4 py-2 rounded-xl text-xs font-semibold text-slate-700 hover:text-slate-900 bg-slate-100 hover:bg-slate-200/80 transition-all cursor-pointer active:scale-95 disabled:opacity-50"
              >
                Cancel
              </button>

              <button
                type="button"
                onClick={confirmDeleteFile}
                disabled={isDeletingFile}
                className="inline-flex items-center space-x-1.5 px-4 py-2 rounded-xl text-xs font-semibold text-white bg-gradient-to-r from-rose-600 to-red-600 hover:from-rose-500 hover:to-red-500 shadow-xs shadow-rose-600/25 active:scale-95 transition-all cursor-pointer disabled:opacity-50"
              >
                {isDeletingFile ? (
                  <>
                    <Loader2 className="w-3.5 h-3.5 animate-spin" />
                    <span>Deleting...</span>
                  </>
                ) : (
                  <>
                    <Trash2 className="w-3.5 h-3.5" />
                    <span>Yes, Delete</span>
                  </>
                )}
              </button>
            </div>
          </div>
        </div>,
        document.body
      )}
    </div>
  );
}
