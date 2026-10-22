import React, { useEffect } from 'react';
import { createPortal } from 'react-dom';
import { X, Loader2 } from 'lucide-react';

/**
 * Reusable confirmation modal matching the exact design system of the logout modal.
 *
 * Props:
 * - isOpen: boolean
 * - onClose: () => void
 * - onConfirm: () => void | Promise<void>
 * - title: string
 * - description: string (one line)
 * - icon: LucideIcon component (displayed in top badge)
 * - iconVariant: 'rose' | 'emerald' | 'amber' | 'indigo' | 'slate' (default: 'rose')
 * - confirmText: string (e.g. 'Approve User', 'Yes, Log out')
 * - confirmVariant: 'rose' | 'emerald' | 'amber' | 'indigo' (default: 'rose')
 * - confirmIcon: optional LucideIcon for confirm button
 * - cancelText: string (default: 'Cancel')
 * - isLoading: boolean
 * - loadingText: string (default: 'Processing...')
 * - user: optional { name, email, role, status }
 */
export default function ConfirmModal({
  isOpen,
  onClose,
  onConfirm,
  title,
  description,
  icon: Icon,
  iconVariant = 'rose',
  confirmText = 'Confirm',
  confirmVariant = 'rose',
  confirmIcon: ConfirmIcon,
  cancelText = 'Cancel',
  isLoading = false,
  loadingText = 'Processing...',
  user = null
}) {
  useEffect(() => {
    if (!isOpen) return;
    const handleKeyDown = (e) => {
      if (e.key === 'Escape' && !isLoading) {
        onClose();
      }
    };
    window.addEventListener('keydown', handleKeyDown);
    return () => window.removeEventListener('keydown', handleKeyDown);
  }, [isOpen, isLoading, onClose]);

  if (!isOpen || typeof document === 'undefined') return null;

  const iconStyles = {
    rose: 'bg-rose-50 dark:bg-rose-950/50 border-rose-200/80 dark:border-rose-900/60 text-rose-600 dark:text-rose-400',
    emerald: 'bg-emerald-50 dark:bg-emerald-950/50 border-emerald-200/80 dark:border-emerald-800/60 text-emerald-600 dark:text-emerald-400',
    amber: 'bg-amber-50 dark:bg-amber-950/50 border-amber-200/80 dark:border-amber-800/60 text-amber-600 dark:text-amber-400',
    indigo: 'bg-indigo-50 dark:bg-indigo-950/50 border-indigo-200/80 dark:border-indigo-800/60 text-indigo-600 dark:text-indigo-400',
    slate: 'bg-slate-100 dark:bg-neutral-800 border-slate-200/80 dark:border-neutral-700 text-slate-600 dark:text-neutral-300'
  }[iconVariant] || 'bg-rose-50 dark:bg-rose-950/50 border-rose-200/80 dark:border-rose-900/60 text-rose-600 dark:text-rose-400';

  const buttonStyles = {
    rose: 'bg-gradient-to-r from-rose-600 to-red-600 hover:from-rose-500 hover:to-red-500 shadow-rose-600/25',
    emerald: 'bg-gradient-to-r from-emerald-600 to-teal-600 hover:from-emerald-500 hover:to-teal-500 shadow-emerald-600/25',
    amber: 'bg-gradient-to-r from-amber-600 to-orange-600 hover:from-amber-500 hover:to-orange-500 shadow-amber-600/25',
    indigo: 'bg-gradient-to-r from-indigo-600 to-blue-600 hover:from-indigo-500 hover:to-blue-500 shadow-indigo-600/25'
  }[confirmVariant] || 'bg-gradient-to-r from-rose-600 to-red-600 hover:from-rose-500 hover:to-red-500 shadow-rose-600/25';

  return createPortal(
    <div
      role="dialog"
      aria-modal="true"
      aria-labelledby="confirm-dialog-title"
      className="fixed inset-0 z-[9999] flex items-center justify-center p-4 bg-slate-900/60 backdrop-blur-sm animate-in fade-in duration-200"
      onClick={(e) => {
        if (e.target === e.currentTarget && !isLoading) onClose();
      }}
    >
      <div
        className="w-full max-w-md bg-white dark:bg-[#1e1e1e] rounded-2xl border border-slate-200/90 dark:border-neutral-800 shadow-2xl p-6 sm:p-7 relative overflow-hidden animate-in zoom-in-95 duration-200"
        onClick={(e) => e.stopPropagation()}
      >
        {/* Close Button */}
        <button
          type="button"
          onClick={() => !isLoading && onClose()}
          disabled={isLoading}
          className="absolute top-4 right-4 p-1.5 rounded-xl text-slate-400 dark:text-neutral-400 hover:text-slate-700 dark:hover:text-white hover:bg-slate-100 dark:hover:bg-neutral-800 transition-colors cursor-pointer disabled:opacity-50"
          aria-label="Close dialog"
        >
          <X className="w-4 h-4" />
        </button>

        <div className="flex items-start space-x-4">
          {Icon && (
            <div className={`w-12 h-12 rounded-2xl border flex items-center justify-center flex-shrink-0 shadow-2xs ${iconStyles}`}>
              <Icon className="w-6 h-6" />
            </div>
          )}

          <div className="flex-1 min-w-0 pt-0.5">
            <h3 id="confirm-dialog-title" className="text-base font-bold text-slate-900 dark:text-white tracking-tight">
              {title}
            </h3>
            {description && (
              <p className="mt-1 text-xs text-slate-500 dark:text-neutral-400 truncate">
                {description}
              </p>
            )}

            {user && (
              <div className="mt-3.5 py-2 px-3 rounded-xl bg-slate-50 dark:bg-neutral-800/80 border border-slate-200/80 dark:border-neutral-700 flex items-center space-x-2.5">
                <div className="w-6 h-6 rounded-lg bg-indigo-600 text-white flex items-center justify-center font-bold text-xs flex-shrink-0 shadow-2xs">
                  {(user.name || user.email || 'U').charAt(0).toUpperCase()}
                </div>
                <div className="min-w-0 flex-1">
                  <p className="text-xs font-semibold text-slate-800 dark:text-neutral-200 truncate">
                    {user.name || 'User'}
                  </p>
                  <p className="text-[11px] text-slate-500 dark:text-neutral-400 truncate">
                    {user.email}
                  </p>
                </div>
                {user.status && (
                  <span className={`text-[10px] font-semibold px-2 py-0.5 rounded-full capitalize ${
                    user.status === 'approved' ? 'bg-emerald-100 dark:bg-emerald-950/60 text-emerald-700 dark:text-emerald-400 border border-emerald-200 dark:border-emerald-800/60' :
                    user.status === 'pending' ? 'bg-amber-100 dark:bg-amber-950/60 text-amber-700 dark:text-amber-400 border border-amber-200 dark:border-amber-800/60' :
                    user.status === 'rejected' ? 'bg-rose-100 dark:bg-rose-950/60 text-rose-700 dark:text-rose-400 border border-rose-200 dark:border-rose-900/60' :
                    'bg-slate-200 dark:bg-neutral-700 text-slate-700 dark:text-neutral-300'
                  }`}>
                    {user.status}
                  </span>
                )}
              </div>
            )}
          </div>
        </div>

        {/* Action Buttons */}
        <div className="mt-6 flex items-center justify-end space-x-2.5 pt-4 border-t border-slate-100 dark:border-neutral-800">
          <button
            type="button"
            onClick={onClose}
            disabled={isLoading}
            className="px-4 py-2 rounded-xl text-xs font-semibold text-slate-700 dark:text-neutral-300 hover:text-slate-900 dark:hover:text-white bg-slate-100 dark:bg-neutral-800 hover:bg-slate-200/80 dark:hover:bg-neutral-700 border border-slate-200/60 dark:border-neutral-700 transition-all cursor-pointer active:scale-95 disabled:opacity-50"
          >
            {cancelText}
          </button>

          <button
            type="button"
            onClick={onConfirm}
            disabled={isLoading}
            className={`inline-flex items-center space-x-1.5 px-4 py-2 rounded-xl text-xs font-semibold text-white shadow-xs active:scale-95 transition-all cursor-pointer disabled:opacity-50 ${buttonStyles}`}
          >
            {isLoading ? (
              <>
                <Loader2 className="w-3.5 h-3.5 animate-spin" />
                <span>{loadingText}</span>
              </>
            ) : (
              <>
                {ConfirmIcon && <ConfirmIcon className="w-3.5 h-3.5" />}
                <span>{confirmText}</span>
              </>
            )}
          </button>
        </div>
      </div>
    </div>,
    document.body
  );
}
