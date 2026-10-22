import React, { useState, useMemo, useRef, useEffect } from 'react';
import { createPortal } from 'react-dom';
import {
  MessageSquare,
  Plus,
  Search,
  MoreVertical,
  Edit2,
  Trash2,
  FileText,
  Globe,
  AlertTriangle,
  ChevronDown,
  X,
  Clock,
  Sparkles,
  PanelLeftClose
} from 'lucide-react';

/**
 * Categorizes an ISO timestamp into chronological time buckets:
 * Today, Yesterday, Previous 7 days, Previous 30 days, or Month Year.
 */
function getTimeGroup(dateStr) {
  if (!dateStr) return 'Older';
  const date = new Date(dateStr);
  const now = new Date();

  const startOfToday = new Date(now.getFullYear(), now.getMonth(), now.getDate());
  const startOfYesterday = new Date(startOfToday);
  startOfYesterday.setDate(startOfYesterday.getDate() - 1);

  const startOf7Days = new Date(startOfToday);
  startOf7Days.setDate(startOf7Days.getDate() - 7);

  const startOf30Days = new Date(startOfToday);
  startOf30Days.setDate(startOf30Days.getDate() - 30);

  if (date >= startOfToday) {
    return 'Today';
  } else if (date >= startOfYesterday) {
    return 'Yesterday';
  } else if (date >= startOf7Days) {
    return 'Previous 7 days';
  } else if (date >= startOf30Days) {
    return 'Previous 30 days';
  } else {
    return date.toLocaleDateString('en-US', { month: 'long', year: 'numeric' });
  }
}

