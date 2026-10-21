import React, { useState, useEffect } from 'react';
import axios from 'axios';
import {
  Activity,
  Database,
  Server,
  Cpu,
  CheckCircle2,
  AlertCircle,
  ExternalLink,
  RefreshCw,
  Folder,
  Layers,
  Flame,
  Globe
} from 'lucide-react';
import { API_BASE_URL } from '../api';

export default function SystemPage() {
  const [healthData, setHealthData] = useState(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(null);
  const [lastChecked, setLastChecked] = useState(null);

  const fetchHealth = async () => {
    setLoading(true);
    setError(null);
    try {
      const res = await axios.get(`${API_BASE_URL}/api/health`);
      setHealthData(res.data);
      setLastChecked(new Date().toLocaleTimeString());
    } catch (err) {
      setError(`Cannot connect to backend (${API_BASE_URL || 'relative path'})`);
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    fetchHealth();
  }, []);

  return (
    <div className="flex-1 min-h-0 overflow-y-auto custom-scrollbar max-w-5xl w-full mx-auto p-4 sm:p-6 lg:p-8 space-y-6">
      {/* Header */}
      <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-4 pb-4 border-b border-slate-200">
        <div>
          <h1 className="text-xl font-bold text-slate-900 tracking-tight flex items-center space-x-2">
            <Activity className="w-5 h-5 text-indigo-600" />
            <span>System Health & Diagnostics</span>
          </h1>
          <p className="text-xs text-slate-500 mt-0.5">
            Monitor API endpoints, ChromaDB vector store, and LLM providers
          </p>
        </div>

        <div className="flex items-center space-x-3">
          <button
            onClick={fetchHealth}
            disabled={loading}
            className="flex items-center space-x-1.5 px-3.5 py-1.5 rounded-xl text-xs font-semibold text-slate-700 bg-white hover:bg-slate-50 border border-slate-200 shadow-2xs transition-all active:scale-95 disabled:opacity-50"
          >
            <RefreshCw className={`w-3.5 h-3.5 ${loading ? 'animate-spin text-indigo-600' : 'text-slate-400'}`} />
            <span>Refresh Diagnostics</span>
          </button>
        </div>
      </div>

      {error ? (
        <div className="p-5 rounded-2xl bg-rose-50 border border-rose-200 space-y-2">
          <div className="flex items-center space-x-2 text-rose-800 font-bold text-sm">
            <AlertCircle className="w-5 h-5 text-rose-600" />
            <span>Backend Offline or Unreachable</span>
          </div>
          <p className="text-xs text-rose-700 leading-relaxed">{error}</p>
          <p className="text-[11px] text-slate-500 mt-2">
            Make sure the FastAPI server is running with <code className="bg-white px-1.5 py-0.5 rounded border border-rose-200 font-mono">npm run dev:backend</code> or <code className="bg-white px-1.5 py-0.5 rounded border border-rose-200 font-mono">uvicorn main:app --reload</code> on port 8000.
          </p>
        </div>
      ) : (
        <div className="space-y-6">
          {/* Main Status Cards */}
          <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
            {/* FastAPI Service */}
            <div className="bg-white rounded-2xl border border-slate-200/90 p-5 shadow-sm space-y-4">
              <div className="flex items-center justify-between">
                <div className="flex items-center space-x-2.5">
                  <div className="w-9 h-9 rounded-xl bg-indigo-50 border border-indigo-100 text-indigo-600 flex items-center justify-center">
                    <Server className="w-4 h-4" />
                  </div>
                  <div>
                    <h3 className="text-sm font-bold text-slate-900">FastAPI Backend</h3>
                    <p className="text-[11px] text-slate-500">{API_BASE_URL || window.location.origin}</p>
                  </div>
                </div>
                <span className="flex items-center space-x-1 px-2.5 py-1 rounded-full text-xs font-semibold bg-emerald-50 text-emerald-700 border border-emerald-200">
                  <span className="w-2 h-2 rounded-full bg-emerald-500 animate-pulse" />
                  <span>Online</span>
                </span>
              </div>

              <div className="pt-3 border-t border-slate-100 space-y-2 text-xs">
                <div className="flex justify-between items-center text-slate-600">
                  <span>Status:</span>
                  <span className="font-semibold text-emerald-700 uppercase">{healthData?.status || 'HEALTHY'}</span>
                </div>
                <div className="flex justify-between items-center text-slate-600">
                  <span>Indexed Documents:</span>
                  <span className="font-bold text-slate-900">{healthData?.documents_count ?? 0}</span>
                </div>
                <div className="flex justify-between items-center text-slate-600">
                  <span>Last Verified:</span>
                  <span className="text-slate-400">{lastChecked || 'Just now'}</span>
                </div>
              </div>

              <a
                href={`${API_BASE_URL}/docs`}
                target="_blank"
                rel="noreferrer"
                className="flex items-center justify-center space-x-1.5 w-full py-2 rounded-xl text-xs font-semibold text-indigo-700 bg-indigo-50 hover:bg-indigo-100 border border-indigo-200/80 transition-colors"
              >
                <span>Open Interactive Swagger Docs</span>
                <ExternalLink className="w-3.5 h-3.5" />
              </a>
            </div>

            {/* ChromaDB Vector Store */}
            <div className="bg-white rounded-2xl border border-slate-200/90 p-5 shadow-sm space-y-4">
              <div className="flex items-center justify-between">
                <div className="flex items-center space-x-2.5">
                  <div className="w-9 h-9 rounded-xl bg-blue-50 border border-blue-100 text-blue-600 flex items-center justify-center">
                    <Database className="w-4 h-4" />
                  </div>
                  <div>
                    <h3 className="text-sm font-bold text-slate-900">ChromaDB Vector Store</h3>
                    <p className="text-[11px] text-slate-500">Persistent disk storage</p>
                  </div>
                </div>
                <span className="flex items-center space-x-1 px-2.5 py-1 rounded-full text-xs font-semibold bg-emerald-50 text-emerald-700 border border-emerald-200">
                  <CheckCircle2 className="w-3.5 h-3.5 text-emerald-600" />
                  <span>Ready</span>
                </span>
              </div>

              <div className="pt-3 border-t border-slate-100 space-y-2 text-xs">
                <div className="flex justify-between items-center text-slate-600">
                  <span>Storage Path:</span>
                  <span className="font-mono text-[11px] text-slate-800 truncate max-w-[200px]" title={healthData?.vector_db_path}>
                    {healthData?.vector_db_path || './vector_db'}
                  </span>
                </div>
                <div className="flex justify-between items-center text-slate-600">
                  <span>Search Mechanism:</span>
                  <span className="font-medium text-slate-900">Cosine Similarity + RRF</span>
                </div>
                <div className="flex justify-between items-center text-slate-600">
                  <span>Chunk Size:</span>
                  <span className="font-mono text-slate-700">1000 chars (200 overlap)</span>
                </div>
              </div>
            </div>
          </div>

          {/* Integration Status Breakdown */}
          <div className="bg-white rounded-2xl border border-slate-200/90 p-5 shadow-sm space-y-4">
            <h3 className="text-sm font-bold text-slate-900">Connected Services & Providers</h3>
            
            <div className="grid grid-cols-1 sm:grid-cols-3 gap-3">
              {/* Gemini */}
              <div className="p-3 rounded-xl border border-slate-200 bg-slate-50/60 flex items-center justify-between">
                <div className="flex items-center space-x-2">
                  <Cpu className="w-4 h-4 text-indigo-600" />
                  <div>
                    <p className="text-xs font-bold text-slate-800">Google Gemini</p>
                    <p className="text-[10px] text-slate-500">Gemini 2.5 Flash</p>
                  </div>
                </div>
                <span className={`text-[10px] font-bold px-2 py-0.5 rounded-full ${
                  healthData?.llm_gemini_active
                    ? 'bg-emerald-50 text-emerald-700 border border-emerald-200'
                    : 'bg-slate-200 text-slate-600'
                }`}>
                  {healthData?.llm_gemini_active ? 'Active' : 'Unconfigured'}
                </span>
              </div>

              {/* OpenAI */}
              <div className="p-3 rounded-xl border border-slate-200 bg-slate-50/60 flex items-center justify-between">
                <div className="flex items-center space-x-2">
                  <Cpu className="w-4 h-4 text-blue-600" />
                  <div>
                    <p className="text-xs font-bold text-slate-800">OpenAI API</p>
                    <p className="text-[10px] text-slate-500">GPT-4o-mini</p>
                  </div>
                </div>
                <span className={`text-[10px] font-bold px-2 py-0.5 rounded-full ${
                  healthData?.llm_openai_active
                    ? 'bg-emerald-50 text-emerald-700 border border-emerald-200'
                    : 'bg-slate-200 text-slate-600'
                }`}>
                  {healthData?.llm_openai_active ? 'Active' : 'Fallback'}
                </span>
              </div>

              {/* Firebase */}
              <div className="p-3 rounded-xl border border-slate-200 bg-slate-50/60 flex items-center justify-between">
                <div className="flex items-center space-x-2">
                  <Flame className="w-4 h-4 text-amber-600" />
                  <div>
                    <p className="text-xs font-bold text-slate-800">Firebase Firestore</p>
                    <p className="text-[10px] text-slate-500">Cloud History Sync</p>
                  </div>
                </div>
                <span className={`text-[10px] font-bold px-2 py-0.5 rounded-full ${
                  healthData?.firebase_active
                    ? 'bg-emerald-50 text-emerald-700 border border-emerald-200'
                    : 'bg-slate-200 text-slate-600'
                }`}>
                  {healthData?.firebase_active ? 'Connected' : 'SQLite Local'}
                </span>
              </div>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}
