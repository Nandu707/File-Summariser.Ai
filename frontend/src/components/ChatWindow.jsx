import React, { useState, useRef, useEffect } from 'react';
import axios from 'axios';
import ReactMarkdown from 'react-markdown';
import DocumentPageModal from './DocumentPageModal';
import { API_BASE_URL } from '../api';
import {
  Send,
  Bot,
  User,
  Copy,
  Check,
  Loader2,
  Sparkles,
  ArrowUpRight,
  Trash2,
  FileText,
  Layers,
  BookOpen,
  ArrowRight,
  ExternalLink,
  Plus,
  Edit2
} from 'lucide-react';

export function cleanInlineSources(text) {
  if (!text || typeof text !== 'string') return text;

  const n = text.length;
  const result = [];
  let i = 0;
  while (i < n) {
    if (text[i] === '(' || text[i] === '[') {
      const opener = text[i];
      const closer = opener === '(' ? ')' : ']';
      const sub = text.slice(i, i + 50).toLowerCase();
      const isCitation = [
        'source:', 'sources:', 'source :', 'sources :', 'source -', 'sources -',
        'excerpt', 'see excerpt', 'doc:', 'document:', 'page ', 'pages ', 'p. ', 'pp. '
      ].some((kw) => sub.startsWith(opener + kw));

      if (isCitation) {
        let depth = 1;
        let j = i + 1;
        while (j < n && depth > 0) {
          if (text[j] === opener) depth++;
          else if (text[j] === closer) depth--;
          j++;
        }
        while (result.length > 0 && (result[result.length - 1] === ' ' || result[result.length - 1] === '\t')) {
          result.pop();
        }
        i = j;
        continue;
      }
    }
    result.push(text[i]);
    i++;
  }

  let cleaned = result.join('');
  cleaned = cleaned.replace(/^\s*(?:Sources?|Excerpts?)\s*:.*$/gim, '');
  cleaned = cleaned.replace(/\bSources?:\s*\[?Excerpt[^.\n]+\]?/gi, '');
  cleaned = cleaned.replace(/\[Excerpt\s*\d+[^\]]*\]/gi, '');
  cleaned = cleaned.replace(/\s*[\(\[]\s*(?:Page|Pages|p\.|pp\.)\s*\d+(?:\s*[-–,]\s*\d+)*\s*[\)\]]/gi, '');
  cleaned = cleaned.replace(/^\s*[-*•]\s*(?:\*\*)?\(?(?:Page|Pages|p\.|pp\.)\s*\d+(?:\s*[-–,]\s*\d+)*\)?(?:\*\*)?:?\s*/gim, '- ');
  cleaned = cleaned.replace(/^\s*(?:Page|Pages)\s*\d+(?:\s*[-–,]\s*\d+)*:?\s*/gim, '');
  cleaned = cleaned.replace(/^\s*[-*•]\s*:\s*/gim, '- ');
  cleaned = cleaned.replace(/\(\s*\)/g, '');
  cleaned = cleaned.replace(/\[\s*\]/g, '');
  cleaned = cleaned.replace(/\s+([.,;:!?])/g, '$1');
  cleaned = cleaned.replace(/(?<!\.)\.\s*\.(?!\.)/g, '.');
  cleaned = cleaned.replace(/\*\*/g, '');
  cleaned = cleaned.replace(/[ \t]+/g, ' ');
  cleaned = cleaned.replace(/\n{3,}/g, '\n\n');
  return cleaned.trim();
}

