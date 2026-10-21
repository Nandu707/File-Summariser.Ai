import React, { useState, useRef, useEffect } from 'react';
import { Send, Bot, User, Sparkles, Copy, Check, Loader2, ArrowUpRight } from 'lucide-react';
import { askQuestion, API_BASE_URL } from '../api';

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
        const res = await fetch(`${API_BASE_URL}/api/documents/${activeDoc.doc_id}/suggested-questions`);
        if (res.ok) {
          const data = await res.json();
          if (isMounted && data && Array.isArray(data.suggested_questions)) {
            setDynamicQuestions(data.suggested_questions);
          }
        }
      } catch (err) {
        // Fallback
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
      const res = await askQuestion(activeDoc.doc_id, question);
      const elapsed = ((performance.now() - startTime) / 1000).toFixed(2);

      const botMessage = {
        role: 'assistant',
        content: res.answer,
        sources: res.sources || [],
        suggested_questions: Array.isArray(res.suggested_questions) ? res.suggested_questions : [],
        elapsed: elapsed,
        timestamp: new Date().toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' }),
      };

      setMessages((prev) => [...prev, botMessage]);
    } catch (err) {
      setError(err.message || 'Failed to generate answer from document.');
    } finally {
      setLoading(false);
    }
  };

  const copyToClipboard = (text, idx) => {
    navigator.clipboard.writeText(text);
    setCopiedIndex(idx);
    setTimeout(() => setCopiedIndex(null), 2000);
  };

  return (
    <div className="flex-1 min-h-0 bg-white rounded-2xl border border-slate-200/90 shadow-sm flex flex-col h-full overflow-hidden">
      {/* Messages */}
      <div
        ref={chatContainerRef}
        className="flex-1 min-h-0 overflow-y-auto custom-scrollbar p-4 sm:p-6 space-y-4"
      >
        {!activeDoc ? (
          <div className="h-full flex flex-col items-center justify-center text-center p-6 text-slate-400">
            <Sparkles className="w-8 h-8 text-indigo-400 mb-2" />
            <p className="text-sm font-semibold text-slate-700">Select a document to begin chatting</p>
          </div>
        ) : messages.length === 0 ? (
          <div className="h-full flex flex-col items-center justify-center text-center p-6 space-y-4">
            <div className="w-12 h-12 rounded-xl bg-indigo-50 text-indigo-600 flex items-center justify-center">
              <Sparkles className="w-6 h-6" />
            </div>
            <div>
              <h3 className="text-sm font-bold text-slate-900">Ask questions about {activeDoc.filename}</h3>
              <p className="text-xs text-slate-500 mt-1">ChromaDB hybrid retrieval is ready.</p>
            </div>
            {dynamicQuestions.length > 0 && (
              <div className="w-full max-w-md space-y-2 text-left">
                {dynamicQuestions.map((q, i) => (
                  <button
                    key={i}
                    onClick={() => handleSend(q)}
                    className="w-full p-2.5 rounded-xl bg-slate-50 hover:bg-indigo-50 border border-slate-200 text-xs text-slate-700 hover:text-indigo-900 flex items-center justify-between"
                  >
                    <span>{q}</span>
                    <ArrowUpRight className="w-3.5 h-3.5 text-slate-400" />
                  </button>
                ))}
              </div>
            )}
          </div>
        ) : (
          messages.map((m, idx) => (
            <div
              key={idx}
              className={`flex items-start space-x-2.5 ${m.role === 'user' ? 'justify-end' : 'justify-start'}`}
            >
              {m.role === 'assistant' && (
                <div className="w-7 h-7 rounded-lg bg-indigo-600 text-white flex items-center justify-center flex-shrink-0 mt-1">
                  <Bot className="w-4 h-4" />
                </div>
              )}
              <div
                className={`max-w-xl p-3.5 rounded-2xl text-xs sm:text-sm leading-relaxed ${
                  m.role === 'user'
                    ? 'bg-gradient-to-r from-indigo-600 to-blue-600 text-white rounded-tr-xs'
                    : 'bg-white border border-slate-200 text-slate-800 shadow-2xs rounded-tl-xs'
                }`}
              >
                <p className="whitespace-pre-wrap">{m.content}</p>
                <div className="mt-2 flex items-center justify-between text-[10px] text-slate-400">
                  <span>{m.timestamp}</span>
                  {m.role === 'assistant' && (
                    <button
                      onClick={() => copyToClipboard(m.content, idx)}
                      className="hover:text-slate-700"
                    >
                      {copiedIndex === idx ? <Check className="w-3 h-3 text-emerald-600" /> : <Copy className="w-3 h-3" />}
                    </button>
                  )}
                </div>
              </div>
              {m.role === 'user' && (
                <div className="w-7 h-7 rounded-lg bg-slate-100 text-slate-600 flex items-center justify-center flex-shrink-0 mt-1 border border-slate-200">
                  <User className="w-4 h-4" />
                </div>
              )}
            </div>
          ))
        )}

        {loading && (
          <div className="flex items-center space-x-2 text-xs text-indigo-600 p-2">
            <Loader2 className="w-4 h-4 animate-spin" />
            <span>Analyzing document and synthesizing answer...</span>
          </div>
        )}

        <div ref={messagesEndRef} />
      </div>

      {/* Input */}
      <div className="p-3 border-t border-slate-200 bg-white">
        <form
          onSubmit={(e) => {
            e.preventDefault();
            handleSend();
          }}
          className="flex items-center space-x-2"
        >
          <input
            ref={inputRef}
            type="text"
            value={inputQuestion}
            onChange={(e) => setInputQuestion(e.target.value)}
            disabled={!activeDoc || loading}
            placeholder={activeDoc ? "Ask a question about this document..." : "Select a document first..."}
            className="flex-1 bg-slate-50 border border-slate-200 rounded-xl px-4 py-2.5 text-xs sm:text-sm text-slate-900 focus:outline-none focus:border-indigo-500 focus:ring-2 focus:ring-indigo-100"
          />
          <button
            type="submit"
            disabled={!activeDoc || !inputQuestion.trim() || loading}
            className="p-2.5 rounded-xl bg-indigo-600 hover:bg-indigo-500 text-white disabled:opacity-40"
          >
            <Send className="w-4 h-4" />
          </button>
        </form>
      </div>
    </div>
  );
}
