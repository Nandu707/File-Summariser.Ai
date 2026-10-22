import React, { useState } from 'react';
import { Eye, EyeOff } from 'lucide-react';
import { useAuth } from '../context/AuthContext';

export default function SignupPage({ onNavigateToLogin }) {
  const { signup } = useAuth();
  const [name, setName] = useState('');
  const [email, setEmail] = useState('');
  const [password, setPassword] = useState('');
  const [confirmPassword, setConfirmPassword] = useState('');
  const [showPassword, setShowPassword] = useState(false);
  const [showConfirmPassword, setShowConfirmPassword] = useState(false);
  const [error, setError] = useState('');
  const [nameError, setNameError] = useState('');
  const [emailError, setEmailError] = useState('');
  const [passwordError, setPasswordError] = useState('');
  const [confirmPasswordError, setConfirmPasswordError] = useState('');
  const [isSubmitting, setIsSubmitting] = useState(false);
  const [signupSuccess, setSignupSuccess] = useState(false);

  const emailRegex = /^[^\s@]+@[^\s@]+\.[^\s@]+$/;

  const validateName = (val) => {
    if (!val.trim()) return 'Please enter your full name.';
    return '';
  };

  const validateEmail = (val) => {
    const trimmed = val.trim();
    if (!trimmed) return 'Please enter your email address.';
    if (!emailRegex.test(trimmed)) return 'Please enter a valid email address (e.g. name@example.com).';
    return '';
  };

  const validatePassword = (val) => {
    if (!val) return 'Please enter your password.';
    if (val.length < 8) return 'Password must be at least 8 characters long.';
    return '';
  };

  const validateConfirmPassword = (val, passVal) => {
    if (!val) return 'Please confirm your password.';
    if (val !== (passVal !== undefined ? passVal : password)) return 'Passwords do not match.';
    return '';
  };

  const handleSubmit = async (e) => {
    e.preventDefault();
    setError('');

    const nErr = validateName(name);
    const eErr = validateEmail(email);
    const pErr = validatePassword(password);
    const cpErr = validateConfirmPassword(confirmPassword, password);

    setNameError(nErr);
    setEmailError(eErr);
    setPasswordError(pErr);
    setConfirmPasswordError(cpErr);

    if (nErr || eErr || pErr || cpErr) {
      return;
    }

    try {
      setIsSubmitting(true);
      const res = await signup(name.trim(), email.trim().toLowerCase(), password);
      setSignupSuccess(true);
    } catch (err) {
      const msg = err.response?.data?.detail || err.message || 'Failed to create account. Please try again.';
      setError(msg);
      if (msg.toLowerCase().includes('email')) {
        setEmailError(msg);
      }
      if (msg.toLowerCase().includes('password')) {
        setPasswordError(msg);
      }
    } finally {
      setIsSubmitting(false);
    }
  };

  if (signupSuccess) {
    return (
      <div className="min-h-screen w-full flex items-center justify-center bg-gradient-to-br from-indigo-50/70 via-slate-50 to-violet-50/60 relative overflow-hidden px-4 font-sans text-slate-800 py-10">
        <div className="w-full max-w-md relative z-10">
          <div className="bg-white/95 backdrop-blur-xl border border-slate-200/90 rounded-3xl p-8 shadow-xl text-center animate-in fade-in zoom-in-95 duration-200">
            <div className="w-16 h-16 rounded-2xl bg-amber-50 border border-amber-200 text-amber-600 flex items-center justify-center mx-auto mb-5 shadow-sm">
              <svg className="w-8 h-8" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M12 8v4l3 3m6-3a9 9 0 11-18 0 9 9 0 0118 0z" />
              </svg>
            </div>
            <h2 className="text-xl font-bold text-slate-900 mb-2">Account Created!</h2>
            <div className="p-4 rounded-2xl bg-amber-50/80 border border-amber-200/80 text-amber-900 text-xs leading-relaxed mb-6">
              <p className="font-semibold text-amber-950 mb-1">Your account is waiting for admin approval</p>
              <p>An administrator will review your account registration before you can log in and access documents.</p>
            </div>
            <button
              onClick={onNavigateToLogin}
              className="w-full py-3 px-4 rounded-xl font-semibold text-sm text-white bg-gradient-to-r from-indigo-600 to-violet-600 hover:from-indigo-500 hover:to-violet-500 shadow-md shadow-indigo-500/20 active:scale-98 transition-all cursor-pointer"
            >
              Return to Sign In
            </button>
          </div>
        </div>
      </div>
    );
  }

  return (
    <div className="min-h-screen w-full flex items-center justify-center bg-gradient-to-br from-indigo-50/70 via-slate-50 to-violet-50/60 relative overflow-hidden px-4 font-sans text-slate-800 py-10">
      {/* Background Ambience */}
      <div className="absolute top-1/4 -right-20 w-96 h-96 bg-indigo-200/40 rounded-full blur-3xl pointer-events-none" />
      <div className="absolute bottom-1/4 -left-20 w-96 h-96 bg-violet-200/40 rounded-full blur-3xl pointer-events-none" />

      <div className="w-full max-w-md relative z-10">
        {/* Brand Header */}
        <div className="text-center mb-8">
          <div className="inline-flex items-center justify-center w-14 h-14 rounded-2xl bg-gradient-to-tr from-indigo-600 to-violet-600 shadow-lg shadow-indigo-500/20 mb-4 border border-indigo-200/50">
            <svg className="w-7 h-7 text-white" fill="none" viewBox="0 0 24 24" stroke="currentColor">
              <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M18 9v3m0 0v3m0-3h3m-3 0h-3m-2-5a4 4 0 11-8 0 4 4 0 018 0zM3 20a6 6 0 0112 0v1H3v-1z" />
            </svg>
          </div>
          <h1 className="text-2xl font-bold tracking-tight text-slate-900">Create Your Account</h1>
          <p className="text-sm text-slate-500 mt-1.5">Get your own private workspace for files and chats</p>
        </div>

        {/* Signup Card */}
        <div className="bg-white/90 backdrop-blur-xl border border-slate-200/80 rounded-3xl p-8 shadow-xl shadow-slate-200/50">
          {error && (
            <div className="mb-6 p-4 rounded-xl bg-red-50 border border-red-200 flex items-start gap-3 text-red-700 text-sm animate-in fade-in slide-in-from-top-1">
              <svg className="w-5 h-5 text-red-500 shrink-0 mt-0.5" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M12 8v4m0 4h.01M21 12a9 9 0 11-18 0 9 9 0 0118 0z" />
              </svg>
              <span>{error}</span>
            </div>
          )}

          <form onSubmit={handleSubmit} noValidate className="space-y-4">
            <div>
              <label className="block text-xs font-semibold uppercase tracking-wider text-slate-600 mb-2">
                Full Name
              </label>
              <div className="relative">
                <div className={`absolute inset-y-0 left-0 pl-3.5 flex items-center pointer-events-none transition-colors ${nameError ? 'text-red-500' : 'text-slate-400'}`}>
                  <svg className="w-4 h-4" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                    <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M16 7a4 4 0 11-8 0 4 4 0 018 0zM12 14a7 7 0 00-7 7h14a7 7 0 00-7-7z" />
                  </svg>
                </div>
                <input
                  type="text"
                  value={name}
                  onChange={(e) => {
                    setName(e.target.value);
                    if (nameError) setNameError(validateName(e.target.value));
                    if (error) setError('');
                  }}
                  onBlur={() => setNameError(validateName(name))}
                  placeholder="Jane Doe"
                  className={`w-full pl-10 pr-4 py-3 rounded-xl text-sm transition-all shadow-sm focus:outline-none ${
                    nameError
                      ? 'bg-red-50/30 border-2 border-red-500 text-red-900 placeholder-red-300 ring-2 ring-red-500/20 focus:ring-red-500 focus:border-red-500'
                      : 'bg-slate-50/80 border border-slate-200 text-slate-900 placeholder-slate-400 focus:bg-white focus:ring-2 focus:ring-indigo-500 focus:border-transparent'
                  }`}
                />
              </div>
              {nameError && (
                <p className="mt-1.5 text-xs text-red-600 flex items-center gap-1 font-medium animate-in fade-in">
                  <svg className="w-3.5 h-3.5 shrink-0" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                    <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M12 8v4m0 4h.01M21 12a9 9 0 11-18 0 9 9 0 0118 0z" />
                  </svg>
                  <span>{nameError}</span>
                </p>
              )}
            </div>

            <div>
              <label className="block text-xs font-semibold uppercase tracking-wider text-slate-600 mb-2">
                Email Address
              </label>
              <div className="relative">
                <div className={`absolute inset-y-0 left-0 pl-3.5 flex items-center pointer-events-none transition-colors ${emailError ? 'text-red-500' : 'text-slate-400'}`}>
                  <svg className="w-4 h-4" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                    <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M16 12a4 4 0 10-8 0 4 4 0 008 0zm0 0v1.5a2.5 2.5 0 005 0V12a9 9 0 10-9 9m4.5-1.206a8.959 8.959 0 01-4.5 1.207" />
                  </svg>
                </div>
                <input
                  type="email"
                  value={email}
                  onChange={(e) => {
                    setEmail(e.target.value);
                    if (emailError) setEmailError(validateEmail(e.target.value));
                    if (error) setError('');
                  }}
                  onBlur={() => setEmailError(validateEmail(email))}
                  placeholder="name@example.com"
                  className={`w-full pl-10 pr-4 py-3 rounded-xl text-sm transition-all shadow-sm focus:outline-none ${
                    emailError
                      ? 'bg-red-50/30 border-2 border-red-500 text-red-900 placeholder-red-300 ring-2 ring-red-500/20 focus:ring-red-500 focus:border-red-500'
                      : 'bg-slate-50/80 border border-slate-200 text-slate-900 placeholder-slate-400 focus:bg-white focus:ring-2 focus:ring-indigo-500 focus:border-transparent'
                  }`}
                />
              </div>
              {emailError && (
                <p className="mt-1.5 text-xs text-red-600 flex items-center gap-1 font-medium animate-in fade-in">
                  <svg className="w-3.5 h-3.5 shrink-0" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                    <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M12 8v4m0 4h.01M21 12a9 9 0 11-18 0 9 9 0 0118 0z" />
                  </svg>
                  <span>{emailError}</span>
                </p>
              )}
            </div>

            <div>
              <label className="block text-xs font-semibold uppercase tracking-wider text-slate-600 mb-2">
                Password <span className="text-slate-400 font-normal lowercase">(minimum 8 characters)</span>
              </label>
              <div className="relative">
                <div className={`absolute inset-y-0 left-0 pl-3.5 flex items-center pointer-events-none transition-colors ${passwordError ? 'text-red-500' : 'text-slate-400'}`}>
                  <svg className="w-4 h-4" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                    <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M12 15v2m-6 4h12a2 2 0 002-2v-6a2 2 0 00-2-2H6a2 2 0 00-2 2v6a2 2 0 002 2zm10-10V7a4 4 0 00-8 0v4h8z" />
                  </svg>
                </div>
                <input
                  type={showPassword ? 'text' : 'password'}
                  value={password}
                  onChange={(e) => {
                    setPassword(e.target.value);
                    if (passwordError) setPasswordError(validatePassword(e.target.value));
                    if (confirmPasswordError && confirmPassword) {
                      setConfirmPasswordError(validateConfirmPassword(confirmPassword, e.target.value));
                    }
                    if (error) setError('');
                  }}
                  onBlur={() => setPasswordError(validatePassword(password))}
                  placeholder="••••••••"
                  className={`w-full pl-10 pr-11 py-3 rounded-xl text-sm transition-all shadow-sm focus:outline-none ${
                    passwordError
                      ? 'bg-red-50/30 border-2 border-red-500 text-red-900 placeholder-red-300 ring-2 ring-red-500/20 focus:ring-red-500 focus:border-red-500'
                      : 'bg-slate-50/80 border border-slate-200 text-slate-900 placeholder-slate-400 focus:bg-white focus:ring-2 focus:ring-indigo-500 focus:border-transparent'
                  }`}
                />
                <button
                  type="button"
                  onClick={() => setShowPassword(!showPassword)}
                  className="absolute inset-y-0 right-0 pr-3.5 flex items-center text-slate-400 hover:text-slate-600 focus:outline-none transition-colors cursor-pointer"
                  title={showPassword ? 'Hide password' : 'Show password'}
                  aria-label={showPassword ? 'Hide password' : 'Show password'}
                >
                  {showPassword ? (
                    <EyeOff className="w-4 h-4 text-slate-500 hover:text-slate-700" />
                  ) : (
                    <Eye className="w-4 h-4 text-slate-400 hover:text-slate-600" />
                  )}
                </button>
              </div>
              {passwordError && (
                <p className="mt-1.5 text-xs text-red-600 flex items-center gap-1 font-medium animate-in fade-in">
                  <svg className="w-3.5 h-3.5 shrink-0" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                    <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M12 8v4m0 4h.01M21 12a9 9 0 11-18 0 9 9 0 0118 0z" />
                  </svg>
                  <span>{passwordError}</span>
                </p>
              )}
            </div>

            <div>
              <label className="block text-xs font-semibold uppercase tracking-wider text-slate-600 mb-2">
                Confirm Password
              </label>
              <div className="relative">
                <div className={`absolute inset-y-0 left-0 pl-3.5 flex items-center pointer-events-none transition-colors ${confirmPasswordError ? 'text-red-500' : 'text-slate-400'}`}>
                  <svg className="w-4 h-4" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                    <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M9 12l2 2 4-4m6 2a9 9 0 11-18 0 9 9 0 0118 0z" />
                  </svg>
                </div>
                <input
                  type={showConfirmPassword ? 'text' : 'password'}
                  value={confirmPassword}
                  onChange={(e) => {
                    setConfirmPassword(e.target.value);
                    if (confirmPasswordError) setConfirmPasswordError(validateConfirmPassword(e.target.value, password));
                    if (error) setError('');
                  }}
                  onBlur={() => setConfirmPasswordError(validateConfirmPassword(confirmPassword, password))}
                  placeholder="••••••••"
                  className={`w-full pl-10 pr-11 py-3 rounded-xl text-sm transition-all shadow-sm focus:outline-none ${
                    confirmPasswordError
                      ? 'bg-red-50/30 border-2 border-red-500 text-red-900 placeholder-red-300 ring-2 ring-red-500/20 focus:ring-red-500 focus:border-red-500'
                      : 'bg-slate-50/80 border border-slate-200 text-slate-900 placeholder-slate-400 focus:bg-white focus:ring-2 focus:ring-indigo-500 focus:border-transparent'
                  }`}
                />
                <button
                  type="button"
                  onClick={() => setShowConfirmPassword(!showConfirmPassword)}
                  className="absolute inset-y-0 right-0 pr-3.5 flex items-center text-slate-400 hover:text-slate-600 focus:outline-none transition-colors cursor-pointer"
                  title={showConfirmPassword ? 'Hide password' : 'Show password'}
                  aria-label={showConfirmPassword ? 'Hide password' : 'Show password'}
                >
                  {showConfirmPassword ? (
                    <EyeOff className="w-4 h-4 text-slate-500 hover:text-slate-700" />
                  ) : (
                    <Eye className="w-4 h-4 text-slate-400 hover:text-slate-600" />
                  )}
                </button>
              </div>
              {confirmPasswordError && (
                <p className="mt-1.5 text-xs text-red-600 flex items-center gap-1 font-medium animate-in fade-in">
                  <svg className="w-3.5 h-3.5 shrink-0" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                    <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M12 8v4m0 4h.01M21 12a9 9 0 11-18 0 9 9 0 0118 0z" />
                  </svg>
                  <span>{confirmPasswordError}</span>
                </p>
              )}
            </div>

            <button
              type="submit"
              disabled={isSubmitting}
              className="w-full mt-3 py-3.5 px-4 bg-gradient-to-r from-indigo-600 via-indigo-500 to-violet-600 hover:from-indigo-700 hover:to-violet-700 text-white font-medium rounded-xl shadow-md shadow-indigo-600/25 flex items-center justify-center gap-2 transition-all duration-200 disabled:opacity-60 active:scale-[0.99] cursor-pointer"
            >
              {isSubmitting ? (
                <>
                  <svg className="animate-spin w-4 h-4 text-white" fill="none" viewBox="0 0 24 24">
                    <circle className="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" strokeWidth="4" />
                    <path className="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8v8H4z" />
                  </svg>
                  <span>Creating Account...</span>
                </>
              ) : (
                <span>Create Account</span>
              )}
            </button>
          </form>

          {/* Switch to Login */}
          <div className="mt-6 pt-6 border-t border-slate-100 text-center">
            <p className="text-sm text-slate-600">
              Already have an account?{' '}
              <button
                type="button"
                onClick={onNavigateToLogin}
                className="text-indigo-600 hover:text-indigo-700 font-semibold transition-colors cursor-pointer"
              >
                Sign in
              </button>
            </p>
          </div>
        </div>
      </div>
    </div>
  );
}
