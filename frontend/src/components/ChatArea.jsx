import React, { useState, useRef, useEffect } from 'react';
import { Send, Bot, User, Sparkles, BookOpen, Copy, Check, AlertCircle, Loader2, ArrowUpRight, HelpCircle, Layers } from 'lucide-react';
import { askQuestion } from '../api';

export default function ChatArea({ activeDoc, onOpenUpload }) {
  const [messages, setMessages] = useState([]);
  const [inputQuestion, setInputQuestion] = useState('');
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState(null);
  const [copiedIndex, setCopiedIndex] = useState(null);
  const [dynamicQuestions, setDynamicQuestions] = useState([]);
  const [loadingQuestions, setLoadingQuestions] = useState(false);
  const chatContainerRef = useRef(null);
  const messagesEndRef = useRef(null);
  const inputRef = useRef(null);

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

  useEffect(() => {
    if (activeDoc) {
      inputRef.current?.focus();
    }

    if (!activeDoc?.doc_id) {
      setDynamicQuestions([]);
      return;
    }

    if (Array.isArray(activeDoc.suggested_questions) && activeDoc.suggested_questions.length > 0) {
      setDynamicQuestions(activeDoc.suggested_questions);
      return;
    }

    let isMounted = true;
    const fetchQuestions = async () => {
      setLoadingQuestions(true);
      try {
        const res = await fetch(`http://localhost:8000/api/documents/${activeDoc.doc_id}/suggested-questions`);
        if (res.ok) {
          const data = await res.json();
          if (isMounted && data && Array.isArray(data.suggested_questions)) {
            setDynamicQuestions(data.suggested_questions);
          }
        }
      } catch (err) {
        // Fallback handled gracefully
      } finally {
        if (isMounted) setLoadingQuestions(false);
      }
    };

    fetchQuestions();
    return () => { isMounted = false; };
  }, [activeDoc?.doc_id]);

  const handleSend = async (qToSend) => {
    const question = (qToSend || inputQuestion).trim();
    if (!question || !activeDoc || loading) return;

    setError(null);
    setInputQuestion('');

    const userMessage = {
      role: 'user',
      content: question,
      timestamp: new Date().toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' }),
    };

    setMessages((prev) => [...prev, userMessage]);
    setLoading(true);

    try {
      const startTime = performance.now();
      // POST /api/ask with { doc_id, question }
      const res = await askQuestion(activeDoc.doc_id, question);
      const elapsed = ((performance.now() - startTime) / 1000).toFixed(2);

      const botMessage = {
        role: 'assistant',
        content: res.answer,
        sources: res.sources || [], // list[int]
        elapsed: elapsed,
        timestamp: new Date().toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' }),
      };

      setMessages((prev) => [...prev, botMessage]);
    } catch (err) {
      setError(err.message || 'Failed to generate answer from document.');
      setMessages((prev) => [
        ...prev,
        {
          role: 'assistant',
          isError: true,
          content: `Error: ${err.message || 'Could not query ChromaDB vector store.'}`,
          sources: [],
          timestamp: new Date().toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' }),
        },
      ]);
    } finally {
      setLoading(false);
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
    setCopiedIndex(idx);
    setTimeout(() => setCopiedIndex(null), 2000);
  };

  const suggestedQuestions = [
    'What is the central topic and summary of this document?',
    'What key findings, conclusions, or recommendations are stated?',
    'Are there any notable dates, statistics, or metrics mentioned?',
    'What action items or next steps are described?',
  ];

  if (!activeDoc) {
    return (
      <section className="flex-1 glass-card rounded-2xl border border-slate-800/80 p-8 flex flex-col items-center justify-center text-center h-[calc(100vh-6.5rem)]">
        <div className="w-16 h-16 rounded-2xl bg-brand-500/10 border border-brand-500/20 text-brand-400 flex items-center justify-center mb-4 shadow-lg shadow-brand-500/10">
          <BookOpen className="w-8 h-8" />
        </div>
        <h3 className="text-xl font-bold text-white tracking-tight">No Active Document Selected</h3>
        <p className="text-sm text-slate-400 max-w-md mt-2 mb-6">
          Upload a new PDF or Text file, or select an existing indexed document from the left sidebar to start asking questions.
        </p>
        <button
          onClick={onOpenUpload}
          className="flex items-center space-x-2 px-5 py-2.5 rounded-xl text-xs font-semibold text-white bg-gradient-to-r from-brand-600 to-indigo-600 hover:from-brand-500 hover:to-indigo-500 shadow-lg shadow-brand-500/20 transition-all active:scale-95"
        >
          <Sparkles className="w-4 h-4" />
          <span>Upload Document</span>
        </button>
      </section>
    );
  }

  return (
    <section className="flex-1 min-h-0 glass-card rounded-2xl border border-slate-800/80 flex flex-col h-[calc(100vh-6.5rem)] overflow-hidden">
      {/* Active Document Top Bar */}
      <div className="flex-shrink-0 px-6 py-3.5 border-b border-slate-800/80 bg-slate-900/40 backdrop-blur-sm flex items-center justify-between">
        <div className="flex items-center space-x-3 overflow-hidden">
          <div className="p-2 rounded-lg bg-brand-500/10 text-brand-400 border border-brand-500/20 flex-shrink-0">
            <BookOpen className="w-4 h-4" />
          </div>
          <div className="overflow-hidden">
            <div className="flex items-center space-x-2">
              <h3 className="text-sm font-bold text-white truncate max-w-sm sm:max-w-md">
                {activeDoc.filename}
              </h3>
              <span className="text-[10px] font-mono px-2 py-0.5 rounded bg-brand-500/10 text-brand-300 border border-brand-500/20">
                {activeDoc.chunks} chunks
              </span>
            </div>
            <p className="text-[11px] text-slate-400">
              Ready for questions
            </p>
          </div>
        </div>

        <div className="hidden md:flex items-center space-x-2 text-xs text-slate-400">
          <span className="inline-block w-2 h-2 rounded-full bg-emerald-400 animate-pulse" />
          <span>ChromaDB Ready</span>
        </div>
      </div>

      {/* Messages Stream - Chat Section Container */}
      <div
        ref={chatContainerRef}
        className="flex-1 min-h-0 overflow-y-scroll custom-scrollbar p-4 sm:p-6 space-y-6"
      >
        {messages.length === 0 ? (
          <div className="h-full flex flex-col justify-center items-center text-center px-4 max-w-lg mx-auto py-12">
            <div className="w-12 h-12 rounded-2xl bg-gradient-to-tr from-brand-600/20 to-indigo-600/20 border border-brand-500/20 text-brand-400 flex items-center justify-center mb-4">
              <Bot className="w-6 h-6" />
            </div>
            <h4 className="text-base font-bold text-white">Ask anything about this document</h4>
            <p className="text-xs text-slate-400 mt-1 mb-6">
              The query searches ChromaDB for the top 4 semantic chunks and cites exact page numbers.
            </p>

            {/* Quick Prompts */}
            <div className="w-full space-y-2">
              <div className="flex items-center justify-between text-left">
                <p className="text-[11px] font-semibold text-slate-500 uppercase tracking-wider flex items-center space-x-1.5">
                  <Sparkles className="w-3.5 h-3.5 text-brand-400" />
                  <span>Suggested Questions for {activeDoc.filename}</span>
                </p>
                {loadingQuestions && (
                  <span className="text-[10px] text-brand-400 flex items-center space-x-1 animate-pulse">
                    <Loader2 className="w-3 h-3 animate-spin" />
                    <span>Generating...</span>
                  </span>
                )}
              </div>
              <div className="grid grid-cols-1 gap-2 text-left">
                {(dynamicQuestions.length > 0 ? dynamicQuestions : suggestedQuestions).map((sq, i) => (
                  <button
                    key={i}
                    onClick={() => handleSend(sq)}
                    className="flex items-center justify-between p-2.5 rounded-xl bg-slate-900/60 hover:bg-slate-800/80 border border-slate-800 hover:border-brand-500/40 text-xs text-slate-300 hover:text-white transition-all group shadow-sm hover:shadow-brand-500/5 active:scale-[0.99]"
                  >
                    <span className="truncate pr-2">{sq}</span>
                    <ArrowUpRight className="w-3.5 h-3.5 text-slate-500 group-hover:text-brand-400 flex-shrink-0 transition-colors" />
                  </button>
                ))}
              </div>
            </div>
          </div>
        ) : (
          messages.map((msg, idx) => (
            <div
              key={idx}
              className={`flex items-start space-x-3 animate-fade-in ${
                msg.role === 'user' ? 'justify-end' : 'justify-start'
              }`}
            >
              {msg.role === 'assistant' && (
                <div className="w-8 h-8 rounded-xl bg-gradient-to-br from-brand-600 to-indigo-600 text-white flex items-center justify-center flex-shrink-0 shadow-md shadow-brand-500/20 mt-1">
                  <Bot className="w-4 h-4" />
                </div>
              )}

              <div
                className={`max-w-2xl rounded-2xl p-4 text-xs sm:text-sm leading-relaxed ${
                  msg.role === 'user'
                    ? 'bg-gradient-to-r from-brand-600 to-indigo-600 text-white shadow-md shadow-brand-600/10'
                    : msg.isError
                    ? 'bg-rose-950/40 border border-rose-500/30 text-rose-200'
                    : 'bg-slate-900/90 border border-slate-800 text-slate-200 shadow-sm'
                }`}
              >
                {/* Content */}
                <div className="whitespace-pre-wrap">{msg.content}</div>

                {/* Sources list[int] citations */}
                {msg.role === 'assistant' && !msg.isError && msg.sources && msg.sources.length > 0 && (
                  <div className="mt-3.5 pt-3 border-t border-slate-800/80 flex flex-wrap items-center gap-1.5">
                    <span className="text-[11px] font-semibold text-slate-400 flex items-center space-x-1 mr-1">
                      <BookOpen className="w-3 h-3 text-brand-400" />
                      <span>Retrieved Sources:</span>
                    </span>
                    {msg.sources.map((pageNum, sIdx) => (
                      <span
                        key={sIdx}
                        className="px-2 py-0.5 rounded-full text-[11px] font-bold bg-brand-500/15 text-brand-300 border border-brand-500/30 hover:bg-brand-500/25 transition-colors"
                        title={`Information sourced from Page ${pageNum}`}
                      >
                        Page {pageNum}
                      </span>
                    ))}
                  </div>
                )}

                {/* Footer details */}
                <div className="mt-2.5 flex items-center justify-between text-[10px] text-slate-400/80">
                  <div className="flex items-center space-x-2">
                    <span>{msg.timestamp}</span>
                    {msg.elapsed && <span>• {msg.elapsed}s</span>}
                  </div>
                  {msg.role === 'assistant' && !msg.isError && (
                    <button
                      onClick={() => copyToClipboard(msg.content, idx)}
                      className="hover:text-white transition-colors flex items-center space-x-1"
                      title="Copy response"
                    >
                      {copiedIndex === idx ? (
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

        {/* Loading Indicator */}
        {loading && (
          <div className="flex items-start space-x-3 animate-fade-in">
            <div className="w-8 h-8 rounded-xl bg-gradient-to-br from-brand-600 to-indigo-600 text-white flex items-center justify-center flex-shrink-0 shadow-md shadow-brand-500/20 mt-1">
              <Bot className="w-4 h-4" />
            </div>
            <div className="bg-slate-900/90 border border-slate-800 rounded-2xl p-4 text-xs text-slate-300 space-y-2">
              <div className="flex items-center space-x-2 text-brand-400">
                <Loader2 className="w-4 h-4 animate-spin" />
                <span className="font-medium">Querying ChromaDB top 4 chunks...</span>
              </div>
              <p className="text-[11px] text-slate-500">
                Searching vector embeddings and synthesizing answer with page citations.
              </p>
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
            value={inputQuestion}
            onChange={(e) => setInputQuestion(e.target.value)}
            onKeyDown={handleKeyDown}
            disabled={loading}
            placeholder={`Ask a question about ${activeDoc.filename}... (Press Enter to ask, Shift+Enter for newline)`}
            className="w-full glass-input custom-scrollbar rounded-xl px-4 py-3 pr-28 text-xs sm:text-sm placeholder:text-slate-500 focus:outline-none transition-all resize-none min-h-[52px] max-h-36 overflow-y-auto"
          />

          <div className="absolute right-2.5 bottom-2.5 flex items-center space-x-1.5">
            <button
              type="submit"
              disabled={!inputQuestion.trim() || loading}
              className="flex items-center space-x-1 px-3.5 py-2 rounded-lg text-xs font-semibold text-white bg-gradient-to-r from-brand-600 to-indigo-600 hover:from-brand-500 hover:to-indigo-500 disabled:opacity-40 disabled:cursor-not-allowed shadow-md shadow-brand-600/20 transition-all active:scale-95"
            >
              {loading ? (
                <Loader2 className="w-3.5 h-3.5 animate-spin" />
              ) : (
                <>
                  <span>Ask</span>
                  <Send className="w-3.5 h-3.5" />
                </>
              )}
            </button>
          </div>
        </form>
        <div className="mt-2 flex items-center justify-end text-[11px] text-slate-500 px-1">
          <span>Shift+Enter for newline</span>
        </div>
      </div>
    </section>
  );
}
