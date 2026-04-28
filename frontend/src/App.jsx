import React, { useState, useEffect } from 'react';
import { Wallet, ArrowUpRight, Activity, Clock, CheckCircle, XCircle } from 'lucide-react';

const API_BASE = 'http://localhost:8000/api/v1';
// In a real app, merchant_id would come from auth. Using Globex Inc from seed.
const MERCHANT_ID = '00000000-0000-0000-0000-000000000000'; // We need the actual UUID, but since seeding is dynamic, let's make it selectable or fetch the first one.

function App() {
  const [merchants, setMerchants] = useState([]);
  const [activeMerchant, setActiveMerchant] = useState(null);
  const [dashboardData, setDashboardData] = useState(null);
  const [amount, setAmount] = useState('');
  const [bankAccount, setBankAccount] = useState('');
  const [submitting, setSubmitting] = useState(false);
  const [error, setError] = useState(null);

  // We need to fetch a merchant ID first to display it, since our seed dynamically generated them.
  // For simplicity, we'll fetch all merchants and pick the first one? Wait, we don't have a GET /merchants route.
  // Let's assume the user supplies the merchant ID or it's hardcoded to the first UUID in db.
  // Actually, I didn't write an endpoint for all merchants. Let's add that to backend or just simulate it.

  useEffect(() => {
    // Polling dashboard
    if (!activeMerchant) return;
    
    const fetchDashboard = async () => {
      try {
        const res = await fetch(`${API_BASE}/merchants/${activeMerchant}/dashboard`);
        if (res.ok) {
          const data = await res.json();
          setDashboardData(data);
        }
      } catch (err) {
        console.error("Dashboard fetch error:", err);
      }
    };

    fetchDashboard();
    const interval = setInterval(fetchDashboard, 3000);
    return () => clearInterval(interval);
  }, [activeMerchant]);

  const handlePayout = async (e) => {
    e.preventDefault();
    setError(null);
    setSubmitting(true);
    
    const amountPaise = parseFloat(amount) * 100;
    const idempotencyKey = crypto.randomUUID();

    try {
      const res = await fetch(`${API_BASE}/merchants/${activeMerchant}/payouts`, {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
          'Idempotency-Key': idempotencyKey,
        },
        body: JSON.stringify({
          amount_paise: amountPaise,
          bank_account_id: bankAccount
        })
      });

      const data = await res.json();
      if (!res.ok) {
        throw new Error(data.error || 'Failed to request payout');
      }
      
      setAmount('');
      setBankAccount('');
    } catch (err) {
      setError(err.message);
    } finally {
      setSubmitting(false);
    }
  };

  const handleSettle = async (payoutId) => {
    try {
      const res = await fetch(`${API_BASE}/payouts/${payoutId}/settle`, { method: 'POST' });
      if (!res.ok) {
        console.error("Failed to settle payout");
      }
    } catch (err) {
      console.error(err);
    }
  };

  const getStatusIcon = (state) => {
    switch (state) {
      case 'COMPLETED': return <CheckCircle className="w-5 h-5 text-emerald-400" />;
      case 'FAILED': return <XCircle className="w-5 h-5 text-rose-400" />;
      case 'PROCESSING': return <Activity className="w-5 h-5 text-sky-400 animate-pulse" />;
      default: return <Clock className="w-5 h-5 text-yellow-400" />;
    }
  };

  // We add a mock way to set active merchant for the test if it's missing.
  if (!activeMerchant) {
    return (
      <div className="min-h-screen flex items-center justify-center bg-[radial-gradient(ellipse_at_top_right,_var(--tw-gradient-stops))] from-slate-900 via-[#0a0f1c] to-black text-white relative overflow-hidden">
        <div className="absolute top-1/4 left-1/4 w-96 h-96 bg-purple-500/20 rounded-full blur-[120px]"></div>
        <div className="absolute bottom-1/4 right-1/4 w-96 h-96 bg-blue-500/20 rounded-full blur-[120px]"></div>
        
        <div className="z-10 bg-white/5 backdrop-blur-xl border border-white/10 p-8 rounded-2xl w-full max-w-md shadow-2xl">
          <h2 className="text-2xl font-semibold mb-6 flex items-center gap-3">
             Select Merchant Simulation
          </h2>
          <p className="text-gray-400 text-sm mb-6">Enter a valid UUID from your Seed script to continue.</p>
          <input 
            type="text" 
            placeholder="Merchant UUID..." 
            className="w-full bg-black/50 border border-white/10 rounded-xl px-4 py-3 mb-4 focus:ring-2 focus:ring-blue-500 outline-none transition-all placeholder:text-gray-600"
            onKeyDown={(e) => {
              if (e.key === 'Enter') setActiveMerchant(e.target.value);
            }}
          />
        </div>
      </div>
    );
  }

  if (!dashboardData) return null;

  return (
    <div className="min-h-screen bg-[radial-gradient(ellipse_at_top_left,_var(--tw-gradient-stops))] from-gray-900 via-[#050b14] to-black text-white font-sans p-6 md:p-12 relative overflow-hidden">
      
      {/* Background decorations */}
      <div className="absolute top-[-10%] left-[-10%] w-[40%] h-[40%] bg-indigo-600/10 rounded-full blur-[120px] pointer-events-none"></div>
      <div className="absolute bottom-[-10%] right-[-10%] w-[40%] h-[40%] bg-blue-600/10 rounded-full blur-[120px] pointer-events-none"></div>

      <div className="max-w-6xl mx-auto relative z-10 space-y-8">
        
        {/* Header */}
        <header className="flex justify-between items-end pb-6 border-b border-white/10">
          <div>
            <h1 className="text-4xl md:text-5xl font-bold bg-gradient-to-r from-blue-400 via-indigo-300 to-purple-400 bg-clip-text text-transparent mb-2 tracking-tight">
              Playto Engine
            </h1>
            <p className="text-gray-400 font-medium">Merchant: {dashboardData.name}</p>
          </div>
          <div className="flex items-center gap-4">
            <button 
              onClick={() => {
                setActiveMerchant(null);
                setDashboardData(null);
              }}
              className="text-sm text-gray-400 hover:text-white bg-white/5 hover:bg-white/10 px-4 py-2 rounded-full border border-white/5 transition-all"
            >
              Change Merchant
            </button>
            <div className="hidden md:flex items-center gap-2 bg-white/5 px-4 py-2 rounded-full border border-white/5">
              <div className="w-2 h-2 rounded-full bg-emerald-400 animate-pulse"></div>
              <span className="text-sm font-medium text-emerald-400">Live API</span>
            </div>
          </div>
        </header>

        <div className="grid grid-cols-1 md:grid-cols-3 gap-6">
          
          {/* Main Balances */}
          <div className="md:col-span-2 space-y-6">
            <div className="grid grid-cols-1 sm:grid-cols-2 gap-6">
              {/* Available Balance Card */}
              <div className="bg-gradient-to-br from-white/10 to-white/5 backdrop-blur-md rounded-3xl p-8 border border-white/10 shadow-xl group hover:border-white/20 transition-all duration-300">
                <div className="flex items-center gap-3 text-gray-400 mb-4">
                  <Wallet className="w-5 h-5 text-emerald-400" />
                  <span className="font-semibold uppercase tracking-wider text-xs">Available Balance</span>
                </div>
                <div className="text-5xl font-bold text-white tracking-tight group-hover:scale-[1.02] transition-transform origin-left">
                  ₹{(dashboardData.available_balance / 100).toLocaleString('en-IN', { minimumFractionDigits: 2 })}
                </div>
              </div>

              {/* Held Balance Card */}
              <div className="bg-white/5 backdrop-blur-md rounded-3xl p-8 border border-white/10 shadow-lg">
                <div className="flex items-center gap-3 text-gray-400 mb-4">
                  <Clock className="w-5 h-5 text-yellow-500" />
                  <span className="font-semibold uppercase tracking-wider text-xs">Held / Processing</span>
                </div>
                <div className="text-4xl font-semibold text-gray-300">
                  ₹{Math.abs(dashboardData.held_balance / 100).toLocaleString('en-IN', { minimumFractionDigits: 2 })}
                </div>
              </div>
            </div>

            {/* Payout History Table */}
            <div className="bg-white/5 backdrop-blur-md rounded-3xl border border-white/10 flex flex-col overflow-hidden shadow-2xl">
              <div className="p-6 border-b border-white/10 bg-white/[0.02]">
                <h3 className="text-xl font-semibold">Recent Payouts</h3>
              </div>
              <div className="overflow-x-auto">
                <table className="w-full text-left border-collapse">
                  <thead>
                    <tr className="text-gray-400 text-sm border-b border-white/5">
                      <th className="px-6 py-4 font-medium">Counterparty</th>
                      <th className="px-6 py-4 font-medium text-right">Amount</th>
                      <th className="px-6 py-4 font-medium text-center">Status</th>
                      <th className="px-6 py-4 font-medium text-right">Time</th>
                    </tr>
                  </thead>
                  <tbody className="divide-y divide-white/5">
                    {dashboardData.payouts && dashboardData.payouts.map(p => (
                      <tr key={p.id} className="hover:bg-white/5 transition-colors group">
                        <td className="px-6 py-4 text-gray-300 font-mono text-sm">{p.bank_account_id === activeMerchant ? p.merchant : p.bank_account_id}</td>
                        <td className="px-6 py-4 text-right font-semibold">₹{(p.amount_paise / 100).toLocaleString('en-IN')}</td>
                        <td className="px-6 py-4 flex justify-center">
                          <div className="flex items-center gap-2">
                            {getStatusIcon(p.state)}
                            <span className="text-xs font-semibold tracking-wider text-gray-400">{p.state}</span>
                            {(p.state === 'PENDING' || p.state === 'PROCESSING') && p.bank_account_id === activeMerchant && (
                              <button 
                                onClick={() => handleSettle(p.id)}
                                className="ml-2 text-[10px] bg-blue-500/20 hover:bg-blue-500/40 text-blue-300 px-2 py-1 rounded transition-colors"
                              >
                                SETTLE
                              </button>
                            )}
                          </div>
                        </td>
                        <td className="px-6 py-4 text-right text-gray-500 text-sm">
                          {new Date(p.created_at).toLocaleTimeString([], {hour: '2-digit', minute:'2-digit'})}
                        </td>
                      </tr>
                    ))}
                    {(!dashboardData.payouts || dashboardData.payouts.length === 0) && (
                      <tr>
                        <td colSpan="4" className="text-center py-12 text-gray-500">No payouts yet.</td>
                      </tr>
                    )}
                  </tbody>
                </table>
              </div>
            </div>

            {/* Recent Transactions Table */}
            <div className="bg-white/5 backdrop-blur-md rounded-3xl border border-white/10 flex flex-col overflow-hidden shadow-2xl">
              <div className="p-6 border-b border-white/10 bg-white/[0.02]">
                <h3 className="text-xl font-semibold">Ledger Transactions</h3>
              </div>
              <div className="overflow-x-auto">
                <table className="w-full text-left border-collapse">
                  <thead>
                    <tr className="text-gray-400 text-sm border-b border-white/5">
                      <th className="px-6 py-4 font-medium">Type</th>
                      <th className="px-6 py-4 font-medium text-right">Amount</th>
                      <th className="px-6 py-4 font-medium text-right">Time</th>
                    </tr>
                  </thead>
                  <tbody className="divide-y divide-white/5">
                    {dashboardData.recent_transactions && dashboardData.recent_transactions.map(t => (
                      <tr key={t.id} className="hover:bg-white/5 transition-colors group">
                        <td className="px-6 py-4 font-semibold text-sm">
                          <span className={
                            t.txn_type === 'CREDIT' ? 'text-emerald-400' : 
                            t.txn_type === 'PAYOUT_HOLD' ? 'text-yellow-400' : 'text-sky-400'
                          }>
                            {t.txn_type.replace('_', ' ')}
                          </span>
                        </td>
                        <td className={`px-6 py-4 text-right font-semibold ${t.amount_paise > 0 ? 'text-emerald-400' : 'text-gray-300'}`}>
                          {t.amount_paise > 0 ? '+' : ''}₹{(t.amount_paise / 100).toLocaleString('en-IN')}
                        </td>
                        <td className="px-6 py-4 text-right text-gray-500 text-sm">
                          {new Date(t.created_at).toLocaleTimeString([], {hour: '2-digit', minute:'2-digit'})}
                        </td>
                      </tr>
                    ))}
                    {(!dashboardData.recent_transactions || dashboardData.recent_transactions.length === 0) && (
                      <tr>
                        <td colSpan="3" className="text-center py-12 text-gray-500">No ledger activity yet.</td>
                      </tr>
                    )}
                  </tbody>
                </table>
              </div>
            </div>
          </div>

          {/* Sidebar / Actions */}
          <div className="space-y-6">
            <div className="bg-gradient-to-b from-blue-900/40 to-black/40 backdrop-blur-xl rounded-3xl p-6 border border-blue-500/20 shadow-[0_0_40px_-15px_rgba(59,130,246,0.3)] relative overflow-hidden">
              <div className="absolute top-0 right-0 p-3 opacity-20 pointer-events-none">
                <ArrowUpRight className="w-24 h-24 text-blue-400" />
              </div>
              <h3 className="text-xl font-semibold mb-6 relative z-10 text-blue-100">Request Payout</h3>
              
              {error && (
                <div className="mb-4 text-sm bg-rose-500/20 text-rose-300 border border-rose-500/30 p-3 rounded-lg">
                  {error}
                </div>
              )}

              <form onSubmit={handlePayout} className="space-y-5 relative z-10">
                <div>
                  <label className="block text-sm text-blue-200/70 mb-2">Amount (₹)</label>
                  <input 
                    type="number" 
                    required 
                    min="1"
                    step="0.01"
                    value={amount}
                    onChange={(e) => setAmount(e.target.value)}
                    className="w-full bg-black/40 border border-blue-500/30 rounded-xl px-4 py-3 focus:ring-2 focus:ring-blue-400 focus:border-transparent outline-none transition-all placeholder:text-blue-900/50"
                    placeholder="500.00"
                  />
                </div>
                <div>
                  <label className="block text-sm text-blue-200/70 mb-2">Bank Account</label>
                  <input 
                    type="text" 
                    required 
                    value={bankAccount}
                    onChange={(e) => setBankAccount(e.target.value)}
                    className="w-full bg-black/40 border border-blue-500/30 rounded-xl px-4 py-3 focus:ring-2 focus:ring-blue-400 focus:border-transparent outline-none transition-all placeholder:text-blue-900/50"
                    placeholder="HDFC_0101XXXXX"
                  />
                </div>
                <button 
                  type="submit" 
                  disabled={submitting || !amount || !bankAccount}
                  className="w-full bg-blue-500 hover:bg-blue-400 text-white font-semibold py-3 px-6 rounded-xl transition-all shadow-[0_0_20px_-5px_rgba(59,130,246,0.4)] hover:shadow-[0_0_30px_-5px_rgba(59,130,246,0.6)] disabled:opacity-50 disabled:cursor-not-allowed group active:scale-95"
                >
                  <span className="flex items-center justify-center gap-2">
                    {submitting ? 'Processing...' : 'Submit Payout'}
                    {!submitting && <ArrowUpRight className="w-5 h-5 group-hover:translate-x-1 transition-transform" />}
                  </span>
                </button>
              </form>
            </div>
          </div>
          
        </div>
      </div>
    </div>
  );
}

export default App;
