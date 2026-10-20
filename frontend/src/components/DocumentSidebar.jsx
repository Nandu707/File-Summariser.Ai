import React from 'react';
import { FileText, Trash2, Plus, Layers, Database } from 'lucide-react';

export default function DocumentSidebar({
  documents,
  activeDocId,
  onSelectDoc,
  onDeleteDoc,
  onOpenUpload,
  loading
}) {
  return (
    <aside className="w-full lg:w-80 flex flex-col bg-white rounded-2xl border border-slate-200/90 shadow-sm p-4 h-[calc(100vh-6.5rem)] sticky top-20 overflow-hidden">
      {/* Header */}
      <div className="flex items-center justify-between pb-3.5 border-b border-slate-200">
        <div className="flex items-center space-x-2">
          <Database className="w-4 h-4 text-indigo-600" />
          <h2 className="text-sm font-bold text-slate-900 tracking-tight">Indexed Documents</h2>
        </div>
        <span className="text-[11px] font-semibold px-2 py-0.5 rounded-full bg-slate-100 text-slate-700 border border-slate-200">
          {documents.length}
        </span>
      </div>

      {/* New Document Button */}
      <div className="pt-3 pb-2">
        <button
          onClick={onOpenUpload}
          className="w-full flex items-center justify-center space-x-2 px-3 py-2 rounded-xl text-xs font-semibold text-white bg-indigo-600 hover:bg-indigo-500 shadow-xs transition-all"
        >
          <Plus className="w-3.5 h-3.5" />
          <span>Upload New File</span>
        </button>
      </div>

      {/* Documents List */}
      <div className="flex-1 overflow-y-auto custom-scrollbar space-y-2 pr-1 mt-2">
        {loading ? (
          <div className="flex items-center justify-center py-12 text-xs text-slate-400 font-medium">
            <span>Loading documents...</span>
          </div>
        ) : documents.length === 0 ? (
          <div className="flex flex-col items-center justify-center py-12 px-4 text-center">
            <div className="w-12 h-12 rounded-xl bg-slate-100 border border-slate-200 flex items-center justify-center text-slate-400 mb-3">
              <FileText className="w-6 h-6" />
            </div>
            <p className="text-xs font-semibold text-slate-700">No documents yet</p>
            <p className="text-[11px] text-slate-400 mt-1">Upload a PDF, TXT or DOCX file to begin.</p>
          </div>
        ) : (
          documents.map((doc) => {
            const isActive = doc.doc_id === activeDocId;
            const ext = doc.filename.split('.').pop().toUpperCase();

            return (
              <div
                key={doc.doc_id}
                onClick={() => onSelectDoc(doc.doc_id)}
                className={`group relative p-3 rounded-xl border text-left cursor-pointer transition-all ${
                  isActive
                    ? 'bg-indigo-50/80 border-indigo-300 shadow-2xs'
                    : 'bg-white hover:bg-slate-50 border-slate-200 text-slate-700 hover:text-slate-900 shadow-2xs'
                }`}
              >
                <div className="flex items-start justify-between gap-2">
                  <div className="flex items-start space-x-2.5 overflow-hidden">
                    <span className={`text-[10px] font-bold px-1.5 py-0.5 rounded uppercase mt-0.5 ${
                      ext === 'PDF'
                        ? 'bg-rose-50 text-rose-700 border border-rose-200'
                        : ext === 'DOCX' || ext === 'DOC'
                        ? 'bg-blue-50 text-blue-700 border border-blue-200'
                        : 'bg-emerald-50 text-emerald-700 border border-emerald-200'
                    }`}>
                      {ext}
                    </span>
                    <div className="overflow-hidden">
                      <p className={`text-xs font-semibold truncate ${isActive ? 'text-indigo-950' : 'text-slate-800'}`}>
                        {doc.filename}
                      </p>
                      <div className="flex items-center space-x-2 mt-1 text-[11px] text-slate-400">
                        <span className="flex items-center space-x-1">
                          <Layers className="w-3 h-3 text-slate-400" />
                          <span className="font-mono text-indigo-600 font-medium">{doc.chunks} chunks</span>
                        </span>
                        {doc.pages_count && (
                          <>
                            <span className="text-slate-300">•</span>
                            <span>{doc.pages_count}p</span>
                          </>
                        )}
                      </div>
                    </div>
                  </div>

                  {/* Actions */}
                  <div className="flex items-center space-x-1">
                    {isActive && (
                      <span className="w-2 h-2 rounded-full bg-indigo-600 animate-pulse" title="Active document" />
                    )}
                    <button
                      type="button"
                      onClick={(e) => {
                        e.stopPropagation();
                        onDeleteDoc(doc.doc_id, doc.filename);
                      }}
                      className="opacity-0 group-hover:opacity-100 p-1 text-slate-400 hover:text-rose-600 rounded hover:bg-rose-50 transition-all"
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
    </aside>
  );
}
