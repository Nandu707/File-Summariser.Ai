import React, { useState, useEffect, useCallback, useMemo } from 'react';
import axios from 'axios';
import {
  Users,
  UserCheck,
  UserX,
  ShieldAlert,
  Search,
  RefreshCw,
  Trash2,
  CheckCircle,
  XCircle,
  AlertCircle,
  Loader2,
  Clock,
  Shield,
  UserCheck2,
  RotateCcw
} from 'lucide-react';
import { API_BASE_URL } from '../api';
import { useAuth } from '../context/AuthContext';
import ConfirmModal from '../components/ConfirmModal';

export default function UsersPage({ onPendingCountChange }) {
  const { user: currentUser } = useAuth();
  const [users, setUsers] = useState([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(null);
  const [actionLoadingId, setActionLoadingId] = useState(null);
  const [searchQuery, setSearchQuery] = useState('');
  const [statusFilter, setStatusFilter] = useState('all'); // 'all' | 'pending' | 'approved' | 'rejected' | 'disabled'
  const [actionModal, setActionModal] = useState(null); // { user, action: 'approve' | 'reject' | 'disable' | 'enable' | 'delete' }

  const fetchUsers = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      const res = await axios.get(`${API_BASE_URL}/api/auth/admin/users`);
      if (Array.isArray(res.data)) {
        setUsers(res.data);
        const pendingCount = res.data.filter((u) => u.status === 'pending').length;
        if (onPendingCountChange) {
          onPendingCountChange(pendingCount);
        }
      }
    } catch (err) {
      console.error('Failed to fetch users:', err);
      setError(err.response?.data?.detail || 'Failed to fetch user accounts.');
    } finally {
      setLoading(false);
    }
  }, [onPendingCountChange]);

  useEffect(() => {
    fetchUsers();
  }, [fetchUsers]);

  const modalConfig = useMemo(() => {
    if (!actionModal) return null;
    const { user, action } = actionModal;
    switch (action) {
      case 'approve':
        return {
          title: 'Approve User Account?',
          description: 'Grant this user access to sign in, upload documents, and chat.',
          icon: UserCheck,
          iconVariant: 'emerald',
          confirmText: 'Approve User',
          confirmVariant: 'emerald',
          confirmIcon: UserCheck,
          loadingText: 'Approving user...',
          user
        };
      case 'reject':
        return {
          title: 'Reject User Registration?',
          description: 'Deny registration request. The user will not be able to log in.',
          icon: UserX,
          iconVariant: 'rose',
          confirmText: 'Reject User',
          confirmVariant: 'rose',
          confirmIcon: UserX,
          loadingText: 'Rejecting user...',
          user
        };
      case 'disable':
        return {
          title: 'Disable User Account?',
          description: 'Immediately suspend this user account and block access.',
          icon: ShieldAlert,
          iconVariant: 'amber',
          confirmText: 'Disable User',
          confirmVariant: 'amber',
          confirmIcon: ShieldAlert,
          loadingText: 'Disabling user...',
          user
        };
      case 'enable':
        return {
          title: 'Enable User Account?',
          description: 'Reactivate this account and restore user access.',
          icon: RotateCcw,
          iconVariant: 'emerald',
          confirmText: 'Enable User',
          confirmVariant: 'emerald',
          confirmIcon: RotateCcw,
          loadingText: 'Enabling user...',
          user
        };
      case 'delete':
        return {
          title: 'Delete User Account?',
          description: 'Permanently remove this user account and all their chat history.',
          icon: Trash2,
          iconVariant: 'rose',
          confirmText: 'Delete User',
          confirmVariant: 'rose',
          confirmIcon: Trash2,
          loadingText: 'Deleting user...',
          user
        };
      default:
        return null;
    }
  }, [actionModal]);

  const handleConfirmModalAction = async () => {
    if (!actionModal) return;
    const { user: targetUser, action } = actionModal;
    const userId = targetUser.id;
    setActionLoadingId(userId);
    setError(null);
    try {
      if (action === 'approve') {
        await axios.post(`${API_BASE_URL}/api/auth/admin/users/${userId}/approve`);
      } else if (action === 'reject') {
        await axios.post(`${API_BASE_URL}/api/auth/admin/users/${userId}/reject`);
      } else if (action === 'disable') {
        await axios.post(`${API_BASE_URL}/api/auth/admin/users/${userId}/disable`);
      } else if (action === 'enable') {
        await axios.post(`${API_BASE_URL}/api/auth/admin/users/${userId}/enable`);
      } else if (action === 'delete') {
        await axios.delete(`${API_BASE_URL}/api/auth/admin/users/${userId}`);
      }
      setActionModal(null);
      await fetchUsers();
    } catch (err) {
      setError(err.response?.data?.detail || `Failed to ${action} user.`);
    } finally {
      setActionLoadingId(null);
    }
  };

  // Status counts for filter chips
  const counts = {
    all: users.length,
    pending: users.filter((u) => u.status === 'pending').length,
    approved: users.filter((u) => u.status === 'approved').length,
    rejected: users.filter((u) => u.status === 'rejected').length,
    disabled: users.filter((u) => u.status === 'disabled').length,
  };

  const filteredUsers = users.filter((u) => {
    const matchesSearch =
      (u.name || '').toLowerCase().includes(searchQuery.toLowerCase()) ||
      (u.email || '').toLowerCase().includes(searchQuery.toLowerCase());
    const matchesStatus = statusFilter === 'all' || u.status === statusFilter;
    return matchesSearch && matchesStatus;
  });

  const getStatusBadge = (status) => {
    switch (status) {
      case 'approved':
        return (
          <span className="inline-flex items-center space-x-1 px-2.5 py-0.5 rounded-full text-xs font-semibold bg-emerald-50 text-emerald-700 border border-emerald-200">
            <CheckCircle className="w-3 h-3 text-emerald-600" />
            <span className="capitalize">Approved</span>
          </span>
        );
      case 'pending':
        return (
          <span className="inline-flex items-center space-x-1 px-2.5 py-0.5 rounded-full text-xs font-semibold bg-amber-50 text-amber-700 border border-amber-200 animate-pulse">
            <Clock className="w-3 h-3 text-amber-600" />
            <span className="capitalize">Pending Approval</span>
          </span>
        );
      case 'rejected':
        return (
          <span className="inline-flex items-center space-x-1 px-2.5 py-0.5 rounded-full text-xs font-semibold bg-rose-50 text-rose-700 border border-rose-200">
            <XCircle className="w-3 h-3 text-rose-600" />
            <span className="capitalize">Rejected</span>
          </span>
        );
      case 'disabled':
        return (
          <span className="inline-flex items-center space-x-1 px-2.5 py-0.5 rounded-full text-xs font-semibold bg-slate-100 text-slate-600 border border-slate-200">
            <UserX className="w-3 h-3 text-slate-500" />
            <span className="capitalize">Disabled</span>
          </span>
        );
      default:
        return (
          <span className="inline-flex items-center px-2.5 py-0.5 rounded-full text-xs font-medium bg-slate-100 text-slate-600">
            {status}
          </span>
        );
    }
  };

  return (
    <div className="flex-1 min-h-0 overflow-y-auto custom-scrollbar w-full p-4 sm:p-6 lg:p-8 space-y-6">
      {/* Top Header */}
      <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-4 pb-4 border-b border-slate-200">
        <div>
          <h1 className="text-xl font-bold text-slate-900 tracking-tight flex items-center space-x-2">
            <Shield className="w-5 h-5 text-indigo-600" />
            <span>User Management & Access Control</span>
            {counts.pending > 0 && (
              <span className="px-2 py-0.5 rounded-full text-xs font-bold bg-amber-500 text-white shadow-xs">
                {counts.pending} Pending
              </span>
            )}
          </h1>
          <p className="text-xs text-slate-500 mt-1">
            Review registration requests, approve new accounts, and manage permissions.
          </p>
        </div>

        <div className="flex items-center space-x-3">
          <button
            onClick={fetchUsers}
            disabled={loading}
            className="flex items-center space-x-1.5 px-3 py-1.5 rounded-xl text-xs font-medium text-slate-600 hover:text-slate-900 bg-white border border-slate-200 hover:border-slate-300 shadow-2xs transition-all active:scale-95"
            title="Refresh user list"
          >
            <RefreshCw className={`w-3.5 h-3.5 ${loading ? 'animate-spin text-indigo-600' : ''}`} />
            <span>Refresh</span>
          </button>
        </div>
      </div>

      {/* Error Banner */}
      {error && (
        <div className="p-3.5 rounded-xl bg-rose-50 border border-rose-200 text-xs text-rose-800 flex items-center justify-between">
          <div className="flex items-center space-x-2">
            <AlertCircle className="w-4 h-4 text-rose-600 flex-shrink-0" />
            <span>{error}</span>
          </div>
          <button
            onClick={() => setError(null)}
            className="text-xs font-semibold text-rose-600 hover:text-rose-800 underline ml-2"
          >
            Dismiss
          </button>
        </div>
      )}

      {/* Filters & Search */}
      <div className="flex flex-col md:flex-row md:items-center justify-between gap-3">
        {/* Filter Chips */}
        <div className="flex flex-wrap items-center gap-1.5">
          {[
            { id: 'all', label: 'All Users', count: counts.all },
            { id: 'pending', label: 'Pending', count: counts.pending, highlight: counts.pending > 0 },
            { id: 'approved', label: 'Approved', count: counts.approved },
            { id: 'rejected', label: 'Rejected', count: counts.rejected },
            { id: 'disabled', label: 'Disabled', count: counts.disabled },
          ].map((tab) => {
            const isActive = statusFilter === tab.id;
            return (
              <button
                key={tab.id}
                onClick={() => setStatusFilter(tab.id)}
                className={`flex items-center space-x-1.5 px-3 py-1.5 rounded-xl text-xs font-semibold transition-all ${
                  isActive
                    ? 'bg-indigo-600 text-white shadow-xs'
                    : 'bg-white text-slate-600 hover:bg-slate-100/80 border border-slate-200'
                }`}
              >
                <span>{tab.label}</span>
                <span
                  className={`text-[10px] px-1.5 py-0.2 rounded-full font-bold ${
                    isActive
                      ? 'bg-white/20 text-white'
                      : tab.highlight
                      ? 'bg-amber-100 text-amber-800'
                      : 'bg-slate-100 text-slate-600'
                  }`}
                >
                  {tab.count}
                </span>
              </button>
            );
          })}
        </div>

        {/* Search */}
        <div className="relative w-full md:w-72">
          <Search className="w-4 h-4 text-slate-400 absolute left-3 top-1/2 -translate-y-1/2" />
          <input
            type="text"
            value={searchQuery}
            onChange={(e) => setSearchQuery(e.target.value)}
            placeholder="Search by name or email..."
            className="w-full bg-white border border-slate-200 focus:border-indigo-500 focus:ring-2 focus:ring-indigo-100 rounded-xl pl-9 pr-3 py-1.5 text-xs text-slate-900 placeholder:text-slate-400 shadow-2xs transition-all"
          />
        </div>
      </div>

      {/* Users Table */}
      <div className="bg-white rounded-2xl border border-slate-200 shadow-sm overflow-hidden">
        {loading && users.length === 0 ? (
          <div className="py-16 text-center text-xs text-slate-500">
            <Loader2 className="w-6 h-6 animate-spin text-indigo-600 mx-auto mb-2" />
            <span>Loading user accounts...</span>
          </div>
        ) : filteredUsers.length === 0 ? (
          <div className="py-16 text-center text-xs text-slate-500">
            <Users className="w-8 h-8 text-slate-300 mx-auto mb-2" />
            <p className="font-semibold text-slate-700">No users found</p>
            <p className="text-slate-400 mt-0.5">
              {searchQuery ? 'Try matching a different name or email' : 'No accounts with this status'}
            </p>
          </div>
        ) : (
          <div className="overflow-x-auto">
            <table className="w-full text-left text-xs">
              <thead className="bg-slate-50 border-b border-slate-200 text-slate-600 font-semibold uppercase tracking-wider text-[10px]">
                <tr>
                  <th className="px-5 py-3.5">User</th>
                  <th className="px-5 py-3.5">Email</th>
                  <th className="px-5 py-3.5">Role</th>
                  <th className="px-5 py-3.5">Status</th>
                  <th className="px-5 py-3.5">Signed Up</th>
                  <th className="px-5 py-3.5 text-right">Actions</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-slate-100 text-slate-700">
                {filteredUsers.map((u) => {
                  const isSelf = u.id === currentUser?.id || u.role === 'admin';
                  const isOperating = actionLoadingId === u.id;
                  const dateStr = u.created_at ? new Date(u.created_at).toLocaleDateString(undefined, {
                    year: 'numeric',
                    month: 'short',
                    day: 'numeric',
                    hour: '2-digit',
                    minute: '2-digit'
                  }) : '—';

                  return (
                    <tr key={u.id} className="hover:bg-slate-50/70 transition-colors">
                      {/* Name & Avatar */}
                      <td className="px-5 py-4 whitespace-nowrap">
                        <div className="flex items-center space-x-3">
                          <div className="w-8 h-8 rounded-full bg-gradient-to-tr from-indigo-600 to-blue-500 text-white font-bold flex items-center justify-center text-xs shadow-xs">
                            {(u.name || u.email || 'U').charAt(0).toUpperCase()}
                          </div>
                          <div>
                            <div className="font-semibold text-slate-900 flex items-center space-x-1.5">
                              <span>{u.name || 'Unnamed User'}</span>
                              {isSelf && (
                                <span className="text-[10px] bg-indigo-50 text-indigo-700 font-semibold px-1.5 py-0.2 rounded border border-indigo-200">
                                  You
                                </span>
                              )}
                            </div>
                            <div className="text-[11px] text-slate-400 font-mono">ID: {u.id.substring(0, 12)}</div>
                          </div>
                        </div>
                      </td>

                      {/* Email */}
                      <td className="px-5 py-4 whitespace-nowrap font-medium text-slate-800">
                        {u.email}
                      </td>

                      {/* Role */}
                      <td className="px-5 py-4 whitespace-nowrap">
                        {u.role === 'admin' ? (
                          <span className="inline-flex items-center space-x-1 px-2.5 py-0.5 rounded-full text-[11px] font-bold bg-indigo-50 text-indigo-700 border border-indigo-200">
                            <Shield className="w-3 h-3 text-indigo-600" />
                            <span>Admin</span>
                          </span>
                        ) : (
                          <span className="inline-flex items-center px-2.5 py-0.5 rounded-full text-[11px] font-medium bg-slate-100 text-slate-600">
                            User
                          </span>
                        )}
                      </td>

                      {/* Status */}
                      <td className="px-5 py-4 whitespace-nowrap">
                        {getStatusBadge(u.status)}
                      </td>

                      {/* Created At */}
                      <td className="px-5 py-4 whitespace-nowrap text-slate-500 text-[11px]">
                        {dateStr}
                      </td>

                      {/* Actions */}
                      <td className="px-5 py-4 whitespace-nowrap text-right">
                        {isSelf ? (
                          <span className="text-[11px] text-slate-400 italic">Protected Admin Account</span>
                        ) : (
                          <div className="inline-flex items-center space-x-1.5">
                            {/* Pending State Actions: Approve & Reject */}
                            {u.status === 'pending' && (
                              <>
                                <button
                                  onClick={() => setActionModal({ user: u, action: 'approve' })}
                                  disabled={isOperating}
                                  className="inline-flex items-center space-x-1 px-2.5 py-1 rounded-lg text-xs font-semibold bg-emerald-50 text-emerald-700 hover:bg-emerald-100 border border-emerald-200 transition-colors cursor-pointer active:scale-95"
                                  title="Approve user registration"
                                >
                                  {isOperating ? <Loader2 className="w-3 h-3 animate-spin" /> : <UserCheck className="w-3.5 h-3.5" />}
                                  <span>Approve</span>
                                </button>
                                <button
                                  onClick={() => setActionModal({ user: u, action: 'reject' })}
                                  disabled={isOperating}
                                  className="inline-flex items-center space-x-1 px-2.5 py-1 rounded-lg text-xs font-semibold bg-rose-50 text-rose-700 hover:bg-rose-100 border border-rose-200 transition-colors cursor-pointer active:scale-95"
                                  title="Reject user registration"
                                >
                                  <UserX className="w-3.5 h-3.5" />
                                  <span>Reject</span>
                                </button>
                              </>
                            )}

                            {/* Approved State Action: Disable */}
                            {u.status === 'approved' && (
                              <button
                                onClick={() => setActionModal({ user: u, action: 'disable' })}
                                disabled={isOperating}
                                className="inline-flex items-center space-x-1 px-2.5 py-1 rounded-lg text-xs font-semibold bg-amber-50 text-amber-700 hover:bg-amber-100 border border-amber-200 transition-colors cursor-pointer active:scale-95"
                                title="Disable user access immediately"
                              >
                                {isOperating ? <Loader2 className="w-3 h-3 animate-spin" /> : <ShieldAlert className="w-3.5 h-3.5" />}
                                <span>Disable</span>
                              </button>
                            )}

                            {/* Disabled State Action: Re-enable */}
                            {u.status === 'disabled' && (
                              <button
                                onClick={() => setActionModal({ user: u, action: 'enable' })}
                                disabled={isOperating}
                                className="inline-flex items-center space-x-1 px-2.5 py-1 rounded-lg text-xs font-semibold bg-emerald-50 text-emerald-700 hover:bg-emerald-100 border border-emerald-200 transition-colors cursor-pointer active:scale-95"
                                title="Re-enable account"
                              >
                                {isOperating ? <Loader2 className="w-3 h-3 animate-spin" /> : <RotateCcw className="w-3.5 h-3.5" />}
                                <span>Re-enable</span>
                              </button>
                            )}

                            {/* Rejected State Action: Re-approve */}
                            {u.status === 'rejected' && (
                              <button
                                onClick={() => setActionModal({ user: u, action: 'approve' })}
                                disabled={isOperating}
                                className="inline-flex items-center space-x-1 px-2.5 py-1 rounded-lg text-xs font-semibold bg-emerald-50 text-emerald-700 hover:bg-emerald-100 border border-emerald-200 transition-colors cursor-pointer active:scale-95"
                                title="Approve account"
                              >
                                {isOperating ? <Loader2 className="w-3 h-3 animate-spin" /> : <UserCheck className="w-3.5 h-3.5" />}
                                <span>Approve</span>
                              </button>
                            )}

                            {/* Delete User */}
                            <button
                              onClick={() => setActionModal({ user: u, action: 'delete' })}
                              disabled={isOperating}
                              className="p-1 rounded-lg text-slate-400 hover:text-rose-600 hover:bg-rose-50 transition-colors cursor-pointer active:scale-95"
                              title="Delete user account and all their chats"
                            >
                              <Trash2 className="w-3.5 h-3.5" />
                            </button>
                          </div>
                        )}
                      </td>
                    </tr>
                  );
                })}
              </tbody>
            </table>
          </div>
        )}
      </div>

      {/* Confirmation Modal for Approval, Rejection, Disable, Enable, and Delete (shared popup component) */}
      {actionModal && modalConfig && (
        <ConfirmModal
          isOpen={Boolean(actionModal)}
          onClose={() => setActionModal(null)}
          onConfirm={handleConfirmModalAction}
          title={modalConfig.title}
          description={modalConfig.description}
          icon={modalConfig.icon}
          iconVariant={modalConfig.iconVariant}
          confirmText={modalConfig.confirmText}
          confirmVariant={modalConfig.confirmVariant}
          confirmIcon={modalConfig.confirmIcon}
          isLoading={actionLoadingId === actionModal.user.id}
          loadingText={modalConfig.loadingText}
          user={modalConfig.user}
        />
      )}
    </div>
  );
}
