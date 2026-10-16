import React from 'react';
import { FileText, Trash2, Check, Clock, Plus, Layers, Database } from 'lucide-react';

export default function DocumentSidebar({
  documents,
  activeDocId,
  onSelectDoc,
  onDeleteDoc,
  onOpenUpload,
  loading
}) {
  return (
    <aside className="w-full lg:w-80 flex flex-col glass-card rounded-2xl border border-slate-800/80 p-4 h-[calc(100vh-6.5rem)] sticky top-20 overflow-hidden">
      {/* Header */}
      <div className="flex items-center justify-between pb-3.5 border-b border-slate-800/80">
        <div className="flex items-center space-x-2">
          <Database className="w-4 h-4 text-brand-400" />
          <h2 className="text-sm font-bold text-slate-100 tracking-tight">Indexed Documents</h2>
        </div>
        <span className="text-[11px] font-semibold px-2 py-0.5 rounded-full bg-slate-800 text-slate-300">
          {documents.length}
        </span>
      </div>

      {/* New Document Button */}
      <div className="pt-3 pb-2">
        <button
          onClick={onOpenUpload}
          className="w-full flex items-center justify-center space-x-2 px-3 py-2 rounded-xl text-xs font-semibold text-white bg-slate-800 hover:bg-slate-700/80 border border-slate-700/70 hover:border-brand-500/40 transition-all shadow-sm"
        >
          <Plus className="w-3.5 h-3.5 text-brand-400" />
          <span>Upload New File</span>
        </button>
      </div>

      {/* Documents List */}
      <div className="flex-1 overflow-y-auto space-y-2 pr-1 mt-2">
        {loading ? (
          <div className="flex items-center justify-center py-12 text-xs text-slate-500">
            <span>Loading documents...</span>
          </div>
        ) : documents.length === 0 ? (
          <div className="flex flex-col items-center justify-center py-12 px-4 text-center">
            <div className="w-12 h-12 rounded-xl bg-slate-900 border border-slate-800 flex items-center justify-center text-slate-600 mb-3">
              <FileText className="w-6 h-6" />
            </div>
            <p className="text-xs font-medium text-slate-300">No documents yet</p>
            <p className="text-[11px] text-slate-500 mt-1">Upload a PDF,TXT or Doc files to begin asking questions.</p>
          </div>
        ) : (
          documents.map((doc) => {
            const isActive = doc.doc_id === activeDocId;
            const ext = doc.filename.split('.').pop().toUpperCase();

            return (
              <div
                key={doc.doc_id}
                onClick={() => onSelectDoc(doc.doc_id)}
                className={`group relative p-3 rounded-xl border text-left cursor-pointer transition-all ${isActive
                  ? 'bg-brand-500/10 border-brand-500/40 shadow-sm shadow-brand-500/10'
                  : 'bg-slate-900/50 hover:bg-slate-900/90 border-slate-800/80 hover:border-slate-700'
                  }`}
              >
                <div className="flex items-start justify-between gap-2">
                  <div className="flex items-start space-x-2.5 overflow-hidden">
                    <span className={`text-[10px] font-bold px-1.5 py-0.5 rounded uppercase mt-0.5 ${ext === 'PDF' ? 'bg-red-500/10 text-red-400 border border-red-500/20' : 'bg-blue-500/10 text-blue-400 border border-blue-500/20'
                      }`}>
                      {ext}
                    </span>
                    <div className="overflow-hidden">
                      <p className={`text-xs font-semibold truncate ${isActive ? 'text-white' : 'text-slate-300'}`}>
                        {doc.filename}
                      </p>
                      <div className="flex items-center space-x-2 mt-1 text-[11px] text-slate-400">
                        <span className="flex items-center space-x-1">
                          <Layers className="w-3 h-3 text-slate-500" />
                          <span className="font-mono text-brand-300">{doc.chunks} chunks</span>
                        </span>
                        {doc.pages_count && (
                          <>
                            <span className="text-slate-600">•</span>
                            <span>{doc.pages_count}p</span>
                          </>
                        )}
                      </div>
                    </div>
                  </div>

                  {/* Actions */}
                  <div className="flex items-center space-x-1">
                    {isActive && (
                      <span className="w-2 h-2 rounded-full bg-brand-400 animate-pulse" title="Active document" />
                    )}
                    <button
                      type="button"
                      onClick={(e) => {
                        e.stopPropagation();
                        onDeleteDoc(doc.doc_id, doc.filename);
                      }}
                      className="opacity-0 group-hover:opacity-100 p-1 text-slate-500 hover:text-rose-400 rounded hover:bg-slate-800 transition-all"
                      title="Delete from vector database"
                    >
                      <Trash2 className="w-3.5 h-3.5" />
                    </button>
                  </div>
                </div>
              </div>
            );
          })
        )}
      </div>

      {/* Persistence Footer */}
      <div className="pt-3 border-t border-slate-800/80 text-[11px] text-slate-500 flex items-center justify-between">
        <span>Store: <code className="text-slate-400">/backend/vector_db</code></span>
        <span className="inline-block w-1.5 h-1.5 rounded-full bg-emerald-400" />
      </div>
    </aside>
  );
}
