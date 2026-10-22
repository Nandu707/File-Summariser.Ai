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
  Layers,
  Shield,
  LogOut,
  Database,
  PanelLeftClose,
  PanelLeftOpen,
  Sun,
  Moon
} from 'lucide-react';
import { useAuth } from '../context/AuthContext';
import { useTheme } from '../context/ThemeContext';
import ConfirmModal from './ConfirmModal';

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
    return date.toLocaleDateString('en-US', { month: 'short', year: 'numeric' });
  }
}

/**
 * Derives user initials (e.g. "NK" for "Nanda Kumar")
 */
function getInitials(name, email) {
  if (name && typeof name === 'string' && name.trim()) {
    const parts = name.trim().split(/\s+/);
    if (parts.length >= 2) {
      return (parts[0][0] + parts[parts.length - 1][0]).toUpperCase();
    }
    return parts[0].slice(0, 2).toUpperCase();
  }
  if (email && typeof email === 'string') {
    return email.slice(0, 2).toUpperCase();
  }
  return 'U';
}

export default function Sidebar({
  isCollapsed = false,
  onToggleCollapse,
  activeTab = 'chat',
  onSelectTab,
  docCount = 0,
  pendingCount = 0,
  backendStatus = 'healthy',
  sessions = [],
  activeSessionId = 'all',
  documents = [],
  onSelectSession,
  onCreateSession,
  onRenameSession,
  onDeleteSession,
  searchQuery = '',
  onSearchChange,
  loading = false,
}) {
  const { user, logout } = useAuth();
  const isAdmin = user?.role === 'admin';

  const { isDark, toggleTheme } = useTheme();

  const [showNewChatMenu, setShowNewChatMenu] = useState(false);
  const [menuOpenId, setMenuOpenId] = useState(null);
  const [editingId, setEditingId] = useState(null);
  const [editTitle, setEditTitle] = useState('');
  const [sessionToDelete, setSessionToDelete] = useState(null);
  const [showLogoutConfirm, setShowLogoutConfirm] = useState(false);
  const [isLoggingOut, setIsLoggingOut] = useState(false);
  const [isSearchOpen, setIsSearchOpen] = useState(false);

  const menuRef = useRef(null);
  const newChatRef = useRef(null);
  const searchInputRef = useRef(null);

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
    const historyOnly = sessions.filter((s) => (s.message_count || 0) > 0);
    if (!searchQuery.trim()) return historyOnly;
    const q = searchQuery.toLowerCase().trim();
    return historyOnly.filter(
      (s) =>
        (s.title && s.title.toLowerCase().includes(q)) ||
        (s.file_name && s.file_name.toLowerCase().includes(q))
    );
  }, [sessions, searchQuery]);

  // Group sessions chronologically: Today, Yesterday, Previous 7 days, etc.
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
    if (onSelectTab && activeTab !== 'chat') {
      onSelectTab('chat');
    }
    if (onCreateSession) {
      if (scope === 'all') {
        onCreateSession({ scope: 'all', title: 'New chat' });
      } else if (doc) {
        onCreateSession({
          scope: 'file',
          file_id: doc.doc_id,
          file_name: doc.filename,
          title: `Chat: ${doc.filename}`,
        });
      }
    }
  };

  const handleConfirmLogout = async () => {
    try {
      setIsLoggingOut(true);
      await logout();
      setShowLogoutConfirm(false);
    } catch (err) {
      console.error('Logout error:', err);
    } finally {
      setIsLoggingOut(false);
    }
  };

  const handleExpandAndSearch = () => {
    if (isCollapsed && onToggleCollapse) {
      onToggleCollapse();
    }
    setIsSearchOpen(true);
    setTimeout(() => searchInputRef.current?.focus(), 150);
  };

  const userInitials = getInitials(user?.name, user?.email);

  return (
    <>
      {/* ======================================================== */}
      {/* UNIFIED SIDEBAR: Smooth width gliding & seamless crossfade */}
      {/* ======================================================== */}
      <aside
        aria-label="Sidebar navigation"
        className={`h-screen flex flex-col select-none flex-shrink-0 z-40 relative overflow-hidden transition-[width,background-color,border-color] duration-300 ease-[cubic-bezier(0.2,0,0,1)] ${
          isCollapsed ? 'w-14' : 'w-[260px]'
        } ${
          isDark
            ? 'bg-[#171717] border-r border-[#262626] text-neutral-200'
            : 'bg-white border-r border-slate-200/90 text-slate-700 shadow-2xs'
        }`}
      >
        {/* 1. COLLAPSED VIEW: Slim Icon Rail (~56px) */}
        <div
          className={`w-14 h-full flex flex-col items-center justify-between py-3.5 absolute inset-y-0 left-0 transition-all duration-200 ease-in-out ${
            isCollapsed
              ? 'opacity-100 pointer-events-auto z-10 translate-x-0'
              : 'opacity-0 pointer-events-none -z-10 -translate-x-2'
          }`}
        >
          {/* Top Actions: Logo, Toggle, New Chat, Nav Icons */}
          <div className="flex flex-col items-center space-y-3 w-full px-2">
            {/* Logo / Brand Icon */}
            <button
              type="button"
              onClick={onToggleCollapse}
              className="w-9 h-9 rounded-xl bg-gradient-to-tr from-indigo-600 via-blue-600 to-sky-500 p-[1.5px] hover:scale-105 transition-all shadow-sm shadow-indigo-500/20 group relative cursor-pointer"
              title="Expand sidebar"
            >
              <div className={`w-full h-full rounded-[10px] flex items-center justify-center ${
                isDark ? 'bg-[#171717]' : 'bg-white'
              }`}>
                <Database className={`w-4 h-4 ${isDark ? 'text-indigo-400' : 'text-indigo-600'} group-hover:scale-110 transition-transform`} />
              </div>
              <div className="hidden lg:flex absolute left-full ml-3 px-2.5 py-1.5 bg-slate-900/95 backdrop-blur-sm text-white text-xs font-medium rounded-lg shadow-xl opacity-0 group-hover:opacity-100 pointer-events-none transition-opacity whitespace-nowrap z-50">
                <span>File Summariser.Ai (Expand)</span>
              </div>
            </button>

            {/* Expand Sidebar Toggle Icon */}
            <button
              type="button"
              onClick={onToggleCollapse}
              className={`w-9 h-9 rounded-xl transition-colors flex items-center justify-center group relative cursor-pointer active:scale-95 ${
                isDark
                  ? 'hover:bg-neutral-800 text-neutral-400 hover:text-white'
                  : 'hover:bg-slate-100 text-slate-500 hover:text-slate-900'
              }`}
              title="Open sidebar"
              aria-label="Open sidebar"
            >
              <PanelLeftOpen className="w-4 h-4" />
              <div className="hidden lg:flex absolute left-full ml-3 px-2.5 py-1.5 bg-slate-900/95 backdrop-blur-sm text-white text-xs font-medium rounded-lg shadow-xl opacity-0 group-hover:opacity-100 pointer-events-none transition-opacity whitespace-nowrap z-50">
                <span>Open sidebar</span>
              </div>
            </button>

            <div className={`w-6 h-[1px] ${isDark ? 'bg-neutral-800' : 'bg-slate-200'}`} />

            {/* New Chat Button */}
            <button
              type="button"
              onClick={() => {
                if (onSelectTab && activeTab !== 'chat') onSelectTab('chat');
                handleCreateScope('all');
              }}
              className={`w-9 h-9 rounded-xl transition-colors flex items-center justify-center group relative cursor-pointer active:scale-95 ${
                isDark
                  ? 'hover:bg-neutral-800 text-neutral-400 hover:text-white'
                  : 'hover:bg-slate-100 text-slate-500 hover:text-indigo-600'
              }`}
              title="New chat"
              aria-label="New chat"
            >
              <Plus className="w-4 h-4" />
              <div className="hidden lg:flex absolute left-full ml-3 px-2.5 py-1.5 bg-slate-900/95 backdrop-blur-sm text-white text-xs font-medium rounded-lg shadow-xl opacity-0 group-hover:opacity-100 pointer-events-none transition-opacity whitespace-nowrap z-50">
                <span>New chat</span>
              </div>
            </button>

            {/* Search Icon */}
            <button
              type="button"
              onClick={handleExpandAndSearch}
              className={`w-9 h-9 rounded-xl transition-colors flex items-center justify-center group relative cursor-pointer active:scale-95 ${
                isDark
                  ? 'hover:bg-neutral-800 text-neutral-400 hover:text-white'
                  : 'hover:bg-slate-100 text-slate-500 hover:text-slate-900'
              }`}
              title="Search chats"
              aria-label="Search chats"
            >
              <Search className="w-4 h-4" />
              <div className="hidden lg:flex absolute left-full ml-3 px-2.5 py-1.5 bg-slate-900/95 backdrop-blur-sm text-white text-xs font-medium rounded-lg shadow-xl opacity-0 group-hover:opacity-100 pointer-events-none transition-opacity whitespace-nowrap z-50">
                <span>Search chats</span>
              </div>
            </button>

            {/* Primary Nav Option: Chat & Q&A */}
            <button
              type="button"
              onClick={() => onSelectTab && onSelectTab('chat')}
              className={`w-9 h-9 rounded-xl transition-all flex items-center justify-center group relative cursor-pointer active:scale-95 ${
                activeTab === 'chat'
                  ? isDark
                    ? 'bg-neutral-800 text-white font-medium'
                    : 'bg-indigo-50 text-indigo-700 shadow-2xs border border-indigo-200/80 font-bold'
                  : isDark
                  ? 'text-neutral-400 hover:text-white hover:bg-neutral-800/60'
                  : 'text-slate-500 hover:text-slate-900 hover:bg-slate-100/80'
              }`}
              title="Chat & Q&A"
            >
              <MessageSquare className="w-4 h-4" />
              <div className="hidden lg:flex absolute left-full ml-3 px-2.5 py-1.5 bg-slate-900/95 backdrop-blur-sm text-white text-xs font-medium rounded-lg shadow-xl opacity-0 group-hover:opacity-100 pointer-events-none transition-opacity whitespace-nowrap z-50">
                <span>Chat & Q&A</span>
              </div>
            </button>

            {/* Primary Nav Option: Files / Shared Documents */}
            <button
              type="button"
              onClick={() => onSelectTab && onSelectTab('documents')}
              className={`w-9 h-9 rounded-xl transition-all flex items-center justify-center group relative cursor-pointer active:scale-95 ${
                activeTab === 'documents'
                  ? isDark
                    ? 'bg-neutral-800 text-white font-medium'
                    : 'bg-indigo-50 text-indigo-700 shadow-2xs border border-indigo-200/80 font-bold'
                  : isDark
                  ? 'text-neutral-400 hover:text-white hover:bg-neutral-800/60'
                  : 'text-slate-500 hover:text-slate-900 hover:bg-slate-100/80'
              }`}
              title={isAdmin ? 'Files' : 'Shared Documents'}
            >
              <Layers className="w-4 h-4" />
              {docCount > 0 && (
                <span className={`absolute top-1.5 right-1.5 w-2 h-2 rounded-full ${
                  isDark ? 'bg-indigo-500 ring-2 ring-[#171717]' : 'bg-indigo-600 ring-2 ring-white'
                }`} />
              )}
              <div className="hidden lg:flex absolute left-full ml-3 px-2.5 py-1.5 bg-slate-900/95 backdrop-blur-sm text-white text-xs font-medium rounded-lg shadow-xl opacity-0 group-hover:opacity-100 pointer-events-none transition-opacity whitespace-nowrap z-50 items-center space-x-1.5">
                <span>{isAdmin ? 'Files' : 'Shared Documents'}</span>
                <span className="text-slate-400 font-normal">({docCount})</span>
              </div>
            </button>

            {/* Primary Nav Option: Users (Admin only) */}
            {isAdmin && (
              <button
                type="button"
                onClick={() => onSelectTab && onSelectTab('users')}
                className={`w-9 h-9 rounded-xl transition-all flex items-center justify-center group relative cursor-pointer active:scale-95 ${
                  activeTab === 'users'
                    ? isDark
                      ? 'bg-neutral-800 text-white font-medium'
                      : 'bg-indigo-50 text-indigo-700 shadow-2xs border border-indigo-200/80 font-bold'
                    : isDark
                    ? 'text-neutral-400 hover:text-white hover:bg-neutral-800/60'
                    : 'text-slate-500 hover:text-slate-900 hover:bg-slate-100/80'
                }`}
                title="Users"
              >
                <Shield className="w-4 h-4" />
                {pendingCount > 0 && (
                  <span className={`absolute top-1.5 right-1.5 w-2 h-2 rounded-full bg-amber-500 animate-pulse ${
                    isDark ? 'ring-2 ring-[#171717]' : 'ring-2 ring-white'
                  }`} />
                )}
                <div className="hidden lg:flex absolute left-full ml-3 px-2.5 py-1.5 bg-slate-900/95 backdrop-blur-sm text-white text-xs font-medium rounded-lg shadow-xl opacity-0 group-hover:opacity-100 pointer-events-none transition-opacity whitespace-nowrap z-50 items-center space-x-1.5">
                  <span>Users</span>
                  {pendingCount > 0 && (
                    <span className="text-amber-400 font-semibold">({pendingCount} pending)</span>
                  )}
                </div>
              </button>
            )}
          </div>

          {/* Bottom Rail: Theme Toggle, API Status & User Avatar */}
          <div className="flex flex-col items-center space-y-2.5 w-full px-2">
            {/* Theme Toggle Button (Light/Dark) */}
            <button
              type="button"
              onClick={toggleTheme}
              className={`w-9 h-9 rounded-xl transition-all duration-300 flex items-center justify-center group relative cursor-pointer active:scale-90 ${
                isDark
                  ? 'text-amber-400 hover:text-amber-300 hover:bg-neutral-800'
                  : 'text-slate-500 hover:text-amber-600 hover:bg-slate-100'
              }`}
              title={isDark ? 'Switch to light mode' : 'Switch to dark mode'}
              aria-label={isDark ? 'Switch to light mode' : 'Switch to dark mode'}
            >
              <div className={`transition-transform duration-500 ease-out ${isDark ? 'rotate-[360deg] scale-110' : 'rotate-0 scale-100'}`}>
                {isDark ? <Sun className="w-4 h-4" /> : <Moon className="w-4 h-4" />}
              </div>
              <div className="hidden lg:flex absolute left-full ml-3 px-2.5 py-1.5 bg-slate-900/95 backdrop-blur-sm text-white text-xs font-medium rounded-lg shadow-xl opacity-0 group-hover:opacity-100 pointer-events-none transition-opacity whitespace-nowrap z-50">
                <span>{isDark ? 'Light mode' : 'Dark mode'}</span>
              </div>
            </button>

            {/* Status indicator dot */}
            <div
              className="w-3 h-3 rounded-full cursor-help group relative flex items-center justify-center"
              title={backendStatus === 'healthy' ? 'API Online' : 'API Offline'}
            >
              <span
                className={`w-2 h-2 rounded-full ${
                  backendStatus === 'healthy' ? 'bg-emerald-500 animate-pulse' : 'bg-rose-500'
                }`}
              />
              <div className="hidden lg:flex absolute left-full ml-3 px-2.5 py-1.5 bg-slate-900/95 backdrop-blur-sm text-white text-xs font-medium rounded-lg shadow-xl opacity-0 group-hover:opacity-100 pointer-events-none transition-opacity whitespace-nowrap z-50">
                <span>{backendStatus === 'healthy' ? 'API Online' : 'API Offline'}</span>
              </div>
            </div>

            <div className={`w-6 h-[1px] ${isDark ? 'bg-neutral-800' : 'bg-slate-200'}`} />

            {/* User Avatar Circle */}
            <button
              type="button"
              onClick={() => setShowLogoutConfirm(true)}
              className="w-8 h-8 rounded-full bg-gradient-to-tr from-indigo-600 via-blue-600 to-sky-500 text-white font-bold text-xs flex items-center justify-center shadow-sm shadow-indigo-500/20 hover:scale-105 active:scale-95 transition-transform group relative cursor-pointer"
              title="User profile & Logout"
              aria-label="User profile & Logout"
            >
              {userInitials}
              <div className="hidden lg:flex flex-col absolute left-full ml-3 px-2.5 py-1.5 bg-slate-900/95 backdrop-blur-sm text-white text-xs font-medium rounded-lg shadow-xl opacity-0 group-hover:opacity-100 pointer-events-none transition-opacity whitespace-nowrap z-50 text-left">
                <p className="font-semibold">{user?.name || user?.email || 'User'}</p>
                <p className="text-[10px] text-slate-400 capitalize">{user?.role || 'User'} • Click to Log out</p>
              </div>
            </button>
          </div>
        </div>

        {/* 2. EXPANDED VIEW: Full Sidebar (~260px) */}
        <div
          className={`w-[260px] h-full flex flex-col absolute inset-y-0 left-0 transition-all duration-200 ease-in-out ${
            !isCollapsed
              ? 'opacity-100 pointer-events-auto z-10 translate-x-0'
              : 'opacity-0 pointer-events-none -z-10 -translate-x-3'
          }`}
        >
          {/* Header Bar: Brand Logo & Title + Theme Toggle, Search & Collapse */}
          <div className={`p-3.5 pb-2.5 flex items-center justify-between border-b ${
            isDark ? 'border-neutral-800/80 bg-[#171717]' : 'border-slate-200/80 bg-slate-50/50'
          }`}>
            <div
              onClick={() => onSelectTab && onSelectTab('chat')}
              className="flex items-center space-x-2.5 cursor-pointer group min-w-0"
              title="File Summariser.Ai"
            >
              <div className="w-8 h-8 rounded-xl bg-gradient-to-tr from-indigo-600 via-blue-600 to-sky-500 p-[1.5px] flex-shrink-0 shadow-sm shadow-indigo-500/20 group-hover:scale-105 transition-transform">
                <div className={`w-full h-full rounded-[10px] flex items-center justify-center ${
                  isDark ? 'bg-[#171717]' : 'bg-white'
                }`}>
                  <Database className={`w-4 h-4 ${isDark ? 'text-indigo-400' : 'text-indigo-600'}`} />
                </div>
              </div>
              <span className={`font-extrabold text-sm tracking-tight truncate ${
                isDark ? 'text-white' : 'bg-gradient-to-r from-slate-900 via-indigo-950 to-blue-900 bg-clip-text text-transparent'
              }`}>
                File Summariser.Ai
              </span>
            </div>

            <div className="flex items-center space-x-1 flex-shrink-0">
              {/* Theme Toggle Button */}
              <button
                type="button"
                onClick={toggleTheme}
                className={`p-1.5 rounded-lg transition-all duration-300 cursor-pointer active:scale-90 ${
                  isDark
                    ? 'text-amber-400 hover:text-amber-300 hover:bg-neutral-800'
                    : 'text-slate-400 hover:text-amber-600 hover:bg-slate-100'
                }`}
                title={isDark ? 'Switch to light mode' : 'Switch to dark mode'}
                aria-label={isDark ? 'Switch to light mode' : 'Switch to dark mode'}
              >
                <div className={`transition-transform duration-500 ease-out ${isDark ? 'rotate-[360deg] scale-110' : 'rotate-0 scale-100'}`}>
                  {isDark ? <Sun className="w-4 h-4" /> : <Moon className="w-4 h-4" />}
                </div>
              </button>

              {/* Search Toggle Button */}
              <button
                type="button"
                onClick={() => {
                  setIsSearchOpen((prev) => !prev);
                  setTimeout(() => searchInputRef.current?.focus(), 100);
                }}
                className={`p-1.5 rounded-lg transition-colors cursor-pointer ${
                  isSearchOpen
                    ? isDark
                      ? 'bg-neutral-800 text-white'
                      : 'bg-slate-100 text-indigo-600'
                    : isDark
                    ? 'text-neutral-400 hover:text-white hover:bg-neutral-800'
                    : 'text-slate-400 hover:text-slate-800 hover:bg-slate-100'
                }`}
                title="Search chats"
                aria-label="Search chats"
              >
                <Search className="w-4 h-4" />
              </button>

              {/* Collapse Button */}
              {onToggleCollapse && (
                <button
                  type="button"
                  onClick={onToggleCollapse}
                  className={`p-1.5 rounded-lg transition-colors cursor-pointer ${
                    isDark
                      ? 'text-neutral-400 hover:text-white hover:bg-neutral-800'
                      : 'text-slate-400 hover:text-slate-800 hover:bg-slate-100'
                  }`}
                  title="Collapse sidebar"
                  aria-label="Collapse sidebar"
                >
                  <PanelLeftClose className="w-4 h-4" />
                </button>
              )}
            </div>
          </div>

          {/* New Chat Button Row (Scope selector dropdown) */}
          <div className="px-3 pt-3 pb-1.5" ref={newChatRef}>
            <div className="relative">
              <button
                type="button"
                onClick={() => setShowNewChatMenu((prev) => !prev)}
                className={`w-full flex items-center justify-between px-3 py-2 rounded-xl text-xs font-semibold text-white shadow-sm active:scale-98 transition-all cursor-pointer ${
                  isDark
                    ? 'bg-neutral-800 hover:bg-neutral-700/80 border border-neutral-700'
                    : 'bg-gradient-to-r from-indigo-600 via-indigo-600 to-blue-600 hover:from-indigo-500 hover:to-blue-500 shadow-indigo-600/20'
                }`}
              >
                <div className="flex items-center space-x-2">
                  <Plus className="w-4 h-4 text-white" />
                  <span>New chat</span>
                </div>
                <ChevronDown className={`w-3.5 h-3.5 transition-transform ${
                  isDark ? 'text-neutral-400' : 'text-indigo-200'
                } ${showNewChatMenu ? 'rotate-180' : ''}`} />
              </button>

              {/* Scope Selection Popover */}
              {showNewChatMenu && (
                <div className={`absolute top-full left-0 right-0 mt-1.5 rounded-xl shadow-xl z-50 p-1.5 space-y-1 animate-in fade-in zoom-in-95 duration-150 border ${
                  isDark
                    ? 'bg-[#212121] border-neutral-700 text-neutral-200'
                    : 'bg-white border-slate-200 text-slate-700'
                }`}>
                  <button
                    type="button"
                    onClick={() => handleCreateScope('all')}
                    className={`w-full flex items-center space-x-2 px-2.5 py-2 rounded-lg text-xs font-semibold transition-colors text-left cursor-pointer ${
                      isDark
                        ? 'text-neutral-200 hover:bg-neutral-700/60'
                        : 'text-slate-700 hover:text-indigo-900 hover:bg-indigo-50/80'
                    }`}
                  >
                    <div className={`p-1 rounded ${
                      isDark ? 'bg-indigo-500/20 text-indigo-400' : 'bg-indigo-50 text-indigo-600'
                    }`}>
                      <Globe className="w-3.5 h-3.5" />
                    </div>
                    <div>
                      <p className={`font-semibold ${isDark ? 'text-white' : 'text-slate-800'}`}>All files</p>
                      <p className={`text-[10px] font-normal ${isDark ? 'text-neutral-400' : 'text-slate-400'}`}>Search across all active files</p>
                    </div>
                  </button>

                  {documents.length > 0 && (
                    <div className={`pt-1 border-t ${isDark ? 'border-neutral-700/60' : 'border-slate-100'}`}>
                      <p className={`text-[10px] font-bold uppercase tracking-wider px-2 py-1 ${
                        isDark ? 'text-neutral-400' : 'text-slate-400'
                      }`}>
                        Specific File
                      </p>
                      <div className="max-h-40 overflow-y-auto custom-scrollbar space-y-0.5">
                        {documents.map((doc) => (
                          <button
                            key={doc.doc_id}
                            type="button"
                            onClick={() => handleCreateScope('file', doc)}
                            className={`w-full flex items-center space-x-2 px-2.5 py-1.5 rounded-lg text-xs transition-colors text-left cursor-pointer ${
                              isDark
                                ? 'text-neutral-300 hover:text-white hover:bg-neutral-700/60'
                                : 'text-slate-700 hover:text-indigo-900 hover:bg-indigo-50/80'
                            }`}
                          >
                            <FileText className={`w-3.5 h-3.5 flex-shrink-0 ${isDark ? 'text-neutral-400' : 'text-slate-400'}`} />
                            <span className="truncate">{doc.filename}</span>
                          </button>
                        ))}
                      </div>
                    </div>
                  )}
                </div>
              )}
            </div>
          </div>

          {/* Primary Navigation Options (Transferred from header) */}
          <div className="px-3 py-1 space-y-1">
            {/* Chat & Q&A */}
            <button
              type="button"
              onClick={() => onSelectTab && onSelectTab('chat')}
              className={`w-full flex items-center justify-between px-3 py-2 rounded-xl text-xs font-medium transition-all cursor-pointer ${
                activeTab === 'chat'
                  ? isDark
                    ? 'bg-neutral-800 text-white font-semibold'
                    : 'bg-indigo-50 text-indigo-700 font-bold border border-indigo-200/80 shadow-2xs'
                  : isDark
                  ? 'text-neutral-400 hover:text-neutral-200 hover:bg-neutral-800/50 border border-transparent'
                  : 'text-slate-600 hover:text-slate-900 hover:bg-slate-100/70 border border-transparent'
              }`}
            >
              <div className="flex items-center space-x-2.5 min-w-0">
                <MessageSquare className={`w-4 h-4 ${
                  activeTab === 'chat'
                    ? isDark ? 'text-indigo-400' : 'text-indigo-600'
                    : isDark ? 'text-neutral-400' : 'text-slate-400'
                }`} />
                <span className="truncate">Chat & Q&A</span>
              </div>
            </button>

            {/* Files / Shared Documents */}
            <button
              type="button"
              onClick={() => onSelectTab && onSelectTab('documents')}
              className={`w-full flex items-center justify-between px-3 py-2 rounded-xl text-xs font-medium transition-all cursor-pointer ${
                activeTab === 'documents'
                  ? isDark
                    ? 'bg-neutral-800 text-white font-semibold'
                    : 'bg-indigo-50 text-indigo-700 font-bold border border-indigo-200/80 shadow-2xs'
                  : isDark
                  ? 'text-neutral-400 hover:text-neutral-200 hover:bg-neutral-800/50 border border-transparent'
                  : 'text-slate-600 hover:text-slate-900 hover:bg-slate-100/70 border border-transparent'
              }`}
            >
              <div className="flex items-center space-x-2.5 min-w-0">
                <Layers className={`w-4 h-4 ${
                  activeTab === 'documents'
                    ? isDark ? 'text-indigo-400' : 'text-indigo-600'
                    : isDark ? 'text-neutral-400' : 'text-slate-400'
                }`} />
                <span className="truncate">{isAdmin ? 'Files' : 'Shared Documents'}</span>
              </div>
              {docCount > 0 && (
                <span className={`text-[10px] font-bold px-2 py-0.5 rounded-full ${
                  activeTab === 'documents'
                    ? isDark
                      ? 'bg-neutral-700 text-white'
                      : 'bg-indigo-600 text-white'
                    : isDark
                    ? 'bg-neutral-800 text-neutral-300 border border-neutral-700'
                    : 'bg-slate-100 text-slate-700 border border-slate-200'
                }`}>
                  {docCount}
                </span>
              )}
            </button>

            {/* Users (Admin only) */}
            {isAdmin && (
              <button
                type="button"
                onClick={() => onSelectTab && onSelectTab('users')}
                className={`w-full flex items-center justify-between px-3 py-2 rounded-xl text-xs font-medium transition-all cursor-pointer ${
                  activeTab === 'users'
                    ? isDark
                      ? 'bg-neutral-800 text-white font-semibold'
                      : 'bg-indigo-50 text-indigo-700 font-bold border border-indigo-200/80 shadow-2xs'
                  : isDark
                  ? 'text-neutral-400 hover:text-neutral-200 hover:bg-neutral-800/50 border border-transparent'
                  : 'text-slate-600 hover:text-slate-900 hover:bg-slate-100/70 border border-transparent'
                }`}
              >
                <div className="flex items-center space-x-2.5 min-w-0">
                  <Shield className={`w-4 h-4 ${
                    activeTab === 'users'
                      ? isDark ? 'text-amber-400' : 'text-indigo-600'
                      : isDark ? 'text-neutral-400' : 'text-slate-400'
                  }`} />
                  <span className="truncate">Users</span>
                </div>
                {pendingCount > 0 && (
                  <span className="text-[10px] font-bold px-2 py-0.5 rounded-full bg-amber-500 text-white animate-pulse">
                    {pendingCount}
                  </span>
                )}
              </button>
            )}

            {/* Backend Health Pill */}
            <div className="pt-1 px-1">
              <div
                className={`inline-flex items-center space-x-2 px-2.5 py-1 rounded-full text-[11px] font-medium border transition-colors ${
                  backendStatus === 'healthy'
                    ? isDark
                      ? 'bg-emerald-950/40 text-emerald-400 border-emerald-800/60'
                      : 'bg-emerald-50 text-emerald-700 border-emerald-200 shadow-2xs'
                    : backendStatus === 'checking'
                    ? isDark
                      ? 'bg-amber-950/40 text-amber-400 border-amber-800/60'
                      : 'bg-amber-50 text-amber-700 border-amber-200'
                    : isDark
                    ? 'bg-rose-950/40 text-rose-400 border-rose-800/60'
                    : 'bg-rose-50 text-rose-700 border-rose-200'
                }`}
              >
                <span
                  className={`w-2 h-2 rounded-full ${
                    backendStatus === 'healthy' ? 'bg-emerald-500 animate-pulse' : 'bg-rose-500'
                  }`}
                />
                <span>
                  {backendStatus === 'healthy' ? 'API Online' : backendStatus === 'checking' ? 'Connecting...' : 'API Offline'}
                </span>
              </div>
            </div>
          </div>

          {/* Search Box (Expandable or standard) */}
          {isSearchOpen && (
            <div className="px-3 py-1.5 animate-in fade-in duration-150">
              <div className="relative">
                <Search className={`w-3.5 h-3.5 absolute left-2.5 top-1/2 -translate-y-1/2 pointer-events-none ${
                  isDark ? 'text-neutral-400' : 'text-slate-400'
                }`} />
                <input
                  ref={searchInputRef}
                  type="text"
                  value={searchQuery}
                  onChange={(e) => onSearchChange && onSearchChange(e.target.value)}
                  placeholder="Search chats..."
                  className={`w-full rounded-xl pl-8 pr-7 py-1.5 text-xs focus:outline-none transition-colors border ${
                    isDark
                      ? 'bg-neutral-800/80 hover:bg-neutral-800 focus:bg-[#212121] border-neutral-700 focus:border-indigo-500 text-white placeholder-neutral-400'
                      : 'bg-slate-50 hover:bg-slate-100/80 focus:bg-white border-slate-200 focus:border-indigo-400 text-slate-800 placeholder-slate-400'
                  }`}
                />
                {searchQuery && (
                  <button
                    onClick={() => onSearchChange && onSearchChange('')}
                    className={`absolute right-2 top-1/2 -translate-y-1/2 ${
                      isDark ? 'text-neutral-400 hover:text-white' : 'text-slate-400 hover:text-slate-600'
                    }`}
                  >
                    <X className="w-3 h-3" />
                  </button>
                )}
              </div>
            </div>
          )}

          {/* Recents Section Header */}
          <div className={`px-3 pt-3 pb-1 flex items-center justify-between border-t mt-1 ${
            isDark ? 'border-neutral-800' : 'border-slate-100'
          }`}>
            <span className={`text-[11px] font-bold uppercase tracking-wider ${
              isDark ? 'text-neutral-400' : 'text-slate-400'
            }`}>
              Recents
            </span>
            <span className={`text-[10px] font-semibold px-1.5 py-0.5 rounded ${
              isDark ? 'text-neutral-500 bg-neutral-800' : 'text-slate-400 bg-slate-100'
            }`}>
              {filteredSessions.length}
            </span>
          </div>

          {/* Chat List Grouped Chronologically */}
          <div className="flex-1 min-h-0 overflow-y-auto custom-scrollbar px-2 space-y-3">
            {groupedSessions.length === 0 ? (
              <div className={`text-center py-6 text-xs space-y-1.5 ${
                isDark ? 'text-neutral-500' : 'text-slate-400'
              }`}>
                <MessageSquare className={`w-5 h-5 mx-auto ${
                  isDark ? 'text-neutral-600' : 'text-slate-300'
                }`} />
                <p>{searchQuery ? 'No matching chats' : 'No recent chats'}</p>
              </div>
            ) : (
              groupedSessions.map((group) => (
                <div key={group.title} className="space-y-0.5">
                  <p className={`text-[10px] font-bold uppercase tracking-wider px-2 py-0.5 sticky top-0 backdrop-blur-xs z-10 ${
                    isDark ? 'text-neutral-500 bg-[#171717]/95' : 'text-slate-400 bg-white/95'
                  }`}>
                    {group.title}
                  </p>

                  <div className="space-y-0.5">
                    {group.items.map((session) => {
                      const isActive = session.id === activeSessionId && activeTab === 'chat';
                      const isDeleted = Boolean(session.is_file_deleted);
                      const isEditing = editingId === session.id;

                      return (
                        <div
                          key={session.id}
                          onClick={() => {
                            if (!isEditing) {
                              if (onSelectTab && activeTab !== 'chat') onSelectTab('chat');
                              onSelectSession(session.id);
                            }
                          }}
                          className={`group relative px-2.5 py-2 rounded-xl text-left cursor-pointer transition-all flex items-center justify-between gap-1.5 border ${
                            isActive
                              ? isDark
                                ? 'bg-neutral-800 text-white font-medium border-transparent'
                                : 'bg-gradient-to-r from-indigo-50 to-blue-50/60 border-indigo-200/80 text-indigo-950 font-semibold shadow-2xs'
                              : isDark
                              ? 'border-transparent text-neutral-300 hover:bg-neutral-800/60 hover:text-white'
                              : 'border-transparent text-slate-700 hover:bg-slate-100/80 hover:text-slate-900'
                          }`}
                        >
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
                                className={`w-full rounded px-1.5 py-0.5 text-xs focus:outline-none border ${
                                  isDark
                                    ? 'bg-[#212121] border-indigo-500 text-white'
                                    : 'bg-white border-indigo-400 text-slate-900'
                                }`}
                              />
                            ) : (
                              <p className="text-xs truncate" title={session.title}>
                                {session.title || 'Untitled chat'}
                              </p>
                            )}
                          </div>

                          {/* Options Menu Trigger */}
                          <div className="relative flex-shrink-0" ref={menuOpenId === session.id ? menuRef : null}>
                            <button
                              type="button"
                              onClick={(e) => {
                                e.stopPropagation();
                                setMenuOpenId(menuOpenId === session.id ? null : session.id);
                              }}
                              className={`p-1 rounded transition-opacity cursor-pointer ${
                                isDark
                                  ? menuOpenId === session.id
                                    ? 'opacity-100 bg-neutral-700 text-white'
                                    : 'opacity-0 group-hover:opacity-100 text-neutral-400 hover:text-white hover:bg-neutral-700'
                                  : menuOpenId === session.id
                                  ? 'opacity-100 bg-slate-200/60 text-slate-700'
                                  : 'opacity-0 group-hover:opacity-100 text-slate-400 hover:text-slate-700 hover:bg-slate-200/60'
                              }`}
                              title="Options"
                            >
                              <MoreVertical className="w-3.5 h-3.5" />
                            </button>

                            {/* Options Dropdown */}
                            {menuOpenId === session.id && (
                              <div
                                className={`absolute right-0 top-full mt-1 w-28 rounded-xl shadow-xl z-50 p-1 space-y-0.5 border ${
                                  isDark
                                    ? 'bg-[#212121] border-neutral-700'
                                    : 'bg-white border-slate-200'
                                }`}
                                onMouseDown={(e) => e.stopPropagation()}
                              >
                                <button
                                  type="button"
                                  onClick={(e) => handleStartRename(e, session)}
                                  className={`w-full flex items-center space-x-1.5 px-2 py-1.5 rounded-lg text-xs transition-colors text-left cursor-pointer ${
                                    isDark
                                      ? 'text-neutral-300 hover:bg-neutral-700 hover:text-white'
                                      : 'text-slate-700 hover:bg-slate-100'
                                  }`}
                                >
                                  <Edit2 className="w-3 h-3 text-slate-400" />
                                  <span>Rename</span>
                                </button>
                                <button
                                  type="button"
                                  onClick={(e) => handleDeleteClick(e, session)}
                                  className={`w-full flex items-center space-x-1.5 px-2 py-1.5 rounded-lg text-xs text-rose-500 hover:bg-rose-500/10 transition-colors text-left cursor-pointer`}
                                >
                                  <Trash2 className="w-3 h-3 text-rose-500" />
                                  <span>Delete</span>
                                </button>
                              </div>
                            )}
                          </div>
                        </div>
                      );
                    })}
                  </div>
                </div>
              ))
            )}

            {loading && (
              <div className={`text-center py-2 text-[10px] ${
                isDark ? 'text-neutral-500' : 'text-slate-400'
              }`}>
                <span>Updating chats...</span>
              </div>
            )}
          </div>

          {/* Retention notice footer */}
          <div className={`px-3 py-2 border-t text-[10px] flex items-center justify-center space-x-1.5 ${
            isDark
              ? 'border-neutral-800 text-neutral-500'
              : 'border-slate-200/80 bg-slate-50/50 text-slate-400'
          }`}>
            <Clock className="w-3 h-3 flex-shrink-0" />
            <span className="truncate">Chats &gt;30d deleted automatically</span>
          </div>

          {/* Bottom Profile Card */}
          <div className={`p-3 border-t flex items-center justify-between gap-2 ${
            isDark
              ? 'border-neutral-800 bg-[#171717]'
              : 'border-slate-200/80 bg-white'
          }`}>
            <div className="flex items-center space-x-2.5 min-w-0 flex-1">
              <div className="w-8 h-8 rounded-full bg-gradient-to-tr from-indigo-600 via-blue-600 to-sky-500 text-white font-bold text-xs flex items-center justify-center flex-shrink-0 shadow-sm shadow-indigo-500/20">
                {userInitials}
              </div>
              <div className="min-w-0 flex-1">
                <p className={`text-xs font-bold truncate ${isDark ? 'text-white' : 'text-slate-800'}`} title={user?.name || user?.email}>
                  {user?.name || user?.email || 'User'}
                </p>
                <p className={`text-[11px] capitalize truncate ${isDark ? 'text-neutral-400' : 'text-slate-500'}`}>
                  {user?.role === 'admin' ? 'Admin' : 'Free'}
                </p>
              </div>
            </div>

            {/* Logout Action */}
            <button
              type="button"
              onClick={() => setShowLogoutConfirm(true)}
              className={`p-1.5 rounded-xl transition-colors cursor-pointer flex-shrink-0 ${
                isDark
                  ? 'text-neutral-400 hover:text-rose-400 hover:bg-neutral-800'
                  : 'text-slate-400 hover:text-rose-600 hover:bg-rose-50'
              }`}
              title="Log out"
              aria-label="Log out"
            >
              <LogOut className="w-4 h-4" />
            </button>
          </div>
        </div>
      </aside>

      {/* Delete Chat Confirmation Modal */}
      {sessionToDelete && typeof document !== 'undefined' && createPortal(
        <div
          role="dialog"
          aria-modal="true"
          className="fixed inset-0 z-[9999] flex items-center justify-center p-4 bg-slate-900/60 backdrop-blur-sm animate-in fade-in duration-200"
          onClick={(e) => {
            if (e.target === e.currentTarget) setSessionToDelete(null);
          }}
        >
          <div
            className="w-full max-w-md bg-white dark:bg-[#1e1e1e] rounded-2xl border border-slate-200/90 dark:border-neutral-800 shadow-2xl p-6 sm:p-7 relative overflow-hidden animate-in zoom-in-95 duration-200"
            onClick={(e) => e.stopPropagation()}
          >
            <button
              type="button"
              onClick={() => setSessionToDelete(null)}
              className="absolute top-4 right-4 p-1.5 rounded-xl text-slate-400 dark:text-neutral-400 hover:text-slate-700 dark:hover:text-white hover:bg-slate-100 dark:hover:bg-neutral-800 transition-colors cursor-pointer"
              aria-label="Close dialog"
            >
              <X className="w-4 h-4" />
            </button>

            <div className="flex items-start space-x-4">
              <div className="w-12 h-12 rounded-2xl bg-rose-50 dark:bg-rose-950/50 border border-rose-200/80 dark:border-rose-900/60 flex items-center justify-center flex-shrink-0 text-rose-600 dark:text-rose-400 shadow-2xs">
                <Trash2 className="w-6 h-6 text-rose-600 dark:text-rose-400" />
              </div>

              <div className="flex-1 min-w-0 pt-0.5">
                <h3 className="text-base font-bold text-slate-900 dark:text-white tracking-tight">
                  Delete conversation
                </h3>
                <p className="mt-1.5 text-xs text-slate-500 dark:text-neutral-400 leading-relaxed">
                  This conversation history will be permanently deleted and cannot be undone.
                </p>

                {sessionToDelete && (
                  <div className="mt-3.5 py-2.5 px-3 rounded-xl bg-slate-50 dark:bg-neutral-800/80 border border-slate-200/80 dark:border-neutral-700 flex items-center space-x-2.5">
                    <div className="w-7 h-7 rounded-lg bg-indigo-50 dark:bg-indigo-950/60 text-indigo-700 dark:text-indigo-400 border border-indigo-200 dark:border-indigo-800/60 flex items-center justify-center flex-shrink-0">
                      <MessageSquare className="w-3.5 h-3.5" />
                    </div>
                    <div className="min-w-0 flex-1">
                      <p className="text-xs font-semibold text-slate-800 dark:text-neutral-200 truncate" title={sessionToDelete.title}>
                        {sessionToDelete.title}
                      </p>
                      <p className="text-[11px] text-slate-500 dark:text-neutral-400 truncate">
                        {sessionToDelete.message_count || 0} messages • {sessionToDelete.scope === 'all' ? 'All files' : sessionToDelete.file_name || 'Document'}
                      </p>
                    </div>
                  </div>
                )}
              </div>
            </div>

            <div className="mt-6 flex items-center justify-end space-x-2.5 pt-4 border-t border-slate-100 dark:border-neutral-800">
              <button
                type="button"
                onClick={() => setSessionToDelete(null)}
                className="px-4 py-2 rounded-xl text-xs font-semibold text-slate-700 dark:text-neutral-300 hover:text-slate-900 dark:hover:text-white bg-slate-100 dark:bg-neutral-800 hover:bg-slate-200/80 dark:hover:bg-neutral-700 transition-all cursor-pointer active:scale-95"
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

      {/* Logout Confirmation Modal */}
      <ConfirmModal
        isOpen={showLogoutConfirm}
        onClose={() => setShowLogoutConfirm(false)}
        onConfirm={handleConfirmLogout}
        title="Are you sure want to logout"
        description="You will need to sign in again to access your account."
        icon={LogOut}
        iconVariant="rose"
        confirmText="Yes, Log out"
        confirmVariant="rose"
        confirmIcon={LogOut}
        isLoading={isLoggingOut}
        loadingText="Signing out..."
        user={user}
      />
    </>
  );
}
