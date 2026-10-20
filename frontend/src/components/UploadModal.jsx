import React, { useState, useRef } from 'react';
import { UploadCloud, FileText, CheckCircle2, AlertCircle, Loader2, X, Sparkles } from 'lucide-react';
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

    const MAX_FILE_SIZE = 500 * 1024 * 1024; // 500MB
    if (file.size > MAX_FILE_SIZE) {
      setError('File size exceeds 500MB limit.');
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
      if (onUploadSuccess) {
        onUploadSuccess(data);
      }
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
    <div className="fixed inset-0 z-50 flex items-center justify-center p-4 bg-slate-900/40 backdrop-blur-sm animate-fade-in">
      <div className="relative w-full max-w-xl bg-white rounded-2xl p-6 sm:p-8 shadow-xl border border-slate-200/90 overflow-hidden text-slate-800">
        {/* Header */}
        <div className="flex items-center justify-between pb-5 border-b border-slate-200">
          <div className="flex items-center space-x-3">
            <div className="p-2.5 rounded-xl bg-indigo-50 text-indigo-600 border border-indigo-200/80">
              <UploadCloud className="w-5 h-5" />
            </div>
            <div>
              <h2 className="text-lg font-bold text-slate-900 tracking-tight">Upload & Index Document</h2>
              <p className="text-xs text-slate-500">PDF, Plain Text (.txt), or Word (.docx/.doc)</p>
            </div>
          </div>
          <button
            onClick={() => { resetModal(); onClose(); }}
            className="p-1.5 rounded-lg text-slate-400 hover:text-slate-700 hover:bg-slate-100 transition-colors"
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
                    ? 'border-indigo-500 bg-indigo-50/70 scale-[1.01]'
                    : 'border-slate-300 hover:border-indigo-400 bg-slate-50/60 hover:bg-indigo-50/30'
                }`}
              >
                <input
                  ref={fileInputRef}
                  type="file"
                  accept=".pdf,.txt,.docx,.doc,application/pdf,text/plain,application/vnd.openxmlformats-officedocument.wordprocessingml.document,application/msword"
                  className="hidden"
                  onChange={handleFileChange}
                />

                <div className="w-14 h-14 rounded-full bg-white border border-slate-200 flex items-center justify-center mb-3 shadow-xs">
                  <FileText className={`w-7 h-7 ${dragActive ? 'text-indigo-600' : 'text-slate-400'}`} />
                </div>

                <p className="text-sm font-semibold text-slate-800 text-center">
                  Drag and drop your document here, or <span className="text-indigo-600 font-bold underline decoration-indigo-300">browse</span>
                </p>
                <p className="text-xs text-slate-500 mt-1">Supports PDF, Text (.txt), and Word (.docx/.doc) up to 500MB</p>

                {selectedFile && (
                  <div className="mt-4 px-3.5 py-2 rounded-lg bg-indigo-50 border border-indigo-200 flex items-center space-x-2 text-xs text-indigo-900 shadow-2xs">
                    <FileText className="w-4 h-4 text-indigo-600" />
                    <span className="font-semibold truncate max-w-[280px]">{selectedFile.name}</span>
                    <span className="text-slate-500">({(selectedFile.size / 1024).toFixed(1)} KB)</span>
                  </div>
                )}
              </div>

              {/* Error Banner */}
              {error && (
                <div className="p-3.5 rounded-xl bg-rose-50 border border-rose-200 flex items-start space-x-2.5 text-xs text-rose-700">
                  <AlertCircle className="w-4 h-4 text-rose-500 flex-shrink-0 mt-0.5" />
                  <span>{error}</span>
                </div>
              )}

              {/* Progress State */}
              {uploading && (
                <div className="p-4 rounded-xl bg-indigo-50/70 border border-indigo-200 space-y-2">
                  <div className="flex items-center space-x-2.5 text-xs text-indigo-900 font-semibold">
                    <Loader2 className="w-4 h-4 animate-spin text-indigo-600" />
                    <span>{uploadStep}</span>
                  </div>
                  <div className="w-full bg-indigo-100 h-1.5 rounded-full overflow-hidden">
                    <div className="bg-gradient-to-r from-indigo-600 to-blue-600 h-full w-2/3 animate-pulse rounded-full" />
                  </div>
                </div>
              )}

              {/* Action Buttons */}
              <div className="flex items-center justify-end space-x-3 pt-2">
                <button
                  type="button"
                  onClick={() => { resetModal(); onClose(); }}
                  disabled={uploading}
                  className="px-4 py-2 text-xs font-semibold text-slate-500 hover:text-slate-800 transition-colors"
                >
                  Cancel
                </button>
                <button
                  type="button"
                  onClick={handleSubmit}
                  disabled={!selectedFile || uploading}
                  className="flex items-center space-x-2 px-5 py-2.5 rounded-xl text-xs font-semibold text-white bg-gradient-to-r from-indigo-600 via-indigo-600 to-blue-600 hover:from-indigo-500 hover:to-blue-500 disabled:opacity-50 disabled:cursor-not-allowed shadow-xs transition-all active:scale-95"
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
              <div className="p-5 rounded-2xl bg-emerald-50 border border-emerald-200 text-center space-y-2">
                <div className="w-12 h-12 rounded-full bg-emerald-100 text-emerald-600 flex items-center justify-center mx-auto shadow-2xs">
                  <CheckCircle2 className="w-6 h-6" />
                </div>
                <h3 className="text-base font-bold text-slate-900">Document Successfully Indexed!</h3>
                <p className="text-xs text-slate-600">
                  Embeddings have been saved into ChromaDB local persistent vector store.
                </p>
              </div>

              {/* Metadata Details */}
              <div className="bg-slate-50 rounded-xl p-4 border border-slate-200 space-y-2.5 text-xs">
                <div className="flex justify-between items-center py-1 border-b border-slate-200">
                  <span className="text-slate-500">Filename:</span>
                  <span className="font-semibold text-slate-800">{result.filename}</span>
                </div>
                <div className="flex justify-between items-center py-1">
                  <span className="text-slate-500">Total Chunks Created:</span>
                  <span className="font-mono font-bold text-indigo-600">{result.chunks} chunks</span>
                </div>
              </div>

              <div className="flex items-center justify-end space-x-3 pt-2">
                <button
                  onClick={() => { resetModal(); }}
                  className="px-4 py-2 text-xs font-semibold text-slate-600 hover:text-slate-900"
                >
                  Upload Another
                </button>
                <button
                  onClick={() => { onClose(); }}
                  className="px-5 py-2.5 rounded-xl text-xs font-semibold text-white bg-indigo-600 hover:bg-indigo-500 shadow-xs transition-all"
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