export default function ChatWindow({
  activeSessionId = 'all',
  activeSession = null,
  activeDocId = 'all',
  documents = [],
  sessions = [],
  onSelectSession,
  onCreateSession,
  onRenameSession,
  onDeleteSession,
  onNavigateTab,
  onViewPage,
  onLoadingChange,
  onSessionActivity
}) {
  const effectiveSessionId = activeSessionId || activeDocId || 'all';
  const [messages, setMessages] = useState([]);
  const [question, setQuestion] = useState('');
  const [loading, setLoading] = useState(false);
  const [loadingChat, setLoadingChat] = useState(false);
  const [error, setError] = useState(null);
  const [copiedIdx, setCopiedIdx] = useState(null);
  const [suggestedQuestions, setSuggestedQuestions] = useState([]);
  const [loadingSuggestions, setLoadingSuggestions] = useState(false);
  const [isEditingTitle, setIsEditingTitle] = useState(false);
  const [editTitle, setEditTitle] = useState('');
  const [isResetting, setIsResetting] = useState(false);
  const [localModalState, setLocalModalState] = useState({
    isOpen: false,
    page: 1,
    docId: null,
    filename: ''
  });

  const chatContainerRef = useRef(null);
  const messagesEndRef = useRef(null);
  const inputRef = useRef(null);

  const docCount = documents.length;
  const isAllDocs = activeSession ? activeSession.scope === 'all' : effectiveSessionId === 'all';
  const isFileDeleted = Boolean(activeSession?.is_file_deleted);

  const sessionTitle = activeSession?.title || (isAllDocs ? 'All files' : activeSession?.file_name || 'Chat');

  const scrollToBottom = () => {
    if (chatContainerRef.current) {
      chatContainerRef.current.scrollTo({
        top: chatContainerRef.current.scrollHeight,
        behavior: 'smooth',
      });
    }
  };

  useEffect(() => {
    scrollToBottom();
  }, [messages, loading]);

  // Load chat session messages when effectiveSessionId changes
  useEffect(() => {
    setError(null);
    setSuggestedQuestions([]);
    inputRef.current?.focus();

    let isMounted = true;

    const fetchChatMessages = async () => {
      setLoadingChat(true);
      try {
        const res = await axios.get(`${API_BASE_URL}/api/chats/${effectiveSessionId}`);
        if (isMounted && res.data && Array.isArray(res.data.messages)) {
          setMessages(res.data.messages);
        }
      } catch (err) {
        // Fallback to legacy endpoint if chat session was not yet in sessions table
        try {
          const resLegacy = await axios.get(`${API_BASE_URL}/api/documents/${effectiveSessionId}/chat`);
          if (isMounted && resLegacy.data && Array.isArray(resLegacy.data.messages)) {
            setMessages(resLegacy.data.messages);
          }
        } catch (lErr) {
          if (isMounted) {
            console.error('Failed to fetch chat messages:', err);
            setMessages([]);
          }
        }
      } finally {
        if (isMounted) {
          setLoadingChat(false);
        }
      }
    };

    fetchChatMessages();

    // Fetch suggested questions for the session scope
    const fetchQuestions = async () => {
      if (docCount === 0) {
        setSuggestedQuestions([]);
        return;
      }
      setLoadingSuggestions(true);
      try {
        const targetId = isAllDocs ? 'all' : (activeSession?.file_id || effectiveSessionId);
        const res = await axios.get(`${API_BASE_URL}/api/documents/${targetId}/suggested-questions`);
        if (isMounted && res.data && Array.isArray(res.data.suggested_questions) && res.data.suggested_questions.length > 0) {
          setSuggestedQuestions(res.data.suggested_questions);
        }
      } catch (err) {
        if (isMounted) {
          if (isAllDocs) {
            setSuggestedQuestions([
              'Summarize the key topics covered across all uploaded files.',
              'What are the primary conclusions and metrics found in the documents?',
              'Compare and synthesize the main findings from the uploaded documents.'
            ]);
          } else {
            const fn = activeSession?.file_name || 'this document';
            setSuggestedQuestions([
              `What is the central topic and summary of ${fn}?`,
              `What key numbers, statistics, or metrics are mentioned in ${fn}?`,
              `What are the primary conclusions and next steps in ${fn}?`
            ]);
          }
        }
      } finally {
        if (isMounted) {
          setLoadingSuggestions(false);
        }
      }
    };

    fetchQuestions();

    return () => {
      isMounted = false;
    };
  }, [effectiveSessionId, isAllDocs, activeSession?.file_id, docCount]);

  // Global shortcut: Ctrl+N or Cmd+N starts a fresh chat smoothly
  useEffect(() => {
    const handleGlobalKeyDown = (e) => {
      if ((e.ctrlKey || e.metaKey) && e.key.toLowerCase() === 'n') {
        e.preventDefault();
        handleNewChat();
      }
    };
    window.addEventListener('keydown', handleGlobalKeyDown);
    return () => window.removeEventListener('keydown', handleGlobalKeyDown);
  }, [loading, isResetting, effectiveSessionId]);

  const handleNewChat = async () => {
    if (loading || isResetting) return;
    if (onCreateSession) {
      onCreateSession({
        scope: isAllDocs ? 'all' : 'file',
        file_id: activeSession?.file_id,
        file_name: activeSession?.file_name,
        title: isAllDocs ? 'New chat' : `Chat: ${activeSession?.file_name || 'Document'}`
      });
    }
  };

  const handleDeleteChatClick = async () => {
    const confirmed = window.confirm(
      `Are you sure you want to permanently delete the chat history for "${sessionTitle}"? This cannot be undone.`
    );
    if (confirmed) {
      setMessages([]);
      if (onDeleteSession) {
        onDeleteSession(effectiveSessionId);
      } else {
        try {
          await axios.delete(`${API_BASE_URL}/api/chats/${effectiveSessionId}`);
        } catch (e) {
          console.error('Delete chat error:', e);
        }
      }
    }
  };

  const handleStartRename = () => {
    setEditTitle(sessionTitle);
    setIsEditingTitle(true);
  };

  const handleSaveRename = () => {
    if (editTitle.trim() && onRenameSession) {
      onRenameSession(effectiveSessionId, editTitle.trim());
    }
    setIsEditingTitle(false);
  };

  const handleSend = async (customPrompt) => {
    if (isFileDeleted) {
      setError('This file was deleted. You can read the history but cannot ask new questions.');
      return;
    }

    const qToSend = (customPrompt || question).trim();
    if (!qToSend || loading) return;

    setError(null);
    setQuestion('');

    const userMessage = {
      role: 'user',
      content: qToSend,
      text: qToSend,
      time: new Date().toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' }),
    };

    setMessages((prev) => [...prev, userMessage]);
    setLoading(true);
    onLoadingChange?.(true);

    try {
      const response = await axios.post(
        `${API_BASE_URL}/api/ask`,
        {
          chat_id: effectiveSessionId,
          doc_id: activeSession?.file_id || (isAllDocs ? 'all' : effectiveSessionId),
          question: qToSend,
        },
        {
          headers: { 'Content-Type': 'application/json' },
          timeout: 90000,
        }
      );

      const data = response.data; // { answer, sources, source_documents, source_details, suggested_questions }
      const cleanAns = cleanInlineSources(data.answer || '');

      const botMessage = {
        role: 'assistant',
        content: cleanAns,
        text: cleanAns,
        sources: Array.isArray(data.sources) ? data.sources : [],
        source_documents: Array.isArray(data.source_documents) ? data.source_documents : [],
        source_details: Array.isArray(data.source_details) ? data.source_details : [],
        suggested_questions: Array.isArray(data.suggested_questions) ? data.suggested_questions : [],
        time: new Date().toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' }),
      };

      setMessages((prev) => [...prev, botMessage]);
      onSessionActivity?.();
    } catch (err) {
      const msg = err.response?.data?.detail || err.message || 'Failed to retrieve answer from backend.';
      setError(msg);
      setMessages((prev) => [
        ...prev,
        {
          role: 'assistant',
          isError: true,
          content: `Error: ${msg}`,
          text: `Error: ${msg}`,
          sources: [],
          source_details: [],
          time: new Date().toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' }),
        },
      ]);
    } finally {
      setLoading(false);
      onLoadingChange?.(false);
    }
  };

  const handleKeyDown = (e) => {
    if (e.key === 'Enter' && !e.shiftKey) {
      e.preventDefault();
      handleSend();
    }
  };

  const copyToClipboard = (text, idx) => {
    navigator.clipboard.writeText(cleanInlineSources(text));
    setCopiedIdx(idx);
    setTimeout(() => setCopiedIdx(null), 2000);
  };

  const handleOpenSourcePdf = (docId, pageNum, filename) => {
    let targetDocId = docId;
    let targetFilename = filename;

    if (!targetDocId || targetDocId === 'all') {
      if (!isAllDocs && activeSession?.file_id) {
        targetDocId = activeSession.file_id;
        targetFilename = activeSession.file_name;
      } else if (filename && Array.isArray(documents) && documents.length > 0) {
        const found = documents.find((d) => d.filename === filename);
        if (found) {
          targetDocId = found.doc_id;
          targetFilename = found.filename;
        }
      }
    }

    if (!targetDocId && Array.isArray(documents) && documents.length > 0) {
      targetDocId = documents[0].doc_id;
      targetFilename = documents[0].filename;
    }

    if (!targetDocId) return;

    const page = pageNum || 1;
    if (onViewPage) {
      onViewPage(targetDocId, page, targetFilename);
    } else {
      setLocalModalState({
        isOpen: true,
        docId: targetDocId,
        page: page,
        filename: targetFilename || 'Document'
      });
    }
  };

  const defaultSamplePrompts = isAllDocs
    ? [
        'Summarize the key topics and findings across all uploaded documents.',
        'What key numbers, statistics, or metrics are mentioned in the files?',
        'What are the primary conclusions and recommended next steps?'
      ]
    : [
        `What is the central topic and summary of ${sessionTitle}?`,
        `What key facts, data, or events are detailed in ${sessionTitle}?`,
        `What are the primary conclusions and takeaways in ${sessionTitle}?`
      ];

  return (
    <section className="flex-1 min-h-0 bg-white rounded-2xl border border-slate-200/90 shadow-sm flex flex-col h-full overflow-hidden relative">
      {/* Top Header - Fixed Non-Wrapping Header */}
      <div className="flex-shrink-0 px-4 sm:px-6 py-3.5 border-b border-slate-200/90 bg-slate-50/80 backdrop-blur-md flex items-center justify-between gap-3 overflow-hidden select-none">
        <div className="min-w-0 flex-1 flex items-center space-x-3">
          <div className="p-2 rounded-xl bg-indigo-50 text-indigo-600 border border-indigo-200/80 flex-shrink-0 shadow-2xs">
            <Bot className="w-4 h-4" />
          </div>
          <div className="min-w-0 flex-1">
            <div className="flex items-center space-x-2">
              {isEditingTitle ? (
                <input
                  type="text"
                  value={editTitle}
                  autoFocus
                  onChange={(e) => setEditTitle(e.target.value)}
                  onKeyDown={(e) => {
                    if (e.key === 'Enter') handleSaveRename();
                    if (e.key === 'Escape') setIsEditingTitle(false);
                  }}
                  onBlur={handleSaveRename}
                  className="bg-white border border-indigo-400 rounded px-2 py-0.5 text-sm font-bold text-slate-900 focus:outline-none max-w-xs"
                />
              ) : (
                <div className="flex items-center space-x-1.5 min-w-0">
                  <h2 className="text-sm font-bold text-slate-900 tracking-tight truncate max-w-sm" title={sessionTitle}>
                    {sessionTitle}
                  </h2>
                  <button
                    onClick={handleStartRename}
                    className="p-1 text-slate-400 hover:text-slate-700 rounded hover:bg-slate-200/60 transition-colors"
                    title="Rename chat"
                  >
                    <Edit2 className="w-3 h-3" />
                  </button>
                </div>
              )}

              {isFileDeleted ? (
                <span className="text-[10px] font-bold px-2 py-0.5 rounded-full bg-rose-100 text-rose-700 border border-rose-300 flex-shrink-0">
                  File deleted • Read-only
                </span>
              ) : isAllDocs ? (
                <span className="text-[10px] font-semibold px-2 py-0.5 rounded-full bg-indigo-50 text-indigo-700 border border-indigo-200/80 flex-shrink-0">
                  All files ({docCount} active)
                </span>
              ) : (
                <span className="text-[10px] font-semibold px-2 py-0.5 rounded-full bg-slate-100 text-slate-700 border border-slate-200 flex-shrink-0 truncate max-w-[140px]">
                  {activeSession?.file_name}
                </span>
              )}
            </div>
            <p className="text-[11px] text-slate-500 truncate">
              {isFileDeleted
                ? 'File content purged from index & LLM context • Chat thread is preserved'
                : isAllDocs
                ? `Searching across all active documents (${docCount} ${docCount === 1 ? 'file' : 'files'})`
                : `Scoped to: ${activeSession?.file_name || sessionTitle}`}
            </p>
          </div>
        </div>

        {/* Fixed Right Control Cluster */}
        <div className="flex-shrink-0 flex items-center space-x-2">
          {/* Explicit 'Delete Chat' Button */}
          {messages.length > 0 && (
            <button
              onClick={handleDeleteChatClick}
              disabled={loading || isResetting}
              title={`Permanently delete the chat history for "${sessionTitle}"`}
              className="inline-flex items-center space-x-1 px-2.5 py-1.5 rounded-xl text-xs font-semibold text-rose-700 hover:text-rose-800 bg-rose-50/80 hover:bg-rose-100 border border-rose-200/90 transition-all duration-200 disabled:opacity-50 cursor-pointer active:scale-95"
            >
              <Trash2 className="w-3.5 h-3.5 text-rose-600" />
              <span className="hidden sm:inline">Delete chat</span>
            </button>
          )}

          {/* New Chat Button */}
          <button
            onClick={handleNewChat}
            disabled={loading || isResetting}
            title="Start a new chat session"
            className="group relative inline-flex items-center space-x-1.5 px-3.5 py-1.5 rounded-xl text-xs font-semibold text-white bg-gradient-to-r from-indigo-600 via-indigo-600 to-blue-600 hover:from-indigo-500 hover:via-indigo-500 hover:to-blue-500 shadow-xs shadow-indigo-600/25 hover:shadow-md hover:shadow-indigo-500/30 active:scale-95 transition-all duration-300 ease-out cursor-pointer disabled:opacity-50 select-none overflow-hidden"
          >
            <Plus className="w-3.5 h-3.5 text-white flex-shrink-0 transition-transform duration-300 ease-out group-hover:rotate-90 group-hover:scale-110" />
            <span className="tracking-tight whitespace-nowrap">New Chat</span>
          </button>
        </div>
      </div>

      {/* Read-Only Banner for Soft-Deleted Files */}
      {isFileDeleted && (
        <div className="flex-shrink-0 mx-4 sm:mx-6 mt-3 p-3 rounded-xl bg-amber-50/90 border border-amber-200 text-amber-950 text-xs flex items-center justify-between gap-3 shadow-2xs">
          <div className="flex items-center space-x-2.5 min-w-0">
            <span className="text-[10px] font-bold uppercase px-2 py-0.5 rounded-full bg-amber-200 text-amber-900 border border-amber-300 flex-shrink-0">
              File deleted
            </span>
            <p className="text-[11px] truncate text-amber-900">
              This file was deleted. You can read the history but cannot ask new questions.
            </p>
          </div>
          <button
            onClick={handleDeleteChatClick}
            className="inline-flex items-center space-x-1 px-2.5 py-1 text-xs font-semibold text-rose-700 bg-white hover:bg-rose-50 border border-rose-200 rounded-lg flex-shrink-0 transition-colors shadow-2xs cursor-pointer active:scale-95"
          >
            <Trash2 className="w-3 h-3 text-rose-600" />
            <span>Delete chat</span>
          </button>
        </div>
      )}

      {/* Messages Scroll Area */}
      <div
        ref={chatContainerRef}
        className="flex-1 min-h-0 overflow-y-auto custom-scrollbar p-4 sm:p-6 space-y-6 bg-gradient-to-b from-white via-white to-slate-50/40"
      >
        {docCount === 0 && isAllDocs && messages.length === 0 ? (
          /* Empty State: No Documents Uploaded */
          <div className="h-full flex flex-col items-center justify-center text-center px-4 max-w-md mx-auto py-12">
            <div className="w-14 h-14 rounded-2xl bg-indigo-50 border border-indigo-100 text-indigo-600 flex items-center justify-center mb-4 shadow-sm">
              <Layers className="w-7 h-7" />
            </div>
            <h3 className="text-base font-bold text-slate-900">No Documents Uploaded Yet</h3>
            <p className="text-xs text-slate-500 mt-2 leading-relaxed">
              Upload your PDF, Word (.docx), or plain text (.txt) files in the <strong>Documents & Upload</strong> tab. The assistant will index and search from all uploaded files to answer your questions.
            </p>
            <button
              onClick={() => onNavigateTab && onNavigateTab('documents')}
              className="mt-5 flex items-center space-x-2 px-5 py-2.5 rounded-xl text-xs font-semibold text-white bg-gradient-to-r from-indigo-600 via-indigo-600 to-blue-600 hover:from-indigo-500 hover:to-blue-500 shadow-sm shadow-indigo-600/20 active:scale-95 transition-all"
            >
              <span>Go to Documents & Upload</span>
              <ArrowRight className="w-3.5 h-3.5" />
            </button>
          </div>
        ) : loadingChat ? (
          <div className="h-full flex flex-col items-center justify-center space-y-3 py-16">
            <Loader2 className="w-7 h-7 text-indigo-600 animate-spin" />
            <p className="text-xs text-slate-500 font-medium">Loading conversation history...</p>
          </div>
        ) : messages.length === 0 ? (
          /* Empty / Welcome State with Suggested Questions */
          <div className="h-full flex flex-col justify-center items-center text-center px-4 max-w-lg mx-auto py-10">
            <div className="w-12 h-12 rounded-2xl bg-indigo-50 border border-indigo-100 text-indigo-600 flex items-center justify-center mb-4 shadow-sm">
              <Sparkles className="w-6 h-6" />
            </div>
            <h3 className="text-base font-bold text-slate-900">
              {isAllDocs ? `Ask anything across your ${docCount} active files` : `Chat about ${sessionTitle}`}
            </h3>
            <p className="text-xs text-slate-500 mt-1 mb-6">
              The LLM will automatically retrieve top vector excerpts from active files and synthesize accurate answers with citations.
            </p>

            <div className="w-full space-y-2 text-left">
              <div className="flex items-center justify-between mb-1">
                <p className="text-[11px] font-semibold text-slate-500 uppercase tracking-wider flex items-center space-x-1.5">
                  <Sparkles className="w-3.5 h-3.5 text-indigo-600" />
                  <span>Suggested Questions:</span>
                </p>
                {loadingSuggestions && (
                  <span className="text-[10px] text-indigo-600 flex items-center space-x-1 animate-pulse">
                    <Loader2 className="w-3 h-3 animate-spin" />
                    <span>Analyzing...</span>
                  </span>
                )}
              </div>

              {(suggestedQuestions.length > 0 ? suggestedQuestions : defaultSamplePrompts).map((prompt, idx) => (
                <button
                  key={idx}
                  onClick={() => handleSend(prompt)}
                  className="w-full flex items-center justify-between p-3 rounded-xl bg-white hover:bg-indigo-50/70 border border-slate-200 hover:border-indigo-300 text-xs text-slate-700 hover:text-indigo-900 transition-all group shadow-2xs active:scale-[0.99] cursor-pointer"
                >
                  <span className="truncate pr-2 font-medium">{prompt}</span>
                  <ArrowUpRight className="w-3.5 h-3.5 text-slate-400 group-hover:text-indigo-600 flex-shrink-0 transition-colors" />
                </button>
              ))}
            </div>
          </div>
        ) : (
          /* Active Chat Stream */
          messages.map((msg, idx) => (
            <div
              key={idx}
              className={`flex items-start space-x-3 animate-fade-in ${
                msg.role === 'user' ? 'justify-end' : 'justify-start'
              }`}
            >
              {msg.role === 'assistant' && (
                <div className="w-8 h-8 rounded-xl bg-gradient-to-tr from-indigo-600 to-blue-600 text-white flex items-center justify-center flex-shrink-0 shadow-xs mt-1">
                  <Bot className="w-4 h-4" />
                </div>
              )}

              <div
                className={`max-w-2xl rounded-2xl p-4 text-xs sm:text-sm leading-relaxed ${
                  msg.role === 'user'
                    ? 'bg-gradient-to-r from-indigo-600 via-indigo-600 to-blue-600 text-white shadow-xs rounded-tr-xs'
                    : msg.isError
                    ? 'bg-rose-50 border border-rose-200 text-rose-800 rounded-tl-xs'
                    : 'bg-white border border-slate-200/90 text-slate-800 shadow-xs rounded-tl-xs'
                }`}
              >
                {/* Markdown Rendered Content */}
                {msg.role === 'assistant' && !msg.isError ? (
                  <div className="prose prose-slate prose-sm max-w-none space-y-2">
                    <ReactMarkdown>{cleanInlineSources(msg.content || msg.text || '')}</ReactMarkdown>
                  </div>
                ) : (
                  <div className="whitespace-pre-wrap">{cleanInlineSources(msg.content || msg.text || '')}</div>
                )}

                {/* Sourced Documents / Pages Badges with Deleted File Marker */}
                {msg.role === 'assistant' && !msg.isError && (
                  (Array.isArray(msg.source_details) && msg.source_details.length > 0) ||
                  (Array.isArray(msg.sources) && msg.sources.length > 0)
                ) && (
                  <div className="mt-3.5 pt-3 border-t border-slate-100 space-y-1.5">
                    <p className="text-[11px] font-semibold text-slate-500 uppercase tracking-wider flex items-center space-x-1">
                      <BookOpen className="w-3.5 h-3.5 text-indigo-600" />
                      <span>Sourced From:</span>
                    </p>
                    <div className="flex flex-wrap gap-1.5">
                      {Array.isArray(msg.source_details) && msg.source_details.length > 0 ? (
                        msg.source_details.map((detail, sIdx) => {
                          const fid = detail.file_id || detail.doc_id;
                          const fn = detail.filename || detail.file_name || 'Document';
                          const isSourceDeleted =
                            Boolean(detail.is_deleted) ||
                            (fid && !documents.some((d) => d.doc_id === fid));

                          return isSourceDeleted ? (
                            <span
                              key={sIdx}
                              className="inline-flex items-center space-x-1.5 px-2.5 py-1 rounded-lg text-xs font-medium bg-slate-100 text-slate-500 border border-slate-200"
                              title="This file was deleted from active storage"
                            >
                              <FileText className="w-3 h-3 text-slate-400" />
                              <span>{fn} (deleted) • Page {detail.page}</span>
                            </span>
                          ) : (
                            <button
                              key={sIdx}
                              type="button"
                              onClick={() => handleOpenSourcePdf(fid, detail.page, fn)}
                              className="inline-flex items-center space-x-1.5 px-2.5 py-1 rounded-lg text-xs font-semibold bg-indigo-50 hover:bg-indigo-100 text-indigo-700 border border-indigo-200/80 hover:border-indigo-300 transition-all active:scale-95 shadow-2xs group cursor-pointer"
                              title={`View ${fn} at Page ${detail.page} inside site`}
                            >
                              <FileText className="w-3 h-3 text-indigo-500 group-hover:text-indigo-600" />
                              <span>{fn ? `${fn} • ` : ''}Page {detail.page}</span>
                              <ExternalLink className="w-3 h-3 text-indigo-400 group-hover:text-indigo-600 ml-0.5" />
                            </button>
                          );
                        })
                      ) : (
                        msg.sources.map((pageNum, sIdx) => {
                          let targetDocId = !isAllDocs ? activeSession?.file_id : null;
                          let fn = '';
                          if (!targetDocId && Array.isArray(msg.source_documents) && msg.source_documents.length > 0) {
                            const found = documents.find((d) => d.filename === msg.source_documents[0]);
                            if (found) {
                              targetDocId = found.doc_id;
                              fn = found.filename;
                            }
                          }
                          return (
                            <button
                              key={sIdx}
                              type="button"
                              onClick={() => handleOpenSourcePdf(targetDocId, pageNum, fn)}
                              className="inline-flex items-center space-x-1.5 px-2.5 py-1 rounded-lg text-xs font-semibold bg-indigo-50 hover:bg-indigo-100 text-indigo-700 border border-indigo-200/80 hover:border-indigo-300 transition-all active:scale-95 shadow-2xs group cursor-pointer"
                            >
                              <FileText className="w-3 h-3 text-indigo-500 group-hover:text-indigo-600" />
                              <span>{fn ? `${fn} • ` : ''}Page {pageNum}</span>
                              <ExternalLink className="w-3 h-3 text-indigo-400 group-hover:text-indigo-600 ml-0.5" />
                            </button>
                          );
                        })
                      )}
                    </div>
                  </div>
                )}

                {/* Sequential Follow-up Questions Suggested by LLM */}
                {msg.role === 'assistant' && !msg.isError && Array.isArray(msg.suggested_questions) && msg.suggested_questions.length > 0 && !isFileDeleted && (
                  <div className="mt-3.5 pt-3 border-t border-slate-100">
                    <div className="flex items-center space-x-1.5 text-[11px] font-semibold text-indigo-700 mb-2">
                      <Sparkles className="w-3.5 h-3.5 text-indigo-600 animate-pulse" />
                      <span>Suggested Follow-up Questions:</span>
                    </div>
                    <div className="grid grid-cols-1 gap-1.5">
                      {msg.suggested_questions.map((seqQ, sIdx) => (
                        <button
                          key={sIdx}
                          type="button"
                          onClick={() => handleSend(seqQ)}
                          disabled={loading || isFileDeleted}
                          className="group w-full flex items-center justify-between p-2 sm:p-2.5 rounded-xl bg-slate-50/90 hover:bg-indigo-50/80 border border-slate-200/80 hover:border-indigo-300 text-left text-xs text-slate-700 hover:text-indigo-900 transition-all shadow-2xs active:scale-[0.99] disabled:opacity-50 cursor-pointer"
                        >
                          <span className="truncate pr-2 font-medium">{seqQ}</span>
                          <ArrowUpRight className="w-3.5 h-3.5 text-slate-400 group-hover:text-indigo-600 group-hover:translate-x-0.5 group-hover:-translate-y-0.5 transition-transform flex-shrink-0" />
                        </button>
                      ))}
                    </div>
                  </div>
                )}

                {/* Footer details */}
                <div className={`mt-2.5 flex items-center justify-between text-[10px] ${
                  msg.role === 'user' ? 'text-indigo-100' : 'text-slate-400'
                }`}>
                  <span>{msg.time || msg.timestamp}</span>
                  {msg.role === 'assistant' && !msg.isError && (
                    <button
                      onClick={() => copyToClipboard(msg.content || msg.text, idx)}
                      className="hover:text-slate-700 transition-colors flex items-center space-x-1 cursor-pointer"
                      title="Copy response"
                    >
                      {copiedIdx === idx ? (
                        <>
                          <Check className="w-3 h-3 text-emerald-600" />
                          <span className="text-emerald-600 font-medium">Copied</span>
                        </>
                      ) : (
                        <>
                          <Copy className="w-3 h-3 text-slate-400" />
                          <span>Copy</span>
                        </>
                      )}
                    </button>
                  )}
                </div>
              </div>

              {msg.role === 'user' && (
                <div className="w-8 h-8 rounded-xl bg-slate-100 text-slate-600 flex items-center justify-center flex-shrink-0 border border-slate-200 mt-1 shadow-2xs">
                  <User className="w-4 h-4" />
                </div>
              )}
            </div>
          ))
        )}

        {/* Loading Spinner */}
        {loading && (
          <div className="flex items-start space-x-3 animate-fade-in">
            <div className="w-8 h-8 rounded-xl bg-gradient-to-tr from-indigo-600 to-blue-600 text-white flex items-center justify-center flex-shrink-0 shadow-xs mt-1">
              <Bot className="w-4 h-4" />
            </div>
            <div className="bg-white border border-slate-200/90 rounded-2xl rounded-tl-xs p-4 text-xs text-slate-700 shadow-xs space-y-1.5">
              <div className="flex items-center space-x-2 text-indigo-600 font-semibold">
                <Loader2 className="w-4 h-4 animate-spin" />
                <span>Searching ChromaDB Across Active Files...</span>
              </div>
              <p className="text-[11px] text-slate-400">
                Retrieving top vector excerpts using reciprocal rank fusion and synthesizing answer.
              </p>
            </div>
          </div>
        )}

        <div ref={messagesEndRef} />
      </div>

      {/* Input Form with Disabled State for Deleted Files */}
      <div className="flex-shrink-0 p-4 border-t border-slate-200/90 bg-white/95 backdrop-blur-md">
        <form
          onSubmit={(e) => {
            e.preventDefault();
            handleSend();
          }}
          className="relative flex items-end"
        >
          <textarea
            ref={inputRef}
            rows={2}
            value={question}
            onChange={(e) => setQuestion(e.target.value)}
            onKeyDown={handleKeyDown}
            disabled={loading || isFileDeleted}
            placeholder={
              isFileDeleted
                ? 'This file was deleted. You can read the history but cannot ask new questions.'
                : isAllDocs
                ? 'Ask a question across all uploaded documents... (Enter to send, Shift+Enter for newline)'
                : `Ask a question about ${sessionTitle}... (Enter to send, Shift+Enter for newline)`
            }
            className="w-full bg-slate-50/60 focus:bg-white border border-slate-200 focus:border-indigo-500 focus:ring-2 focus:ring-indigo-100 custom-scrollbar rounded-xl px-4 py-3 pr-24 text-xs sm:text-sm text-slate-900 placeholder:text-slate-400 focus:outline-none transition-all resize-none min-h-[52px] max-h-36 overflow-y-auto disabled:opacity-60 disabled:cursor-not-allowed"
          />

          <div className="absolute right-2.5 bottom-2.5 flex items-center">
            <button
              type="submit"
              disabled={!question.trim() || loading || isFileDeleted}
              className="flex items-center space-x-1.5 px-4 py-2 rounded-lg text-xs font-semibold text-white bg-gradient-to-r from-indigo-600 via-indigo-600 to-blue-600 hover:from-indigo-500 hover:to-blue-500 disabled:opacity-40 disabled:cursor-not-allowed shadow-xs transition-all active:scale-95 cursor-pointer"
            >
              {loading ? (
                <Loader2 className="w-3.5 h-3.5 animate-spin" />
              ) : (
                <>
                  <span>Ask</span>
                  <Send className="w-3 h-3" />
                </>
              )}
            </button>
          </div>
        </form>
        <div className="mt-2 flex items-center justify-between text-[11px] text-slate-400 px-1">
          <span>
            {isFileDeleted
              ? 'Status: File deleted (Read-only chat archive)'
              : isAllDocs
              ? 'Searching: All active indexed files in ChromaDB'
              : `Scope: ${sessionTitle}`}
          </span>
          <span>{isFileDeleted ? 'Chat is read-only' : 'Shift+Enter for newline'}</span>
        </div>
      </div>

      {!onViewPage && (
        <DocumentPageModal
          isOpen={localModalState.isOpen}
          onClose={() => setLocalModalState((prev) => ({ ...prev, isOpen: false }))}
          docId={localModalState.docId}
          initialPage={localModalState.page}
          filename={localModalState.filename}
        />
      )}
    </section>
  );
}
