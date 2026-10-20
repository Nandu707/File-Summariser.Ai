import { Database, MessageSquare, Layers } from 'lucide-react';

export default function Navbar({ activeTab = 'chat', onSelectTab, backendStatus, docCount = 0 }) {
  const navItems = [
    { id: 'chat', label: 'Chat & Q&A', icon: MessageSquare },
    { id: 'documents', label: 'Documents & Upload', icon: Layers, badge: docCount },
  ];

  return (
    <header className="sticky top-0 z-40 border-b border-slate-200/90 bg-white/85 backdrop-blur-md shadow-xs">
      <div className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8">
        <div className="flex items-center justify-between h-16">
          {/* Logo & Brand */}
          <div className="flex items-center space-x-6">
            <div 
              onClick={() => onSelectTab && onSelectTab('chat')}
              className="flex items-center space-x-3 cursor-pointer group"
            >
              <div className="w-10 h-10 rounded-xl bg-gradient-to-tr from-indigo-600 via-blue-600 to-sky-500 p-[1.5px] shadow-sm shadow-indigo-500/20 group-hover:scale-105 transition-transform">
                <div className="w-full h-full bg-white rounded-[10px] flex items-center justify-center">
                  <Database className="w-5 h-5 text-indigo-600" />
                </div>
              </div>
              <div>
                <div className="flex items-center space-x-2">
                  <span className="font-extrabold text-lg tracking-tight bg-gradient-to-r from-slate-900 via-indigo-950 to-blue-900 bg-clip-text text-transparent">
                    File Summariser.Ai
                  </span>
                  <span className="text-[10px] uppercase font-bold tracking-wider px-2 py-0.5 rounded-full bg-indigo-50 text-indigo-700 border border-indigo-200/80">
                    RAG Engine
                  </span>
                </div>
              </div>
            </div>

            {/* Navigation Tabs (Desktop) */}
            {onSelectTab && (
              <nav className="hidden md:flex items-center space-x-1.5 pl-5 border-l border-slate-200">
                {navItems.map((item) => {
                  const Icon = item.icon;
                  const isActive = activeTab === item.id;
                  return (
                    <button
                      key={item.id}
                      onClick={() => onSelectTab(item.id)}
                      className={`flex items-center space-x-2 px-4 py-2 rounded-xl text-xs font-semibold transition-all ${
                        isActive
                          ? 'bg-indigo-50 text-indigo-700 shadow-xs border border-indigo-200/80'
                          : 'text-slate-600 hover:text-slate-900 hover:bg-slate-100/70 border border-transparent'
                      }`}
                    >
                      <Icon className={`w-4 h-4 ${isActive ? 'text-indigo-600' : 'text-slate-400'}`} />
                      <span>{item.label}</span>
                      {item.badge !== undefined && item.badge > 0 && (
                        <span className={`text-[10px] px-2 py-0.5 rounded-full font-bold ${
                          isActive ? 'bg-indigo-600 text-white' : 'bg-slate-200 text-slate-700'
                        }`}>
                          {item.badge}
                        </span>
                      )}
                    </button>
                  );
                })}
              </nav>
            )}
          </div>

          {/* Right Action & Status Indicators */}
          <div className="flex items-center space-x-3">
            {/* Backend Health Badge */}
            <div 
              className={`flex items-center space-x-1.5 px-3 py-1.5 rounded-full text-xs font-medium border transition-colors ${
                backendStatus === 'healthy'
                  ? 'bg-emerald-50 text-emerald-700 border-emerald-200 shadow-2xs'
                  : backendStatus === 'checking'
                  ? 'bg-amber-50 text-amber-700 border-amber-200'
                  : 'bg-rose-50 text-rose-700 border-rose-200'
              }`}
              title={backendStatus === 'healthy' ? 'FastAPI Backend Online' : 'Connecting to Backend'}
            >
              <span className={`w-2 h-2 rounded-full ${
                backendStatus === 'healthy' ? 'bg-emerald-500 animate-pulse' : 'bg-rose-500'
              }`} />
              <span className="hidden sm:inline font-medium">
                {backendStatus === 'healthy' ? 'API Online' : backendStatus === 'checking' ? 'Connecting...' : 'API Offline'}
              </span>
            </div>


          </div>
        </div>

        {/* Mobile Navigation Bar */}
        {onSelectTab && (
          <div className="flex md:hidden items-center justify-around py-2 border-t border-slate-100">
            {navItems.map((item) => {
              const Icon = item.icon;
              const isActive = activeTab === item.id;
              return (
                <button
                  key={item.id}
                  onClick={() => onSelectTab(item.id)}
                  className={`flex items-center space-x-2 px-4 py-1.5 rounded-lg text-xs font-medium ${
                    isActive ? 'bg-indigo-50 text-indigo-700 font-bold' : 'text-slate-600'
                  }`}
                >
                  <Icon className="w-3.5 h-3.5" />
                  <span>{item.label}</span>
                  {item.badge !== undefined && item.badge > 0 && (
                    <span className="text-[10px] px-1.5 rounded-full bg-slate-200 text-slate-700 font-bold">
                      {item.badge}
                    </span>
                  )}
                </button>
              );
            })}
          </div>
        )}
      </div>
    </header>
  );
}
