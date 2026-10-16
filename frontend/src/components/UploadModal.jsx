import React, { useState, useRef } from 'react';
import { UploadCloud, FileText, CheckCircle2, AlertCircle, Loader2, X, Sparkles, Layers, Cpu } from 'lucide-react';
import { uploadDocument } from '../api';

export default function UploadModal({ isOpen, onClose, onUploadSuccess }) {
  const [dragActive, setDragActive] = useState(false);
  const [selectedFile, setSelectedFile] = useState(null);
  const [uploading, setUploading] = useState(false);
  const [uploadStep, setUploadStep] = useState('');
  const [error, setError] = useState(null);
  const [result, setResult] = useState(null);
  const fileInputRef = useRef(null);

  if (!isOpen) return null;

  const handleDrag = (e) => {
    e.preventDefault();
    e.stopPropagation();
    if (e.type === 'dragenter' || e.type === 'dragover') {
      setDragActive(true);
    } else if (e.type === 'dragleave') {
      setDragActive(false);
    }
  };

  const validateAndSetFile = (file) => {
    setError(null);
    setResult(null);
    if (!file) return;

    const ext = file.name.split('.').pop().toLowerCase();
    if (!['pdf', 'txt', 'docx', 'doc'].includes(ext)) {
      setError('Only .pdf, .txt, .docx, and .doc files are supported.');
      return;
    }

    if (file.size > 25 * 1024 * 1024) {
      setError('File size exceeds 25MB limit.');
      return;
    }

    setSelectedFile(file);
  };

  const handleDrop = (e) => {
    e.preventDefault();
    e.stopPropagation();
    setDragActive(false);
    if (e.dataTransfer.files && e.dataTransfer.files[0]) {
      validateAndSetFile(e.dataTransfer.files[0]);
    }
  };

  const handleFileChange = (e) => {
    if (e.target.files && e.target.files[0]) {
      validateAndSetFile(e.target.files[0]);
    }
  };

  const handleSubmit = async () => {
    if (!selectedFile) return;

    setUploading(true);
    setError(null);
    setResult(null);
    setUploadStep('Extracting text & page metadata with PyMuPDF...');

    try {
      setTimeout(() => {
        setUploadStep('Chunking document & generating vector embeddings...');
      }, 700);

      const data = await uploadDocument(selectedFile);
      setResult(data);
      setUploadStep('');
      onUploadSuccess(data);
    } catch (err) {
      setError(err.message || 'Failed to parse and index document.');
    } finally {
      setUploading(false);
    }
  };

  const resetModal = () => {
    setSelectedFile(null);
    setError(null);
    setResult(null);
    setUploading(false);
  };

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center p-4 bg-black/75 backdrop-blur-sm animate-fade-in">
      <div className="relative w-full max-w-xl glass-card rounded-2xl p-6 sm:p-8 shadow-2xl border border-slate-700/60 overflow-hidden">
        {/* Glow Accent */}
        <div className="absolute -top-20 -left-20 w-44 h-44 bg-brand-500/20 rounded-full blur-3xl pointer-events-none" />
        <div className="absolute -bottom-20 -right-20 w-44 h-44 bg-indigo-500/20 rounded-full blur-3xl pointer-events-none" />

        {/* Header */}
        <div className="flex items-center justify-between pb-5 border-b border-slate-800">
          <div className="flex items-center space-x-3">
            <div className="p-2.5 rounded-xl bg-brand-500/10 text-brand-400 border border-brand-500/20">
              <UploadCloud className="w-5 h-5" />
            </div>
            <div>
              <h2 className="text-lg font-bold text-white tracking-tight">Upload & Index Document</h2>
              <p className="text-xs text-slate-400">PDF, Plain Text (.txt), or Word (.docx/.doc)</p>
            </div>
          </div>
          <button
            onClick={() => { resetModal(); onClose(); }}
            className="p-1.5 rounded-lg text-slate-400 hover:text-white hover:bg-slate-800 transition-colors"
          >
            <X className="w-5 h-5" />
          </button>
        </div>

        {/* Content */}
        <div className="mt-6 space-y-4">
          {!result ? (
            <>
              {/* Drop Zone */}
              <div
                onDragEnter={handleDrag}
                onDragLeave={handleDrag}
                onDragOver={handleDrag}
                onDrop={handleDrop}
                onClick={() => fileInputRef.current?.click()}
                className={`relative flex flex-col items-center justify-center p-8 rounded-xl border-2 border-dashed cursor-pointer transition-all ${
                  dragActive
                    ? 'border-brand-400 bg-brand-500/10 scale-[1.01]'
                    : 'border-slate-700 hover:border-slate-500 bg-slate-900/40 hover:bg-slate-900/70'
                }`}
              >
                <input
                  ref={fileInputRef}
                  type="file"
                  accept=".pdf,.txt,.docx,.doc,application/pdf,text/plain,application/vnd.openxmlformats-officedocument.wordprocessingml.document,application/msword"
                  className="hidden"
                  onChange={handleFileChange}
                />

                <div className="w-14 h-14 rounded-full bg-slate-800/80 flex items-center justify-center mb-3 shadow-inner">
                  <FileText className={`w-7 h-7 ${dragActive ? 'text-brand-400' : 'text-slate-400'}`} />
                </div>

                <p className="text-sm font-semibold text-slate-200 text-center">
                  Drag and drop your document here, or <span className="text-brand-400 underline decoration-brand-500/40">browse</span>
                </p>
                <p className="text-xs text-slate-500 mt-1">Supports PDF, Text (.txt), and Word (.docx/.doc) up to 25MB</p>

                {selectedFile && (
                  <div className="mt-4 px-3.5 py-2 rounded-lg bg-brand-500/10 border border-brand-500/30 flex items-center space-x-2 text-xs text-brand-300">
                    <FileText className="w-4 h-4 text-brand-400" />
                    <span className="font-medium truncate max-w-[280px]">{selectedFile.name}</span>
                    <span className="text-slate-400">({(selectedFile.size / 1024).toFixed(1)} KB)</span>
                  </div>
                )}
              </div>

              {/* Error Banner */}
              {error && (
                <div className="p-3.5 rounded-xl bg-rose-500/10 border border-rose-500/30 flex items-start space-x-2.5 text-xs text-rose-300">
                  <AlertCircle className="w-4 h-4 text-rose-400 flex-shrink-0 mt-0.5" />
                  <span>{error}</span>
                </div>
              )}

              {/* Progress State */}
              {uploading && (
                <div className="p-4 rounded-xl bg-slate-900/90 border border-slate-800 space-y-2">
                  <div className="flex items-center space-x-2.5 text-xs text-brand-300 font-medium">
                    <Loader2 className="w-4 h-4 animate-spin text-brand-400" />
                    <span>{uploadStep}</span>
                  </div>
                  <div className="w-full bg-slate-800 h-1.5 rounded-full overflow-hidden">
                    <div className="bg-gradient-to-r from-brand-500 to-indigo-500 h-full w-2/3 animate-pulse" />
                  </div>
                </div>
              )}

              {/* Action Buttons */}
              <div className="flex items-center justify-end space-x-3 pt-2">
                <button
                  type="button"
                  onClick={() => { resetModal(); onClose(); }}
                  disabled={uploading}
                  className="px-4 py-2 text-xs font-medium text-slate-400 hover:text-white transition-colors"
                >
                  Cancel
                </button>
                <button
                  type="button"
                  onClick={handleSubmit}
                  disabled={!selectedFile || uploading}
                  className="flex items-center space-x-2 px-5 py-2.5 rounded-xl text-xs font-semibold text-white bg-gradient-to-r from-brand-600 via-indigo-600 to-brand-500 hover:opacity-95 disabled:opacity-50 disabled:cursor-not-allowed shadow-lg shadow-brand-500/25 transition-all"
                >
                  {uploading ? (
                    <>
                      <Loader2 className="w-3.5 h-3.5 animate-spin" />
                      <span>Indexing in ChromaDB...</span>
                    </>
                  ) : (
                    <>
                      <Sparkles className="w-3.5 h-3.5" />
                      <span>Upload & Index Document</span>
                    </>
                  )}
                </button>
              </div>
            </>
          ) : (
            /* Success Card */
            <div className="space-y-5 py-2 animate-slide-up">
              <div className="p-5 rounded-2xl bg-emerald-500/10 border border-emerald-500/20 text-center space-y-2">
                <div className="w-12 h-12 rounded-full bg-emerald-500/20 text-emerald-400 flex items-center justify-center mx-auto">
                  <CheckCircle2 className="w-6 h-6" />
                </div>
                <h3 className="text-base font-bold text-white">Document Successfully Indexed!</h3>
                <p className="text-xs text-slate-300">
                  Embeddings have been saved into ChromaDB local persistent vector store.
                </p>
              </div>

              {/* Metadata Details */}
              <div className="bg-slate-900/80 rounded-xl p-4 border border-slate-800 space-y-2.5 text-xs">
                <div className="flex justify-between items-center py-1 border-b border-slate-800/60">
                  <span className="text-slate-400">Filename:</span>
                  <span className="font-semibold text-slate-200">{result.filename}</span>
                </div>
                <div className="flex justify-between items-center py-1">
                  <span className="text-slate-400">Total Chunks Created:</span>
                  <span className="font-mono font-semibold text-brand-400">{result.chunks} chunks</span>
                </div>
              </div>

              <div className="flex items-center justify-end space-x-3 pt-2">
                <button
                  onClick={() => { resetModal(); }}
                  className="px-4 py-2 text-xs font-medium text-slate-400 hover:text-white"
                >
                  Upload Another
                </button>
                <button
                  onClick={() => { onClose(); }}
                  className="px-5 py-2.5 rounded-xl text-xs font-semibold text-white bg-brand-600 hover:bg-brand-500 shadow-md shadow-brand-500/20 transition-all"
                >
                  Start Asking Questions
                </button>
              </div>
            </div>
          )}
        </div>
      </div>
    </div>
  );
}
