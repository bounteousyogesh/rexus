import { useEffect, useState, type FormEvent } from 'react';
import { authApi } from '../api';
import type { AuthUser } from '../types';

export default function AdminPage() {
  const [users, setUsers] = useState<AuthUser[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState('');

  // Create user form
  const [showCreate, setShowCreate] = useState(false);
  const [newUsername, setNewUsername] = useState('');
  const [newEmail, setNewEmail] = useState('');
  const [newPassword, setNewPassword] = useState('');
  const [newRole, setNewRole] = useState('analyst');
  const [createError, setCreateError] = useState('');

  // Reset password modal
  const [resetTarget, setResetTarget] = useState<AuthUser | null>(null);
  const [resetPassword, setResetPassword] = useState('');
  const [resetError, setResetError] = useState('');

  async function loadUsers() {
    setLoading(true);
    try {
      const data = await authApi.listUsers();
      setUsers(data);
      setError('');
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to load users');
    } finally {
      setLoading(false);
    }
  }

  useEffect(() => { loadUsers(); }, []);

  async function handleCreate(e: FormEvent) {
    e.preventDefault();
    setCreateError('');
    try {
      await authApi.createUser({
        username: newUsername,
        password: newPassword,
        email: newEmail || undefined,
        role: newRole,
      });
      setNewUsername('');
      setNewEmail('');
      setNewPassword('');
      setNewRole('analyst');
      setShowCreate(false);
      await loadUsers();
    } catch (err) {
      setCreateError(err instanceof Error ? err.message : 'Create failed');
    }
  }

  async function toggleActive(user: AuthUser) {
    try {
      if (user.is_active) {
        await authApi.deactivateUser(user.id);
      } else {
        await authApi.updateUser(user.id, { is_active: true });
      }
      await loadUsers();
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Update failed');
    }
  }

  async function handleResetPassword(e: FormEvent) {
    e.preventDefault();
    if (!resetTarget) return;
    setResetError('');
    try {
      await authApi.updateUser(resetTarget.id, { password: resetPassword });
      setResetTarget(null);
      setResetPassword('');
    } catch (err) {
      setResetError(err instanceof Error ? err.message : 'Reset failed');
    }
  }

  function formatDate(d: string | null | undefined) {
    if (!d) return '--';
    return new Date(d).toLocaleString();
  }

  return (
    <div className="p-8 max-w-5xl mx-auto">
      <div className="flex items-center justify-between mb-6">
        <h1 className="text-2xl font-bold text-slate-900">User Management</h1>
        <button
          onClick={() => setShowCreate(!showCreate)}
          className="bg-red-500 hover:bg-red-600 text-white px-4 py-2 rounded-lg text-sm font-medium"
        >
          {showCreate ? 'Cancel' : 'Create User'}
        </button>
      </div>

      {error && (
        <div className="bg-red-50 text-red-700 text-sm px-4 py-3 rounded-lg border border-red-200 mb-4">
          {error}
        </div>
      )}

      {/* Create User Form */}
      {showCreate && (
        <div className="bg-white rounded-xl border border-slate-200 p-6 mb-6">
          <h2 className="text-lg font-semibold text-slate-800 mb-4">Create New User</h2>
          <form onSubmit={handleCreate} className="grid grid-cols-2 gap-4">
            <div>
              <label className="block text-sm font-medium text-slate-700 mb-1">Username</label>
              <input
                type="text"
                required
                minLength={2}
                value={newUsername}
                onChange={(e) => setNewUsername(e.target.value)}
                className="w-full px-3 py-2 border border-slate-300 rounded-lg text-sm focus:outline-none focus:ring-2 focus:ring-red-500"
              />
            </div>
            <div>
              <label className="block text-sm font-medium text-slate-700 mb-1">Email</label>
              <input
                type="email"
                value={newEmail}
                onChange={(e) => setNewEmail(e.target.value)}
                className="w-full px-3 py-2 border border-slate-300 rounded-lg text-sm focus:outline-none focus:ring-2 focus:ring-red-500"
              />
            </div>
            <div>
              <label className="block text-sm font-medium text-slate-700 mb-1">Password</label>
              <input
                type="password"
                required
                minLength={8}
                value={newPassword}
                onChange={(e) => setNewPassword(e.target.value)}
                className="w-full px-3 py-2 border border-slate-300 rounded-lg text-sm focus:outline-none focus:ring-2 focus:ring-red-500"
              />
            </div>
            <div>
              <label className="block text-sm font-medium text-slate-700 mb-1">Role</label>
              <select
                value={newRole}
                onChange={(e) => setNewRole(e.target.value)}
                className="w-full px-3 py-2 border border-slate-300 rounded-lg text-sm focus:outline-none focus:ring-2 focus:ring-red-500"
              >
                <option value="analyst">Analyst</option>
                <option value="viewer">Viewer</option>
                <option value="admin">Admin</option>
              </select>
            </div>
            <div className="col-span-2 flex items-center gap-3">
              <button
                type="submit"
                className="bg-slate-900 hover:bg-slate-800 text-white px-4 py-2 rounded-lg text-sm font-medium"
              >
                Create
              </button>
              {createError && (
                <span className="text-red-600 text-sm">{createError}</span>
              )}
            </div>
          </form>
        </div>
      )}

      {/* Users Table */}
      {loading ? (
        <div className="text-slate-500 text-sm">Loading users...</div>
      ) : (
        <div className="bg-white rounded-xl border border-slate-200 overflow-hidden">
          <table className="w-full text-sm">
            <thead>
              <tr className="bg-slate-50 text-slate-600 text-left">
                <th className="px-4 py-3 font-medium">Username</th>
                <th className="px-4 py-3 font-medium">Email</th>
                <th className="px-4 py-3 font-medium">Role</th>
                <th className="px-4 py-3 font-medium">Active</th>
                <th className="px-4 py-3 font-medium">Last Login</th>
                <th className="px-4 py-3 font-medium">Actions</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-slate-100">
              {users.map((u) => (
                <tr key={u.id} className="hover:bg-slate-50">
                  <td className="px-4 py-3 font-medium text-slate-900">{u.username}</td>
                  <td className="px-4 py-3 text-slate-600">{u.email || '--'}</td>
                  <td className="px-4 py-3">
                    <span
                      className={`inline-block px-2 py-0.5 rounded text-xs font-medium ${
                        u.role === 'admin'
                          ? 'bg-purple-100 text-purple-700'
                          : u.role === 'analyst'
                          ? 'bg-blue-100 text-blue-700'
                          : 'bg-slate-100 text-slate-600'
                      }`}
                    >
                      {u.role}
                    </span>
                  </td>
                  <td className="px-4 py-3">
                    <span
                      className={`inline-block w-2 h-2 rounded-full ${
                        u.is_active ? 'bg-green-500' : 'bg-red-400'
                      }`}
                    />
                    <span className="ml-2 text-slate-600">{u.is_active ? 'Yes' : 'No'}</span>
                  </td>
                  <td className="px-4 py-3 text-slate-500">{formatDate(u.last_login)}</td>
                  <td className="px-4 py-3 space-x-2">
                    <button
                      onClick={() => toggleActive(u)}
                      className="text-xs px-2 py-1 rounded border border-slate-300 hover:bg-slate-100"
                    >
                      {u.is_active ? 'Deactivate' : 'Activate'}
                    </button>
                    <button
                      onClick={() => { setResetTarget(u); setResetPassword(''); setResetError(''); }}
                      className="text-xs px-2 py-1 rounded border border-slate-300 hover:bg-slate-100"
                    >
                      Reset Password
                    </button>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}

      {/* Reset Password Modal */}
      {resetTarget && (
        <div className="fixed inset-0 bg-black/40 flex items-center justify-center z-50">
          <div className="bg-white rounded-xl p-6 w-full max-w-sm shadow-xl">
            <h3 className="text-lg font-semibold text-slate-900 mb-4">
              Reset password for {resetTarget.username}
            </h3>
            <form onSubmit={handleResetPassword} className="space-y-4">
              <div>
                <label className="block text-sm font-medium text-slate-700 mb-1">New Password</label>
                <input
                  type="password"
                  required
                  minLength={8}
                  value={resetPassword}
                  onChange={(e) => setResetPassword(e.target.value)}
                  className="w-full px-3 py-2 border border-slate-300 rounded-lg text-sm focus:outline-none focus:ring-2 focus:ring-red-500"
                />
              </div>
              {resetError && (
                <div className="text-red-600 text-sm">{resetError}</div>
              )}
              <div className="flex gap-3">
                <button
                  type="submit"
                  className="bg-red-500 hover:bg-red-600 text-white px-4 py-2 rounded-lg text-sm font-medium"
                >
                  Reset
                </button>
                <button
                  type="button"
                  onClick={() => setResetTarget(null)}
                  className="border border-slate-300 px-4 py-2 rounded-lg text-sm hover:bg-slate-50"
                >
                  Cancel
                </button>
              </div>
            </form>
          </div>
        </div>
      )}
    </div>
  );
}
