import React, { useState, useEffect } from 'react';
import { Database, MessageSquare, Layers, LogOut, User, Loader2, Shield } from 'lucide-react';
import { useAuth } from '../context/AuthContext';
import ConfirmModal from './ConfirmModal';

export default function Navbar({ activeTab = 'chat', onSelectTab, backendStatus, docCount = 0, pendingCount = 0 }) {
  const { user, logout } = useAuth();
  const [showLogoutConfirm, setShowLogoutConfirm] = useState(false);
  const [isLoggingOut, setIsLoggingOut] = useState(false);

  const isAdmin = user?.role === 'admin';

  const navItems = [
    { id: 'chat', label: 'Chat & Q&A', icon: MessageSquare },
    {
      id: 'documents',
      label: isAdmin ? 'Files' : 'Shared Documents',
      icon: Layers,
      badge: docCount,
    },
    ...(isAdmin
      ? [
          {
            id: 'users',
            label: 'Users',
            icon: Shield,
            badge: pendingCount,
            isPendingBadge: true,
          },
        ]
      : []),
  ];

  useEffect(() => {
    if (!showLogoutConfirm) return;
    const handleKeyDown = (e) => {
      if (e.key === 'Escape' && !isLoggingOut) {
        setShowLogoutConfirm(false);
      }
    };
    window.addEventListener('keydown', handleKeyDown);
    return () => window.removeEventListener('keydown', handleKeyDown);
  }, [showLogoutConfirm, isLoggingOut]);

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

  return (
    <header className="sticky top-0 z-40 border-b border-slate-200/90 bg-white/85 backdrop-blur-md shadow-xs">
      <div className="w-full px-4 sm:px-6 lg:px-8">
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
                          item.isPendingBadge
                            ? 'bg-amber-500 text-white animate-pulse'
                            : isActive
                            ? 'bg-indigo-600 text-white'
                            : 'bg-slate-200 text-slate-700'
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

            {/* User Profile Badge & Logout */}
            {user && (
              <div className="flex items-center space-x-2 pl-2 border-l border-slate-200">
                <div className="flex items-center space-x-2 px-2.5 py-1.5 rounded-xl bg-slate-100/80 border border-slate-200 text-slate-700 text-xs">
                  <div className="w-6 h-6 rounded-lg bg-indigo-600 text-white flex items-center justify-center font-bold text-xs shadow-xs">
                    {(user.name || user.email || 'U').charAt(0).toUpperCase()}
                  </div>
                  <span className="font-semibold max-w-[120px] truncate hidden md:inline">
                    {user.name || user.email}
                  </span>
                </div>

                <button
                  onClick={() => setShowLogoutConfirm(true)}
                  title="Log out of session"
                  className="flex items-center space-x-1 px-3 py-1.5 rounded-xl text-xs font-medium text-slate-600 hover:text-red-600 hover:bg-red-50 border border-slate-200 hover:border-red-200 transition-all cursor-pointer active:scale-95"
                >
                  <LogOut className="w-3.5 h-3.5" />
                  <span className="hidden sm:inline">Logout</span>
                </button>
              </div>
            )}
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
                    <span className={`text-[10px] px-1.5 rounded-full font-bold ${
                      item.isPendingBadge
                        ? 'bg-amber-500 text-white animate-pulse'
                        : 'bg-slate-200 text-slate-700'
                    }`}>
                      {item.badge}
                    </span>
                  )}
                </button>
              );
            })}
          </div>
        )}
      </div>

      {/* Logout Confirmation Dialog */}
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
    </header>
  );
}
