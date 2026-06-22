import React, { useState } from 'react';

interface LoginProps {
  onLogin: (email: string, password: string) => Promise<{ error: any }>;
  onRegister: (email: string, password: string) => Promise<{ error: any }>;
}

const Login: React.FC<LoginProps> = ({ onLogin, onRegister }) => {
  const [email, setEmail] = useState('');
  const [password, setPassword] = useState('');
  const [error, setError] = useState('');
  const [success, setSuccess] = useState('');
  const [loading, setLoading] = useState(false);
  const [mode, setMode] = useState<'login' | 'register'>('login');

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    setLoading(true);
    setError('');
    setSuccess('');
    if (mode === 'login') {
      const result = await onLogin(email, password);
      if (result.error) setError(result.error.message || 'Login fehlgeschlagen');
    } else {
      const result = await onRegister(email, password);
      if (result.error) {
        setError(result.error.message || 'Registrierung fehlgeschlagen');
      } else {
        setSuccess('Konto erstellt! Bitte E-Mail bestätigen, dann anmelden.');
        setMode('login');
      }
    }
    setLoading(false);
  };

  return (
    <div className="min-h-screen flex items-center justify-center bg-gradient-to-br from-blue-600 to-purple-700">
      <div className="bg-white p-8 rounded-2xl shadow-2xl w-full max-w-md">
        <div className="text-center mb-8">
          <div style={{width:64,height:64,background:'linear-gradient(135deg,#10b981,#059669)',borderRadius:'50%',display:'flex',alignItems:'center',justifyContent:'center',margin:'0 auto 16px'}}>
            <span style={{fontSize:28}}>🛡️</span>
          </div>
          <h1 className="text-3xl font-bold text-gray-800 mb-2">Admin Dashboard</h1>
          <p className="text-gray-600">
            {mode === 'login' ? 'Melde dich an, um auf das Dashboard zuzugreifen.' : 'Erstelle dein Konto.'}
          </p>
        </div>

        <form onSubmit={handleSubmit} className="space-y-6">
          <div>
            <label className="block text-sm font-medium text-gray-700 mb-2">E-Mail</label>
            <input type="email" value={email} onChange={(e) => setEmail(e.target.value)} required
              className="w-full px-4 py-3 border border-gray-300 rounded-lg focus:ring-2 focus:ring-green-500"
              placeholder="email@example.com" />
          </div>
          <div>
            <label className="block text-sm font-medium text-gray-700 mb-2">Passwort</label>
            <input type="password" value={password} onChange={(e) => setPassword(e.target.value)} required
              className="w-full px-4 py-3 border border-gray-300 rounded-lg focus:ring-2 focus:ring-green-500"
              placeholder="••••••••" minLength={6} />
          </div>
          {error && <div className="text-red-500 text-sm text-center bg-red-50 p-3 rounded-lg">{error}</div>}
          {success && <div className="text-green-600 text-sm text-center bg-green-50 p-3 rounded-lg">{success}</div>}
          <button type="submit" disabled={loading}
            style={{background:'linear-gradient(135deg,#10b981,#059669)'}}
            className="w-full text-white py-3 rounded-lg font-semibold hover:opacity-90 transition-opacity disabled:opacity-50">
            {loading ? 'Bitte warten...' : mode === 'login' ? 'Anmelden' : 'Konto erstellen'}
          </button>
        </form>

        <div className="mt-6 text-center text-sm text-gray-500">
          {mode === 'login' ? (
            <p>Noch kein Konto?{' '}
              <button onClick={() => { setMode('register'); setError(''); setSuccess(''); }}
                className="text-green-600 font-semibold hover:underline">Registrieren</button>
            </p>
          ) : (
            <p>Bereits registriert?{' '}
              <button onClick={() => { setMode('login'); setError(''); setSuccess(''); }}
                className="text-green-600 font-semibold hover:underline">Anmelden</button>
            </p>
          )}
        </div>
      </div>
    </div>
  );
};

export default Login;
