import React, { useState, useRef, useEffect } from 'react';
import axios from 'axios';
import ReactMarkdown from 'react-markdown';
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
  ChevronDown
} from 'lucide-react';

export default function ChatWindow({
  activeDocId = 'all',
  documents = [],
  onSelectDoc,
  onNavigateTab,
  onViewPage,
  onLoadingChange
}) {
  const [messages, setMessages] = useState([]);
  const [question, setQuestion] = useState('');
  const [loading, setLoading] = useState(false);
  const [loadingChat, setLoadingChat] = useState(false);
  const [error, setError] = useState(null);
  const [copiedIdx, setCopiedIdx] = useState(null);
  const [suggestedQuestions, setSuggestedQuestions] = useState([]);
  const [loadingSuggestions, setLoadingSuggestions] = useState(false);
  const chatContainerRef = useRef(null);
  const messagesEndRef = useRef(null);
  const inputRef = useRef(null);

  const docCount = documents.length;
  const isAllDocs = !activeDocId || activeDocId === 'all';
  const activeDocument = isAllDocs ? null : documents.find((d) => d.doc_id === activeDocId);
  const activeDocTitle = isAllDocs
    ? `All Uploaded Documents (${docCount} ${docCount === 1 ? 'file' : 'files'})`
    : activeDocument?.filename || 'Selected Document';

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

  // Load persistent chat history and suggested questions when activeDocId changes
  useEffect(() => {
    setError(null);
    inputRef.current?.focus();

    let isMounted = true;
    const effectiveId = activeDocId || 'all';

    // Fetch persistent chat history
    const fetchChatHistory = async () => {
      setLoadingChat(true);
      try {
        const res = await axios.get(`http://localhost:8000/api/documents/${effectiveId}/chat`);
        if (isMounted && res.data && Array.isArray(res.data.messages)) {
          setMessages(res.data.messages);
        }
      } catch (err) {
        if (isMounted) {
          console.error('Failed to fetch chat history:', err);
          setMessages([]);
        }
      } finally {
        if (isMounted) {
          setLoadingChat(false);
        }
      }
    };

    fetchChatHistory();

    // Fetch dynamic questions tailored to the active selection (all or specific file)
    const fetchQuestions = async () => {
      if (docCount === 0) {
        setSuggestedQuestions([]);
        return;
      }
      setLoadingSuggestions(true);
      try {
        const res = await axios.get(`http://localhost:8000/api/documents/${effectiveId}/suggested-questions`);
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
            const fn = activeDocument?.filename || 'this document';
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
  }, [activeDocId]);

  const handleClearChat = async () => {
    if (loading) return;
    const effectiveId = activeDocId || 'all';
    try {
      await axios.delete(`http://localhost:8000/api/documents/${effectiveId}/chat`);
      setMessages([]);
    } catch (err) {
      console.error('Failed to clear chat history:', err);
    }
  };

  const handleSend = async (customPrompt) => {
    const qToSend = (customPrompt || question).trim();
    if (!qToSend || loading) return;

    setError(null);
    setQuestion('');

    const userMessage = {
      role: 'user',
      content: qToSend,
      time: new Date().toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' }),
    };

    setMessages((prev) => [...prev, userMessage]);
    setLoading(true);
    onLoadingChange?.(true);

    try {
      const response = await axios.post(
        'http://localhost:8000/api/ask',
        {
          doc_id: activeDocId || 'all',
          question: qToSend,
        },
        {
          headers: { 'Content-Type': 'application/json' },
          timeout: 90000,
        }
      );

      const data = response.data; // { answer, sources, source_documents, source_details, suggested_questions }

      const botMessage = {
        role: 'assistant',
        content: data.answer || '',
        sources: Array.isArray(data.sources) ? data.sources : [],
        source_documents: Array.isArray(data.source_documents) ? data.source_documents : [],
        source_details: Array.isArray(data.source_details) ? data.source_details : [],
        suggested_questions: Array.isArray(data.suggested_questions) ? data.suggested_questions : [],
        time: new Date().toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' }),
      };

      setMessages((prev) => [...prev, botMessage]);
    } catch (err) {
      const msg = err.response?.data?.detail || err.message || 'Failed to retrieve answer from backend.';
      setError(msg);
      setMessages((prev) => [
        ...prev,
        {
          role: 'assistant',
          isError: true,
          content: `Error querying documents: ${msg}`,
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
    navigator.clipboard.writeText(text);
    setCopiedIdx(idx);
    setTimeout(() => setCopiedIdx(null), 2000);
  };

  const defaultSamplePrompts = [
    'Summarize the key topics and findings across all uploaded documents.',
    'What key numbers, statistics, or metrics are mentioned in the files?',
    'What are the primary conclusions and recommended next steps?'
  ];

  return (
    <section className="flex-1 min-h-0 bg-white rounded-2xl border border-slate-200/90 shadow-sm flex flex-col h-full overflow-hidden relative">
      {/* Top Banner / Scope Bar */}
      <div className="flex-shrink-0 px-4 sm:px-6 py-3.5 border-b border-slate-200/90 bg-slate-50/80 backdrop-blur-md flex flex-wrap items-center justify-between gap-3">
        <div className="flex items-center space-x-3">
          <div className="p-2 rounded-xl bg-indigo-50 text-indigo-600 border border-indigo-200/80">
            <Bot className="w-4 h-4" />
          </div>
          <div>
            <div className="flex items-center space-x-2">
              <h2 className="text-sm font-bold text-slate-900 tracking-tight">
                Document Q&A Assistant
              </h2>
              <span className="text-[10px] font-semibold px-2 py-0.5 rounded-full bg-indigo-50 text-indigo-700 border border-indigo-200/80">
                ChromaDB RRF
              </span>
            </div>
            <p className="text-[11px] text-slate-500">
              {docCount === 0
                ? 'No documents uploaded yet • Upload files in Documents tab'
                : isAllDocs
                ? `Searching across all ${docCount} uploaded ${docCount === 1 ? 'document' : 'documents'}`
                : `Searching specifically in: ${activeDocument?.filename}`}
            </p>
          </div>
        </div>

        {/* Search Target Selector & Clear Chat */}
        <div className="flex items-center space-x-2.5">
          {docCount > 0 && (
            <div className="relative">
              <select
                value={activeDocId || 'all'}
                onChange={(e) => onSelectDoc && onSelectDoc(e.target.value)}
                className="appearance-none bg-white border border-slate-200 hover:border-slate-300 focus:border-indigo-500 rounded-xl pl-3 pr-8 py-1.5 text-xs font-semibold text-slate-700 shadow-2xs focus:outline-none cursor-pointer"
              >
                <option value="all">🌐 All Uploaded Documents ({docCount})</option>
                {documents.map((d) => (
                  <option key={d.doc_id} value={d.doc_id}>
                    📄 {d.filename} ({d.chunks} chunks)
                  </option>
                ))}
              </select>
              <ChevronDown className="w-3.5 h-3.5 text-slate-400 absolute right-2.5 top-1/2 -translate-y-1/2 pointer-events-none" />
            </div>
          )}

          {messages.length > 0 && (
            <button
              onClick={handleClearChat}
              disabled={loading}
              title="Clear conversation history"
              className="inline-flex items-center space-x-1 px-2.5 py-1.5 rounded-xl text-xs font-medium text-slate-600 hover:text-rose-600 hover:bg-rose-50 border border-slate-200 hover:border-rose-200 transition-colors disabled:opacity-50"
            >
              <Trash2 className="w-3.5 h-3.5" />
              <span className="hidden sm:inline">Clear</span>
            </button>
          )}
        </div>
      </div>

      {/* Messages Scroll Area */}
      <div
        ref={chatContainerRef}
        className="flex-1 min-h-0 overflow-y-auto custom-scrollbar p-4 sm:p-6 space-y-6 bg-gradient-to-b from-white via-white to-slate-50/40"
      >
        {docCount === 0 ? (
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
              Ask anything across your {docCount} uploaded {docCount === 1 ? 'file' : 'files'}
            </h3>
            <p className="text-xs text-slate-500 mt-1 mb-6">
              The LLM will automatically retrieve top vector excerpts from all uploaded files and synthesize accurate answers with citations.
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
                  className="w-full flex items-center justify-between p-3 rounded-xl bg-white hover:bg-indigo-50/70 border border-slate-200 hover:border-indigo-300 text-xs text-slate-700 hover:text-indigo-900 transition-all group shadow-2xs active:scale-[0.99]"
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
                    <ReactMarkdown>{msg.content}</ReactMarkdown>
                  </div>
                ) : (
                  <div className="whitespace-pre-wrap">{msg.content}</div>
                )}

                {/* Sourced Documents / Pages Badges */}
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
                        msg.source_details.map((detail, sIdx) => (
                          <button
                            key={sIdx}
                            type="button"
                            onClick={() => onViewPage && onViewPage(detail.doc_id, detail.page, detail.filename)}
                            className="inline-flex items-center space-x-1 px-2.5 py-1 rounded-lg text-xs font-semibold bg-indigo-50 hover:bg-indigo-100 text-indigo-700 border border-indigo-200/80 transition-all active:scale-95 shadow-2xs"
                            title={`Preview ${detail.filename} Page ${detail.page}`}
                          >
                            <FileText className="w-3 h-3 text-indigo-500" />
                            <span>{detail.filename} • Page {detail.page}</span>
                          </button>
                        ))
                      ) : (
                        msg.sources.map((pageNum, sIdx) => (
                          <span
                            key={sIdx}
                            className="inline-flex items-center space-x-1 px-2 py-0.5 rounded-md text-[11px] font-semibold bg-indigo-50 text-indigo-700 border border-indigo-200"
                          >
                            Page {pageNum}
                          </span>
                        ))
                      )}
                    </div>
                  </div>
                )}

                {/* Sequential Follow-up Questions Suggested by LLM */}
                {msg.role === 'assistant' && !msg.isError && Array.isArray(msg.suggested_questions) && msg.suggested_questions.length > 0 && (
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
                          disabled={loading}
                          className="group w-full flex items-center justify-between p-2 sm:p-2.5 rounded-xl bg-slate-50/90 hover:bg-indigo-50/80 border border-slate-200/80 hover:border-indigo-300 text-left text-xs text-slate-700 hover:text-indigo-900 transition-all shadow-2xs active:scale-[0.99] disabled:opacity-50"
                          title={`Click to ask: "${seqQ}"`}
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
                  <span>{msg.time}</span>
                  {msg.role === 'assistant' && !msg.isError && (
                    <button
                      onClick={() => copyToClipboard(msg.content, idx)}
                      className="hover:text-slate-700 transition-colors flex items-center space-x-1"
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
                <span>Searching ChromaDB Across Uploaded Files...</span>
              </div>
              <p className="text-[11px] text-slate-400">
                Retrieving top vector excerpts using reciprocal rank fusion and synthesizing answer.
              </p>
            </div>
          </div>
        )}

        <div ref={messagesEndRef} />
      </div>

      {/* Input Form */}
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
            disabled={loading}
            placeholder={
              isAllDocs
                ? 'Ask a question across all uploaded documents... (Enter to send, Shift+Enter for newline)'
                : `Ask a question about ${activeDocument?.filename || 'this document'}... (Enter to send, Shift+Enter for newline)`
            }
            className="w-full bg-slate-50/60 focus:bg-white border border-slate-200 focus:border-indigo-500 focus:ring-2 focus:ring-indigo-100 custom-scrollbar rounded-xl px-4 py-3 pr-24 text-xs sm:text-sm text-slate-900 placeholder:text-slate-400 focus:outline-none transition-all resize-none min-h-[52px] max-h-36 overflow-y-auto"
          />

          <div className="absolute right-2.5 bottom-2.5 flex items-center">
            <button
              type="submit"
              disabled={!question.trim() || loading}
              className="flex items-center space-x-1.5 px-4 py-2 rounded-lg text-xs font-semibold text-white bg-gradient-to-r from-indigo-600 via-indigo-600 to-blue-600 hover:from-indigo-500 hover:to-blue-500 disabled:opacity-40 disabled:cursor-not-allowed shadow-xs transition-all active:scale-95"
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
            {isAllDocs ? 'Searching: All indexed files in ChromaDB' : `Scope: ${activeDocument?.filename}`}
          </span>
          <span>Shift+Enter for newline</span>
        </div>
      </div>
    </section>
  );
}
