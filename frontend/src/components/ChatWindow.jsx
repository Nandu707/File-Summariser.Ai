import React, { useState, useRef, useEffect } from 'react';
import axios from 'axios';
import ReactMarkdown from 'react-markdown';
import { Send, Bot, User, BookOpen, Copy, Check, AlertCircle, Loader2, Lock, Sparkles, ArrowUpRight, Trash2 } from 'lucide-react';

export default function ChatWindow({ docId, documentInfo, onLoadingChange }) {
  const [messages, setMessages] = useState([]);
  const [question, setQuestion] = useState('');
  const [loading, setLoading] = useState(false);
  const [loadingChat, setLoadingChat] = useState(false);
  const [error, setError] = useState(null);
  const [copiedIdx, setCopiedIdx] = useState(null);
  const [selectedPageSource, setSelectedPageSource] = useState(null);
  const [suggestedQuestions, setSuggestedQuestions] = useState([]);
  const [loadingSuggestions, setLoadingSuggestions] = useState(false);
  const chatContainerRef = useRef(null);
  const messagesEndRef = useRef(null);
  const inputRef = useRef(null);

  const isChatDisabled = !docId;

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

  // When docId changes, load persistent chat history from DB and document-tailored suggested questions
  useEffect(() => {
    setError(null);
    if (docId) {
      inputRef.current?.focus();
    }

    if (!docId) {
      setMessages([]);
      setSuggestedQuestions([]);
      return;
    }

    let isMounted = true;

    // Load persisted chat history for this document from SQLite DB
    const fetchChatHistory = async () => {
      setLoadingChat(true);
      try {
        const res = await axios.get(`http://localhost:8000/api/documents/${docId}/chat`);
        if (isMounted && res.data && Array.isArray(res.data.messages)) {
          setMessages(res.data.messages);
        }
      } catch (err) {
        if (isMounted) {
          console.error("Failed to fetch chat history:", err);
          setMessages([]);
        }
      } finally {
        if (isMounted) {
          setLoadingChat(false);
        }
      }
    };

    fetchChatHistory();

    // If documentInfo already has suggested questions, use them directly
    if (Array.isArray(documentInfo?.suggested_questions) && documentInfo.suggested_questions.length > 0) {
      setSuggestedQuestions(documentInfo.suggested_questions);
    } else {
      // Fetch dynamic questions tailored to the active file
      const fetchQuestions = async () => {
        setLoadingSuggestions(true);
        try {
          const res = await axios.get(`http://localhost:8000/api/documents/${docId}/suggested-questions`);
          if (isMounted && res.data && Array.isArray(res.data.suggested_questions) && res.data.suggested_questions.length > 0) {
            setSuggestedQuestions(res.data.suggested_questions);
          }
        } catch (err) {
          if (isMounted) {
            const fn = documentInfo?.filename || 'this document';
            setSuggestedQuestions([
              `What is the central topic and summary of ${fn}?`,
              `What key technical skills, metrics, or methods are outlined?`,
              `What conclusions and next steps are stated in ${fn}?`
            ]);
          }
        } finally {
          if (isMounted) {
            setLoadingSuggestions(false);
          }
        }
      };
      fetchQuestions();
    }

    return () => {
      isMounted = false;
    };
  }, [docId, documentInfo]);

  const handleClearChat = async () => {
    if (!docId || loading) return;
    try {
      await axios.delete(`http://localhost:8000/api/documents/${docId}/chat`);
      setMessages([]);
    } catch (err) {
      console.error("Failed to clear chat history:", err);
    }
  };

  const handleSend = async (customPrompt) => {
    const qToSend = (customPrompt || question).trim();
    if (!qToSend || isChatDisabled || loading) return;

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
      // POST to http://localhost:8000/api/ask using axios
      const response = await axios.post('http://localhost:8000/api/ask', {
        doc_id: docId,
        question: qToSend,
      }, {
        headers: {
          'Content-Type': 'application/json',
        },
        timeout: 60000,
      });

      const data = response.data; // { answer, sources }

      const botMessage = {
        role: 'assistant',
        content: data.answer || '',
        sources: Array.isArray(data.sources) ? data.sources : [],
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
          content: `Error querying document: ${msg}`,
          sources: [],
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

  const handleBadgeClick = (pageNum) => {
    setSelectedPageSource(pageNum);
    setTimeout(() => setSelectedPageSource(null), 3000);
  };

  const samplePrompts = [
    'What is the central topic and summary of this document?',
    'What key numbers, statistics, or metrics are mentioned?',
    'What are the primary conclusions or next steps?',
  ];

  return (
    <section className="flex-1 min-h-0 glass-card rounded-2xl border border-slate-800/80 flex flex-col h-full overflow-hidden relative">
      {/* Top Banner */}
      <div className="flex-shrink-0 px-6 py-3.5 border-b border-slate-800/80 bg-slate-900/40 backdrop-blur-md flex items-center justify-between">
        <div className="flex items-center space-x-3">
          <div className={`p-2 rounded-lg border ${isChatDisabled
            ? 'bg-slate-800 text-slate-500 border-slate-700'
            : 'bg-brand-500/10 text-brand-400 border-brand-500/20'
            }`}>
            <Bot className="w-4 h-4" />
          </div>
          <div>
            <div className="flex items-center space-x-2">
              <h3 className="text-sm font-bold text-white tracking-tight">
                {isChatDisabled ? 'Chat Window' : documentInfo?.filename || 'Active Document'}
              </h3>
              {!isChatDisabled && (
                <span className="text-[10px] font-mono px-2 py-0.5 rounded-full bg-brand-500/15 text-brand-300 border border-brand-500/30">
                  {documentInfo?.chunks ? `${documentInfo.chunks} chunks` : 'Indexed'}
                </span>
              )}
            </div>
            <p className="text-[11px] text-slate-400">
              {isChatDisabled
                ? 'Upload a document in the left sidebar to unlock Q&A'
                : 'Ready for questions'}
            </p>
          </div>
        </div>

        <div className="flex items-center space-x-2">
          {messages.length > 0 && !isChatDisabled && (
            <button
              onClick={handleClearChat}
              disabled={loading}
              title="Clear conversation history for this document"
              className="inline-flex items-center space-x-1.5 px-2.5 py-1 rounded-lg text-xs font-medium text-slate-400 hover:text-red-400 hover:bg-red-500/10 border border-slate-700/60 hover:border-red-500/30 transition-colors disabled:opacity-50"
            >
              <Trash2 className="w-3.5 h-3.5" />
              <span>Clear Chat</span>
            </button>
          )}
          <span className={`inline-flex items-center space-x-1.5 px-2.5 py-1 rounded-full text-xs font-medium border ${isChatDisabled
            ? 'bg-slate-800/80 text-slate-500 border-slate-700'
            : 'bg-emerald-500/10 text-emerald-400 border-emerald-500/20'
            }`}>
            <span className={`w-2 h-2 rounded-full ${isChatDisabled ? 'bg-slate-500' : 'bg-emerald-400 animate-pulse'}`} />
            <span>{isChatDisabled ? 'Waiting for Document' : 'ChromaDB Ready'}</span>
          </span>
        </div>
      </div>

      {/* Selected Page Source Notification Alert */}
      {selectedPageSource && (
        <div className="absolute top-16 right-6 z-20 animate-slide-up">
          <div className="px-3.5 py-2 rounded-xl bg-brand-900/90 border border-brand-400/50 text-brand-200 text-xs shadow-xl flex items-center space-x-2 backdrop-blur-md">
            <BookOpen className="w-3.5 h-3.5 text-brand-300" />
            <span>Citation highlighted: Sourced from <strong>Page {selectedPageSource}</strong></span>
          </div>
        </div>
      )}

      {/* Messages Area - Chat Section Container */}
      <div
        ref={chatContainerRef}
        className="flex-1 min-h-0 overflow-y-scroll custom-scrollbar p-4 sm:p-6 space-y-6"
      >
        {isChatDisabled ? (
          /* Disabled State Screen */
          <div className="h-full flex flex-col items-center justify-center text-center px-4 max-w-md mx-auto">
            <div className="w-14 h-14 rounded-2xl bg-slate-900 border border-slate-800 text-slate-600 flex items-center justify-center mb-4">
              <Lock className="w-6 h-6" />
            </div>
            <h4 className="text-base font-bold text-white">Chat Interface Disabled</h4>
            <p className="text-xs text-slate-400 mt-2 leading-relaxed">
              Upload a <strong>.pdf</strong>, <strong>.txt</strong>, or <strong>.docx/.doc</strong> document in the left sidebar to initialize ChromaDB embeddings and unlock questions.
            </p>
          </div>
        ) : loadingChat ? (
          <div className="h-full flex flex-col items-center justify-center space-y-3 py-16">
            <Loader2 className="w-7 h-7 text-brand-400 animate-spin" />
            <p className="text-xs text-slate-400">Loading conversation history from database...</p>
          </div>
        ) : messages.length === 0 ? (
          /* Empty / Welcome State with Suggested Questions */
          <div className="h-full flex flex-col justify-center items-center text-center px-4 max-w-lg mx-auto py-10">
            <div className="w-12 h-12 rounded-2xl bg-brand-500/10 border border-brand-500/20 text-brand-400 flex items-center justify-center mb-4 shadow-lg shadow-brand-500/10">
              <Sparkles className="w-6 h-6" />
            </div>
            <h4 className="text-base font-bold text-white">Ask anything about this document</h4>
            <p className="text-xs text-slate-400 mt-1 mb-6">
              Retrieves top 4 chunks from ChromaDB and applies strict context synthesis with exact page citations.
            </p>

            <div className="w-full space-y-2 text-left">
              <div className="flex items-center justify-between mb-1">
                <p className="text-[11px] font-semibold text-slate-500 uppercase tracking-wider flex items-center space-x-1.5">
                  <Sparkles className="w-3.5 h-3.5 text-brand-400" />
                  <span>Suggested Questions for {documentInfo?.filename || 'Document'}</span>
                </p>
                {loadingSuggestions && (
                  <span className="text-[10px] text-brand-400 flex items-center space-x-1 animate-pulse">
                    <Loader2 className="w-3 h-3 animate-spin" />
                    <span>Generating...</span>
                  </span>
                )}
              </div>

              {loadingSuggestions && suggestedQuestions.length === 0 ? (
                <div className="space-y-2 pt-1">
                  {[1, 2, 3].map((n) => (
                    <div key={n} className="w-full p-3 rounded-xl bg-slate-900/40 border border-slate-800/80 animate-pulse flex items-center justify-between">
                      <div className="h-3 bg-slate-800/80 rounded w-4/5"></div>
                      <div className="w-3 h-3 bg-slate-800 rounded"></div>
                    </div>
                  ))}
                </div>
              ) : (
                (suggestedQuestions.length > 0 ? suggestedQuestions : samplePrompts).map((prompt, idx) => (
                  <button
                    key={idx}
                    onClick={() => handleSend(prompt)}
                    className="w-full flex items-center justify-between p-3 rounded-xl bg-slate-900/60 hover:bg-slate-800/80 border border-slate-800 hover:border-brand-500/40 text-xs text-slate-300 hover:text-white transition-all group shadow-sm hover:shadow-brand-500/5 active:scale-[0.99]"
                  >
                    <span className="truncate pr-2">{prompt}</span>
                    <ArrowUpRight className="w-3.5 h-3.5 text-slate-500 group-hover:text-brand-400 flex-shrink-0 transition-colors" />
                  </button>
                ))
              )}
            </div>
          </div>
        ) : (
          /* Active Chat Stream */
          messages.map((msg, idx) => (
            <div
              key={idx}
              className={`flex items-start space-x-3 animate-fade-in ${msg.role === 'user' ? 'justify-end' : 'justify-start'
                }`}
            >
              {msg.role === 'assistant' && (
                <div className="w-8 h-8 rounded-xl bg-gradient-to-br from-brand-600 to-indigo-600 text-white flex items-center justify-center flex-shrink-0 shadow-md shadow-brand-500/20 mt-1">
                  <Bot className="w-4 h-4" />
                </div>
              )}

              <div
                className={`max-w-2xl rounded-2xl p-4 text-xs sm:text-sm leading-relaxed ${msg.role === 'user'
                  ? 'bg-gradient-to-r from-brand-600 to-indigo-600 text-white shadow-md'
                  : msg.isError
                    ? 'bg-rose-950/40 border border-rose-500/30 text-rose-200'
                    : 'bg-slate-900/90 border border-slate-800 text-slate-200 shadow-sm'
                  }`}
              >
                {/* Markdown Rendered Content */}
                {msg.role === 'assistant' && !msg.isError ? (
                  <div className="prose prose-invert prose-sm max-w-none space-y-2">
                    <ReactMarkdown>{msg.content}</ReactMarkdown>
                  </div>
                ) : (
                  <div className="whitespace-pre-wrap">{msg.content}</div>
                )}

                {/* Clickable Source Page Badges */}
                {msg.role === 'assistant' && !msg.isError && msg.sources && msg.sources.length > 0 && (
                  <div className="mt-3.5 pt-3 border-t border-slate-800 flex flex-wrap items-center gap-1.5">
                    <span className="text-[11px] font-semibold text-slate-400 flex items-center space-x-1 mr-1">
                      <BookOpen className="w-3 h-3 text-brand-400" />
                      <span>Sources:</span>
                    </span>
                    {msg.sources.map((pageNum, sIdx) => (
                      <button
                        key={sIdx}
                        onClick={() => handleBadgeClick(pageNum)}
                        className="px-2.5 py-0.5 rounded-full text-[11px] font-bold bg-brand-500/20 text-brand-300 border border-brand-500/40 hover:bg-brand-500/35 hover:scale-105 active:scale-95 transition-all shadow-sm"
                        title={`Click to view citation details for Page ${pageNum}`}
                      >
                        Page {pageNum}
                      </button>
                    ))}
                  </div>
                )}

                {/* Footer details */}
                <div className="mt-2.5 flex items-center justify-between text-[10px] text-slate-400">
                  <span>{msg.time}</span>
                  {msg.role === 'assistant' && !msg.isError && (
                    <button
                      onClick={() => copyToClipboard(msg.content, idx)}
                      className="hover:text-white transition-colors flex items-center space-x-1"
                      title="Copy response"
                    >
                      {copiedIdx === idx ? (
                        <>
                          <Check className="w-3 h-3 text-emerald-400" />
                          <span className="text-emerald-400">Copied</span>
                        </>
                      ) : (
                        <>
                          <Copy className="w-3 h-3" />
                          <span>Copy</span>
                        </>
                      )}
                    </button>
                  )}
                </div>
              </div>

              {msg.role === 'user' && (
                <div className="w-8 h-8 rounded-xl bg-slate-800 text-slate-300 flex items-center justify-center flex-shrink-0 border border-slate-700 mt-1">
                  <User className="w-4 h-4" />
                </div>
              )}
            </div>
          ))
        )}

        {/* Loading Spinner */}
        {loading && (
          <div className="flex items-start space-x-3 animate-fade-in">
            <div className="w-8 h-8 rounded-xl bg-gradient-to-br from-brand-600 to-indigo-600 text-white flex items-center justify-center flex-shrink-0 shadow-md shadow-brand-500/20 mt-1">
              <Bot className="w-4 h-4" />
            </div>
            <div className="bg-slate-900/90 border border-slate-800 rounded-2xl p-4 text-xs text-slate-300 space-y-1.5">
              <div className="flex items-center space-x-2 text-brand-400">
                <Loader2 className="w-4 h-4 animate-spin" />
                <span className="font-semibold">Querying ChromaDB & Synthesizing Answer...</span>
              </div>
              <p className="text-[11px] text-slate-500">Searching top 4 vector chunks and applying strict context-only prompt.</p>
            </div>
          </div>
        )}

        <div ref={messagesEndRef} />
      </div>

      {/* Input Form */}
      <div className="flex-shrink-0 p-4 border-t border-slate-800/80 bg-slate-950/60 backdrop-blur-md">
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
            disabled={isChatDisabled || loading}
            placeholder={
              isChatDisabled
                ? 'Upload a document in the left sidebar first...'
                : 'Ask a question about the uploaded document... (Press Enter to ask, Shift+Enter for newline)'
            }
            className={`w-full glass-input custom-scrollbar rounded-xl px-4 py-3 pr-24 text-xs sm:text-sm placeholder:text-slate-500 focus:outline-none transition-all resize-none min-h-[52px] max-h-36 overflow-y-auto ${isChatDisabled ? 'bg-slate-900/30 opacity-50 cursor-not-allowed' : ''
              }`}
          />

          <div className="absolute right-2.5 bottom-2.5 flex items-center">
            <button
              type="submit"
              disabled={isChatDisabled || !question.trim() || loading}
              className="flex items-center space-x-1.5 px-4 py-2 rounded-lg text-xs font-semibold text-white bg-gradient-to-r from-brand-600 to-indigo-600 hover:from-brand-500 hover:to-indigo-500 disabled:opacity-40 disabled:cursor-not-allowed shadow-md shadow-brand-600/20 transition-all active:scale-95"
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
        <div className="mt-2 flex items-center justify-between text-[11px] text-slate-500 px-1">

          <span>Shift+Enter for newline</span>
        </div>
      </div>
    </section>
  );
}