export default function DocumentSidebar({
  sessions = [],
  activeSessionId = 'all',
  documents = [],
  onSelectSession,
  onCreateSession,
  onRenameSession,
  onDeleteSession,
  onOpenUpload,
  searchQuery = '',
  onSearchChange,
  loading = false,
  onToggleCollapse
}) {
  const [showNewChatMenu, setShowNewChatMenu] = useState(false);
  const [menuOpenId, setMenuOpenId] = useState(null);
  const [editingId, setEditingId] = useState(null);
  const [editTitle, setEditTitle] = useState('');
  const [sessionToDelete, setSessionToDelete] = useState(null);
  const menuRef = useRef(null);
  const newChatRef = useRef(null);

  // Close delete modal on Escape key
  useEffect(() => {
    if (!sessionToDelete) return;
    const handleKeyDown = (e) => {
      if (e.key === 'Escape') setSessionToDelete(null);
    };
    window.addEventListener('keydown', handleKeyDown);
    return () => window.removeEventListener('keydown', handleKeyDown);
  }, [sessionToDelete]);

  // Close menus on outside click
  useEffect(() => {
    const handleClickOutside = (e) => {
      if (menuRef.current && !menuRef.current.contains(e.target)) {
        setMenuOpenId(null);
      }
      if (newChatRef.current && !newChatRef.current.contains(e.target)) {
        setShowNewChatMenu(false);
      }
    };
    document.addEventListener('click', handleClickOutside);
    return () => document.removeEventListener('click', handleClickOutside);
  }, []);

  // Filter sessions: only show sessions that have started (have messages)
  const filteredSessions = useMemo(() => {
    const historyOnly = sessions.filter(
      (s) => (s.message_count || 0) > 0
    );
    if (!searchQuery.trim()) return historyOnly;
    const q = searchQuery.toLowerCase().trim();
    return historyOnly.filter(
      (s) =>
        (s.title && s.title.toLowerCase().includes(q)) ||
        (s.file_name && s.file_name.toLowerCase().includes(q))
    );
  }, [sessions, searchQuery]);

  // Group sessions by time with headers
  const groupedSessions = useMemo(() => {
    const groups = [];
    const groupMap = new Map();

    const order = ['Today', 'Yesterday', 'Previous 7 days', 'Previous 30 days'];

    for (const session of filteredSessions) {
      const g = getTimeGroup(session.updated_at || session.created_at);
      if (!groupMap.has(g)) {
        groupMap.set(g, []);
      }
      groupMap.get(g).push(session);
    }

    // Preserve standard chronological order for fixed buckets, then chronological for months
    for (const ord of order) {
      if (groupMap.has(ord)) {
        groups.push({ title: ord, items: groupMap.get(ord) });
        groupMap.delete(ord);
      }
    }

    for (const [title, items] of groupMap.entries()) {
      groups.push({ title, items });
    }

    return groups;
  }, [filteredSessions]);

  const handleStartRename = (e, session) => {
    e.stopPropagation();
    setEditingId(session.id);
    setEditTitle(session.title || '');
    setMenuOpenId(null);
  };

  const handleSaveRename = (sessionId) => {
    if (editTitle.trim() && onRenameSession) {
      onRenameSession(sessionId, editTitle.trim());
    }
    setEditingId(null);
  };

  const handleDeleteClick = (e, session) => {
    e.stopPropagation();
    setMenuOpenId(null);
    setSessionToDelete(session);
  };

  const handleConfirmDelete = () => {
    if (sessionToDelete && onDeleteSession) {
      onDeleteSession(sessionToDelete.id);
    }
    setSessionToDelete(null);
  };

  const handleCreateScope = (scope, doc = null) => {
    setShowNewChatMenu(false);
    // If active session is already empty and matches this scope, just stay in it
    const active = sessions.find((s) => s.id === activeSessionId);
    if (active && (!active.message_count || active.message_count === 0) && active.scope === scope) {
      if (scope === 'all' || (doc && active.file_id === doc.doc_id)) {
        return;
      }
    }
    if (onCreateSession) {
      if (scope === 'all') {
        onCreateSession({ scope: 'all', title: 'New chat' });
      } else if (doc) {
        onCreateSession({
          scope: 'file',
          file_id: doc.doc_id,
          file_name: doc.filename,
          title: `Chat: ${doc.filename}`
        });
      }
    }
  };

  return (
    <aside className="w-full h-full flex flex-col bg-white rounded-2xl border border-slate-200/90 shadow-sm p-3.5 sm:p-4 overflow-hidden flex-shrink-0 select-none">
      {/* Sidebar Header & New Chat Button */}
      <div className="pb-3 border-b border-slate-200/80 space-y-2.5">
        <div className="flex items-center justify-between">
          <div className="flex items-center space-x-2">
            <div className="w-7 h-7 rounded-lg bg-indigo-50 text-indigo-600 flex items-center justify-center border border-indigo-200/80 flex-shrink-0">
              <MessageSquare className="w-3.5 h-3.5" />
            </div>
            <div className="min-w-0">
              <h2 className="text-xs font-bold text-slate-900 tracking-tight truncate">Chats</h2>
              <p className="text-[10px] text-slate-500 truncate">Conversation history</p>
            </div>
          </div>
          <div className="flex items-center space-x-1.5 flex-shrink-0">
            <span className="text-[10px] font-semibold px-2 py-0.5 rounded-full bg-slate-100 text-slate-700 border border-slate-200">
              {filteredSessions.length} {filteredSessions.length === 1 ? 'chat' : 'chats'}
            </span>
            {onToggleCollapse && (
              <button
                type="button"
                onClick={onToggleCollapse}
                className="p-1 rounded-lg text-slate-400 hover:text-slate-700 hover:bg-slate-100 transition-colors cursor-pointer"
                title="Collapse history sidebar"
              >
                <PanelLeftClose className="w-4 h-4" />
              </button>
            )}
          </div>
        </div>

        {/* 'New chat' button with Scope Selector */}
        <div className="relative" ref={newChatRef}>
          <button
            onClick={() => setShowNewChatMenu((prev) => !prev)}
            className="w-full flex items-center justify-between px-3 py-2 rounded-xl text-xs font-semibold text-white bg-gradient-to-r from-indigo-600 via-indigo-600 to-blue-600 hover:from-indigo-500 hover:to-blue-500 shadow-sm shadow-indigo-600/20 active:scale-98 transition-all cursor-pointer"
          >
            <div className="flex items-center space-x-2">
              <Plus className="w-4 h-4 text-white" />
              <span>New chat</span>
            </div>
            <ChevronDown className="w-3.5 h-3.5 text-indigo-200" />
          </button>

          {/* New Chat Scope Dropdown */}
          {showNewChatMenu && (
            <div className="absolute top-full left-0 right-0 mt-1.5 bg-white border border-slate-200 rounded-xl shadow-lg z-50 p-1.5 space-y-1 animate-in fade-in slide-in-from-top-1 duration-150">
              <button
                type="button"
                onClick={() => handleCreateScope('all')}
                className="w-full flex items-center space-x-2 px-2.5 py-2 rounded-lg text-xs font-semibold text-slate-700 hover:text-indigo-900 hover:bg-indigo-50/80 transition-colors text-left cursor-pointer"
              >
                <div className="p-1 rounded bg-indigo-50 text-indigo-600">
                  <Globe className="w-3.5 h-3.5" />
                </div>
                <div>
                  <p className="font-semibold text-slate-800">All files</p>
                  <p className="text-[10px] text-slate-400 font-normal">Search across all active files</p>
                </div>
              </button>

              {documents.length > 0 && (
                <div className="pt-1 border-t border-slate-100">
                  <p className="text-[10px] font-bold uppercase tracking-wider text-slate-400 px-2 py-1">
                    Specific File
                  </p>
                  <div className="max-h-48 overflow-y-auto custom-scrollbar space-y-0.5">
                    {documents.map((doc) => (
                      <button
                        key={doc.doc_id}
                        type="button"
                        onClick={() => handleCreateScope('file', doc)}
                        className="w-full flex items-center space-x-2 px-2.5 py-1.5 rounded-lg text-xs text-slate-700 hover:text-indigo-900 hover:bg-indigo-50/80 transition-colors text-left cursor-pointer"
                      >
                        <FileText className="w-3.5 h-3.5 text-slate-400 flex-shrink-0" />
                        <span className="truncate">{doc.filename}</span>
                      </button>
                    ))}
                  </div>
                </div>
              )}
            </div>
          )}
        </div>

        {/* Search Box */}
        <div className="relative">
          <Search className="w-3.5 h-3.5 text-slate-400 absolute left-2.5 top-1/2 -translate-y-1/2 pointer-events-none" />
          <input
            type="text"
            value={searchQuery}
            onChange={(e) => onSearchChange && onSearchChange(e.target.value)}
            placeholder="Search chats..."
            className="w-full bg-slate-50 hover:bg-slate-100/80 focus:bg-white border border-slate-200 focus:border-indigo-400 rounded-xl pl-8 pr-7 py-1.5 text-xs text-slate-800 placeholder-slate-400 focus:outline-none transition-colors"
          />
          {searchQuery && (
            <button
              onClick={() => onSearchChange && onSearchChange('')}
              className="absolute right-2 top-1/2 -translate-y-1/2 text-slate-400 hover:text-slate-600"
            >
              <X className="w-3 h-3" />
            </button>
          )}
        </div>
      </div>

      {/* Unified Chat List Grouped by Time */}
      <div className="flex-1 min-h-0 overflow-y-auto custom-scrollbar space-y-4 pr-1 mt-2.5">
        {groupedSessions.length === 0 ? (
          <div className="text-center py-8 text-xs text-slate-400 space-y-2">
            <MessageSquare className="w-6 h-6 mx-auto text-slate-300" />
            <p>{searchQuery ? 'No matching chats found' : 'No chats yet. Start a new chat!'}</p>
          </div>
        ) : (
          groupedSessions.map((group) => (
            <div key={group.title} className="space-y-1">
              {/* Time Section Header */}
              <p className="text-[10px] font-bold uppercase tracking-wider text-slate-400 px-2 py-0.5 sticky top-0 bg-white/95 backdrop-blur-xs z-10">
                {group.title}
              </p>

              {/* Chat Session Rows */}
              <div className="space-y-1">
                {group.items.map((session) => {
                  const isActive = session.id === activeSessionId;
                  const isDeleted = Boolean(session.is_file_deleted);
                  const isEditing = editingId === session.id;

                  return (
                    <div
                      key={session.id}
                      onClick={() => !isEditing && onSelectSession(session.id)}
                      className={`group relative p-2 sm:p-2.5 rounded-xl border text-left cursor-pointer transition-all ${
                        isActive
                          ? isDeleted
                            ? 'bg-rose-50/70 border-rose-300 shadow-2xs font-semibold text-rose-950'
                            : 'bg-gradient-to-r from-indigo-50 to-blue-50/60 border-indigo-300 shadow-2xs font-semibold text-indigo-950'
                          : 'bg-white hover:bg-slate-50/90 border-slate-200/90 text-slate-700 hover:text-slate-900'
                      }`}
                    >
                      <div className="flex items-center justify-between gap-1.5">
                        <div className="flex items-center space-x-2 min-w-0 flex-1">
                          {/* Scope / Status Badge */}
                          {session.scope === 'all' ? (
                            <div className={`p-1 rounded-md flex-shrink-0 ${isActive ? 'bg-indigo-600 text-white' : 'bg-slate-100 text-slate-500'}`}>
                              <Globe className="w-3 h-3" />
                            </div>
                          ) : isDeleted ? (
                            <div className="p-1 rounded-md flex-shrink-0 bg-rose-100 text-rose-600">
                              <AlertTriangle className="w-3 h-3" />
                            </div>
                          ) : (
                            <div className="p-1 rounded-md flex-shrink-0 bg-slate-100 text-slate-500">
                              <FileText className="w-3 h-3" />
                            </div>
                          )}

                          {/* Chat Title / Rename Input */}
                          <div className="min-w-0 flex-1">
                            {isEditing ? (
                              <input
                                type="text"
                                value={editTitle}
                                autoFocus
                                onClick={(e) => e.stopPropagation()}
                                onChange={(e) => setEditTitle(e.target.value)}
                                onKeyDown={(e) => {
                                  if (e.key === 'Enter') handleSaveRename(session.id);
                                  if (e.key === 'Escape') setEditingId(null);
                                }}
                                onBlur={() => handleSaveRename(session.id)}
                                className="w-full bg-white border border-indigo-400 rounded px-1.5 py-0.5 text-xs text-slate-900 focus:outline-none"
                              />
                            ) : (
                              <p className={`text-xs truncate ${isActive ? 'font-bold' : 'font-medium'}`} title={session.title}>
                                {session.title || 'Untitled chat'}
                              </p>
                            )}

                            {/* Badge row - only chat history markers */}
                            <div className="flex items-center space-x-1.5 mt-0.5">
                              {session.scope === 'all' ? (
                                <span className="text-[9px] font-semibold px-1.5 py-0.2 rounded bg-indigo-50 text-indigo-700 border border-indigo-200">
                                  All files
                                </span>
                              ) : isDeleted ? (
                                <span className="text-[9px] font-bold px-1.5 py-0.2 rounded bg-rose-100 text-rose-700 border border-rose-200">
                                  File deleted
                                </span>
                              ) : null}
                              {session.message_count > 0 && (
                                <span className="text-[9px] text-slate-400">
                                  {session.message_count} {session.message_count === 1 ? 'msg' : 'msgs'}
                                </span>
                              )}
                            </div>
                          </div>
                        </div>

                        {/* Right actions: active dot & Menu */}
                        <div className="flex items-center space-x-0.5 flex-shrink-0">
                          {isActive && (
                            <span className={`w-1.5 h-1.5 rounded-full mr-1 ${isDeleted ? 'bg-rose-500' : 'bg-indigo-600 animate-pulse'}`} />
                          )}

                          {/* Chat Menu Trigger */}
                          <div className="relative" ref={menuOpenId === session.id ? menuRef : null}>
                            <button
                              type="button"
                              onClick={(e) => {
                                e.stopPropagation();
                                setMenuOpenId(menuOpenId === session.id ? null : session.id);
                              }}
                              className={`p-1 text-slate-400 hover:text-slate-700 rounded hover:bg-slate-100 transition-opacity cursor-pointer ${
                                menuOpenId === session.id ? 'opacity-100 bg-slate-100 text-slate-700' : 'opacity-0 group-hover:opacity-100'
                              }`}
                              title="Chat options"
                            >
                              <MoreVertical className="w-3.5 h-3.5" />
                            </button>

                            {/* Menu Dropdown */}
                            {menuOpenId === session.id && (
                              <div
                                className="absolute right-0 top-full mt-1 w-32 bg-white border border-slate-200 rounded-xl shadow-lg z-50 p-1 space-y-0.5"
                                onMouseDown={(e) => e.stopPropagation()}
                              >
                                <button
                                  type="button"
                                  onClick={(e) => handleStartRename(e, session)}
                                  className="w-full flex items-center space-x-1.5 px-2 py-1.5 rounded-lg text-xs text-slate-700 hover:bg-slate-100 transition-colors text-left cursor-pointer"
                                >
                                  <Edit2 className="w-3 h-3 text-slate-500" />
                                  <span>Rename</span>
                                </button>
                                <button
                                  type="button"
                                  onClick={(e) => handleDeleteClick(e, session)}
                                  className="w-full flex items-center space-x-1.5 px-2 py-1.5 rounded-lg text-xs text-rose-600 hover:bg-rose-50 transition-colors text-left cursor-pointer"
                                >
                                  <Trash2 className="w-3 h-3 text-rose-600" />
                                  <span>Delete chat</span>
                                </button>
                              </div>
                            )}
                          </div>
                        </div>
                      </div>
                    </div>
                  );
                })}
              </div>
            </div>
          ))
        )}

        {loading && (
          <div className="text-center py-2 text-[11px] text-slate-400">
            <span>Updating chats...</span>
          </div>
        )}
      </div>

      {/* Retention Notice Footer */}
      <div className="p-3 border-t border-slate-200/80 bg-slate-50/50">
        <div className="flex items-center gap-2 text-[11px] text-slate-500 justify-center text-center">
          <Clock className="w-3.5 h-3.5 text-slate-400 shrink-0" />
          <span>Chats older than 30 days are deleted automatically</span>
        </div>
      </div>

      {/* Delete Chat Confirmation Modal Dialog */}
      {sessionToDelete && typeof document !== 'undefined' && createPortal(
        <div
          role="dialog"
          aria-modal="true"
          aria-labelledby="delete-session-dialog-title"
          className="fixed inset-0 z-[9999] flex items-center justify-center p-4 bg-slate-900/60 backdrop-blur-sm animate-in fade-in duration-200"
          onClick={(e) => {
            if (e.target === e.currentTarget) setSessionToDelete(null);
          }}
        >
          <div
            className="w-full max-w-md bg-white rounded-2xl border border-slate-200/90 shadow-2xl p-6 sm:p-7 relative overflow-hidden animate-in zoom-in-95 duration-200"
            onClick={(e) => e.stopPropagation()}
          >
            {/* Close Button */}
            <button
              type="button"
              onClick={() => setSessionToDelete(null)}
              className="absolute top-4 right-4 p-1.5 rounded-xl text-slate-400 hover:text-slate-700 hover:bg-slate-100 transition-colors cursor-pointer"
              aria-label="Close dialog"
            >
              <X className="w-4 h-4" />
            </button>

            <div className="flex items-start space-x-4">
              <div className="w-12 h-12 rounded-2xl bg-rose-50 border border-rose-200/80 flex items-center justify-center flex-shrink-0 text-rose-600 shadow-2xs">
                <Trash2 className="w-6 h-6 text-rose-600" />
              </div>

              <div className="flex-1 min-w-0 pt-0.5">
                <h3 id="delete-session-dialog-title" className="text-base font-bold text-slate-900 tracking-tight">
                  Are you sure want to delete the file
                </h3>
                <p className="mt-1.5 text-xs text-slate-500 leading-relaxed">
                  This conversation history will be permanently deleted and cannot be undone.
                </p>

                {sessionToDelete && (
                  <div className="mt-3.5 py-2.5 px-3 rounded-xl bg-slate-50 border border-slate-200/80 flex items-center space-x-2.5">
                    <div className="w-7 h-7 rounded-lg bg-indigo-50 text-indigo-700 border border-indigo-200 flex items-center justify-center flex-shrink-0">
                      <MessageSquare className="w-3.5 h-3.5" />
                    </div>
                    <div className="min-w-0 flex-1">
                      <p className="text-xs font-semibold text-slate-800 truncate" title={sessionToDelete.title}>
                        {sessionToDelete.title}
                      </p>
                      <p className="text-[11px] text-slate-500 truncate">
                        {sessionToDelete.message_count || 0} messages • {sessionToDelete.scope === 'all' ? 'All files' : sessionToDelete.file_name || 'Document'}
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
                onClick={() => setSessionToDelete(null)}
                className="px-4 py-2 rounded-xl text-xs font-semibold text-slate-700 hover:text-slate-900 bg-slate-100 hover:bg-slate-200/80 transition-all cursor-pointer active:scale-95"
              >
                Cancel
              </button>

              <button
                type="button"
                onClick={handleConfirmDelete}
                className="inline-flex items-center space-x-1.5 px-4 py-2 rounded-xl text-xs font-semibold text-white bg-gradient-to-r from-rose-600 to-red-600 hover:from-rose-500 hover:to-red-500 shadow-xs shadow-rose-600/25 active:scale-95 transition-all cursor-pointer"
              >
                <Trash2 className="w-3.5 h-3.5" />
                <span>Yes, Delete</span>
              </button>
            </div>
          </div>
        </div>,
        document.body
      )}
    </aside>
  );
}
