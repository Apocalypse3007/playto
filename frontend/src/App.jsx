import React, { useState, useEffect } from 'react';
import { Wallet, Activity, Clock, CheckCircle2, XCircle, ArrowRight, CornerDownRight, Check, Loader2 } from 'lucide-react';
import { Routes, Route, useNavigate, useParams } from 'react-router-dom';

const API_BASE = 'http://localhost:8000/api/v1';

function Dashboard() {
  const { merchantId: activeMerchant } = useParams();
  const navigate = useNavigate();
  const [dashboardData, setDashboardData] = useState(null);
  const [amount, setAmount] = useState('');
  const [bankAccount, setBankAccount] = useState('');
  const [submitting, setSubmitting] = useState(false);
  const [error, setError] = useState(null);

  useEffect(() => {
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

  const getStatusBadge = (state) => {
    switch (state) {
      case 'COMPLETED': 
        return (
          <span className="inline-flex items-center gap-1.5 px-2 py-0.5 rounded-full text-xs font-medium bg-emerald-500/10 text-emerald-500 border border-emerald-500/20">
            <CheckCircle2 className="w-3 h-3" /> Completed
          </span>
        );
      case 'FAILED': 
        return (
          <span className="inline-flex items-center gap-1.5 px-2 py-0.5 rounded-full text-xs font-medium bg-red-500/10 text-red-500 border border-red-500/20">
            <XCircle className="w-3 h-3" /> Failed
          </span>
        );
      case 'PROCESSING': 
        return (
          <span className="inline-flex items-center gap-1.5 px-2 py-0.5 rounded-full text-xs font-medium bg-amber-500/10 text-amber-500 border border-amber-500/20">
            <Loader2 className="w-3 h-3 animate-spin" /> Processing
          </span>
        );
      default: 
        return (
          <span className="inline-flex items-center gap-1.5 px-2 py-0.5 rounded-full text-xs font-medium bg-neutral-500/10 text-neutral-400 border border-neutral-500/20">
            <Clock className="w-3 h-3" /> {state}
          </span>
        );
    }
  };

  if (!dashboardData) return null;

  return (
    <div className="min-h-screen bg-black text-neutral-200 font-sans selection:bg-neutral-800 selection:text-white">
      {/* Header Navigation */}
      <header className="sticky top-0 z-50 bg-black/80 backdrop-blur-md border-b border-neutral-800">
        <div className="max-w-6xl mx-auto px-6 h-16 flex items-center justify-between">
          <div className="flex items-center gap-6">
            <div className="flex items-center gap-2">
              <span className="text-white font-semibold tracking-tight">Playto</span>
            </div>
            <div className="h-4 w-px bg-neutral-800"></div>
            <div className="flex items-center gap-2 text-sm text-neutral-400">
              <span className="hover:text-white transition-colors cursor-pointer">{dashboardData.name}</span>
              <span className="bg-neutral-900 border border-neutral-800 text-neutral-300 text-[10px] font-mono px-1.5 py-0.5 rounded">Pro</span>
            </div>
          </div>
          
          <div className="flex items-center gap-4">
            <button 
              onClick={() => navigate('/')}
              className="text-sm text-neutral-400 hover:text-white transition-colors"
            >
              Change Merchant
            </button>
            <div className="flex items-center gap-2 text-sm text-neutral-400 border border-neutral-800 rounded-full px-3 py-1">
              <div className="w-2 h-2 rounded-full bg-emerald-500 relative">
                <div className="absolute inset-0 rounded-full bg-emerald-500 animate-ping opacity-75"></div>
              </div>
              Live
            </div>
          </div>
        </div>
      </header>

      <main className="max-w-6xl mx-auto px-6 py-12 space-y-12">
        {/* Page Title */}
        <div>
          <h1 className="text-3xl font-semibold text-white tracking-tight mb-2">Dashboard</h1>
          <p className="text-neutral-400 text-sm">Manage your payouts and monitor recent transactions.</p>
        </div>

        <div className="grid grid-cols-1 lg:grid-cols-3 gap-8">
          
          {/* Main Content Area */}
          <div className="lg:col-span-2 space-y-8">
            
            {/* Balances */}
            <div className="grid grid-cols-1 sm:grid-cols-2 gap-4">
              <div className="bg-[#0a0a0a] border border-neutral-800 rounded-xl p-6 hover:border-neutral-700 transition-colors">
                <div className="flex justify-between items-start mb-6">
                  <h3 className="text-sm font-medium text-neutral-400">Available Balance</h3>
                  <Wallet className="w-4 h-4 text-neutral-500" />
                </div>
                <div className="flex items-baseline gap-1">
                  <span className="text-neutral-500">₹</span>
                  <span className="text-3xl font-semibold text-white tracking-tight">
                    {(dashboardData.available_balance / 100).toLocaleString('en-IN', { minimumFractionDigits: 2 })}
                  </span>
                </div>
              </div>

              <div className="bg-[#0a0a0a] border border-neutral-800 rounded-xl p-6 hover:border-neutral-700 transition-colors">
                <div className="flex justify-between items-start mb-6">
                  <h3 className="text-sm font-medium text-neutral-400">Held for Processing</h3>
                  <Clock className="w-4 h-4 text-neutral-500" />
                </div>
                <div className="flex items-baseline gap-1">
                  <span className="text-neutral-500">₹</span>
                  <span className="text-3xl font-semibold text-white tracking-tight">
                    {Math.abs(dashboardData.held_balance / 100).toLocaleString('en-IN', { minimumFractionDigits: 2 })}
                  </span>
                </div>
              </div>
            </div>

            {/* Payouts Table */}
            <div className="bg-black border border-neutral-800 rounded-xl overflow-hidden">
              <div className="px-6 py-4 border-b border-neutral-800 flex justify-between items-center">
                <h3 className="font-medium text-white">Recent Payouts</h3>
              </div>
              <div className="overflow-x-auto">
                <table className="w-full text-sm text-left">
                  <thead className="text-xs text-neutral-400 bg-[#0a0a0a] border-b border-neutral-800">
                    <tr>
                      <th className="px-6 py-3 font-medium">Destination</th>
                      <th className="px-6 py-3 font-medium text-right">Amount</th>
                      <th className="px-6 py-3 font-medium">Status</th>
                      <th className="px-6 py-3 font-medium text-right">Created</th>
                    </tr>
                  </thead>
                  <tbody className="divide-y divide-neutral-800">
                    {dashboardData.payouts && dashboardData.payouts.map(p => (
                      <tr key={p.id} className="hover:bg-neutral-900/50 transition-colors group">
                        <td className="px-6 py-4 whitespace-nowrap text-neutral-300 font-mono text-xs">
                          {p.bank_account_id === activeMerchant ? p.merchant : p.bank_account_id}
                        </td>
                        <td className="px-6 py-4 whitespace-nowrap text-right text-white font-medium">
                          ₹{(p.amount_paise / 100).toLocaleString('en-IN')}
                        </td>
                        <td className="px-6 py-4 whitespace-nowrap">
                          <div className="flex items-center gap-3">
                            {getStatusBadge(p.state)}
                            {(p.state === 'PENDING' || p.state === 'PROCESSING') && p.bank_account_id === activeMerchant && (
                              <button 
                                onClick={() => handleSettle(p.id)}
                                className="opacity-0 group-hover:opacity-100 transition-opacity flex items-center gap-1 text-[10px] bg-neutral-800 hover:bg-neutral-700 text-white px-2 py-1 rounded"
                              >
                                Settle <ArrowRight className="w-3 h-3" />
                              </button>
                            )}
                          </div>
                        </td>
                        <td className="px-6 py-4 whitespace-nowrap text-right text-neutral-500">
                          {new Date(p.created_at).toLocaleDateString(undefined, {month: 'short', day: 'numeric', hour: '2-digit', minute:'2-digit'})}
                        </td>
                      </tr>
                    ))}
                    {(!dashboardData.payouts || dashboardData.payouts.length === 0) && (
                      <tr>
                        <td colSpan="4" className="text-center py-8 text-neutral-500">No payouts yet.</td>
                      </tr>
                    )}
                  </tbody>
                </table>
              </div>
            </div>

            {/* Ledger Transactions */}
            <div className="bg-black border border-neutral-800 rounded-xl overflow-hidden">
              <div className="px-6 py-4 border-b border-neutral-800">
                <h3 className="font-medium text-white">Ledger Activity</h3>
              </div>
              <div className="overflow-x-auto">
                <table className="w-full text-sm text-left">
                  <thead className="text-xs text-neutral-400 bg-[#0a0a0a] border-b border-neutral-800">
                    <tr>
                      <th className="px-6 py-3 font-medium">Type</th>
                      <th className="px-6 py-3 font-medium text-right">Amount</th>
                      <th className="px-6 py-3 font-medium text-right">Date</th>
                    </tr>
                  </thead>
                  <tbody className="divide-y divide-neutral-800">
                    {dashboardData.recent_transactions && dashboardData.recent_transactions.map(t => (
                      <tr key={t.id} className="hover:bg-neutral-900/50 transition-colors">
                        <td className="px-6 py-4 whitespace-nowrap">
                          <span className="text-xs font-mono text-neutral-300">
                            {t.txn_type}
                          </span>
                        </td>
                        <td className={`px-6 py-4 whitespace-nowrap text-right font-medium ${t.amount_paise > 0 ? 'text-emerald-500' : 'text-neutral-300'}`}>
                          {t.amount_paise > 0 ? '+' : ''}₹{(t.amount_paise / 100).toLocaleString('en-IN')}
                        </td>
                        <td className="px-6 py-4 whitespace-nowrap text-right text-neutral-500">
                          {new Date(t.created_at).toLocaleDateString(undefined, {month: 'short', day: 'numeric', hour: '2-digit', minute:'2-digit'})}
                        </td>
                      </tr>
                    ))}
                    {(!dashboardData.recent_transactions || dashboardData.recent_transactions.length === 0) && (
                      <tr>
                        <td colSpan="3" className="text-center py-8 text-neutral-500">No ledger activity yet.</td>
                      </tr>
                    )}
                  </tbody>
                </table>
              </div>
            </div>
          </div>

          {/* Sidebar */}
          <div className="space-y-6">
            <div className="bg-[#0a0a0a] border border-neutral-800 rounded-xl p-6 sticky top-24">
              <h3 className="font-medium text-white mb-6 flex items-center gap-2">
                <CornerDownRight className="w-4 h-4 text-neutral-500" />
                Initiate Payout
              </h3>
              
              {error && (
                <div className="mb-6 text-sm bg-red-500/10 text-red-500 border border-red-500/20 p-3 rounded-md flex items-start gap-2">
                  <XCircle className="w-4 h-4 mt-0.5 shrink-0" />
                  <span>{error}</span>
                </div>
              )}

              <form onSubmit={handlePayout} className="space-y-4">
                <div>
                  <label className="block text-xs font-medium text-neutral-400 mb-1.5">Amount (₹)</label>
                  <input 
                    type="number" 
                    required 
                    min="1"
                    step="0.01"
                    value={amount}
                    onChange={(e) => setAmount(e.target.value)}
                    className="w-full bg-black border border-neutral-800 rounded-md px-3 py-2 text-sm text-white placeholder-neutral-600 focus:outline-none focus:ring-1 focus:ring-white focus:border-white transition-all"
                    placeholder="0.00"
                  />
                </div>
                <div>
                  <label className="block text-xs font-medium text-neutral-400 mb-1.5">Destination Bank Account</label>
                  <input 
                    type="text" 
                    required 
                    value={bankAccount}
                    onChange={(e) => setBankAccount(e.target.value)}
                    className="w-full bg-black border border-neutral-800 rounded-md px-3 py-2 text-sm text-white placeholder-neutral-600 focus:outline-none focus:ring-1 focus:ring-white focus:border-white transition-all font-mono"
                    placeholder="HDFC_..."
                  />
                </div>
                <div className="pt-2">
                  <button 
                    type="submit" 
                    disabled={submitting || !amount || !bankAccount}
                    className="w-full bg-white hover:bg-neutral-200 text-black font-medium py-2 px-4 rounded-md text-sm transition-colors disabled:opacity-50 disabled:hover:bg-white disabled:cursor-not-allowed flex items-center justify-center gap-2"
                  >
                    {submitting ? (
                      <Loader2 className="w-4 h-4 animate-spin" />
                    ) : (
                      'Send Payout'
                    )}
                  </button>
                </div>
              </form>
            </div>
          </div>
          
        </div>
      </main>
    </div>
  );
}

function SelectMerchant() {
  const navigate = useNavigate();
  const [newCorpName, setNewCorpName] = useState('');
  const [isCreating, setIsCreating] = useState(false);
  const [createError, setCreateError] = useState(null);

  const handleCreateMerchant = async (e) => {
    e.preventDefault();
    if (!newCorpName.trim()) return;
    
    setIsCreating(true);
    setCreateError(null);
    try {
      const res = await fetch(`${API_BASE}/merchants`, {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
        },
        body: JSON.stringify({ name: newCorpName.trim() })
      });
      const data = await res.json();
      if (!res.ok) {
        throw new Error(data.error || 'Failed to create merchant');
      }
      navigate(`/${data.id}`);
    } catch (err) {
      setCreateError(err.message);
    } finally {
      setIsCreating(false);
    }
  };

  return (
    <div className="min-h-screen flex items-center justify-center bg-black text-white font-sans selection:bg-neutral-800 selection:text-white">
      <div className="w-full max-w-sm px-6">
        <div className="text-center mb-8">
          <h2 className="text-xl font-semibold tracking-tight text-white mb-2">
            Select Merchant
          </h2>
          <p className="text-neutral-400 text-sm">
            Enter a valid simulation UUID to view dashboard.
          </p>
        </div>

        <div className="bg-[#0a0a0a] border border-neutral-800 rounded-xl p-4 shadow-xl mb-6">
          <input 
            type="text" 
            placeholder="Merchant UUID..." 
            className="w-full bg-black border border-neutral-800 rounded-md px-3 py-2 text-sm text-white placeholder-neutral-600 focus:outline-none focus:ring-1 focus:ring-white focus:border-white transition-all font-mono mb-3"
            onKeyDown={(e) => {
              if (e.key === 'Enter') navigate(`/${e.target.value}`);
            }}
            autoFocus
          />
          <button 
            className="w-full bg-white hover:bg-neutral-200 text-black font-medium py-2 px-4 rounded-md text-sm transition-colors"
            onClick={(e) => {
              const input = e.currentTarget.previousElementSibling;
              if (input.value) navigate(`/${input.value}`);
            }}
          >
            Continue &rarr;
          </button>
        </div>

        <div className="relative">
          <div className="absolute inset-0 flex items-center">
            <div className="w-full border-t border-neutral-800"></div>
          </div>
          <div className="relative flex justify-center text-xs">
            <span className="bg-black px-2 text-neutral-500">Or create new</span>
          </div>
        </div>

        <div className="mt-6 bg-[#0a0a0a] border border-neutral-800 rounded-xl p-4 shadow-xl">
          {createError && (
             <div className="mb-3 text-xs text-red-500 bg-red-500/10 border border-red-500/20 p-2 rounded flex items-center gap-2">
               <XCircle className="w-3 h-3" /> {createError}
             </div>
          )}
          <form onSubmit={handleCreateMerchant}>
            <input 
              type="text" 
              placeholder="Corp Name (e.g. Acme Corp)" 
              value={newCorpName}
              onChange={(e) => setNewCorpName(e.target.value)}
              className="w-full bg-black border border-neutral-800 rounded-md px-3 py-2 text-sm text-white placeholder-neutral-600 focus:outline-none focus:ring-1 focus:ring-white focus:border-white transition-all mb-3"
            />
            <button 
              type="submit"
              disabled={isCreating || !newCorpName.trim()}
              className="w-full bg-black border border-neutral-800 hover:bg-neutral-900 text-white font-medium py-2 px-4 rounded-md text-sm transition-colors flex items-center justify-center gap-2 disabled:opacity-50 disabled:cursor-not-allowed"
            >
              {isCreating ? <Loader2 className="w-4 h-4 animate-spin" /> : 'Create Merchant'}
            </button>
          </form>
        </div>
        
        <div className="mt-8 text-center">
          <p className="text-xs text-neutral-600">
            Powered by Playto Engine
          </p>
        </div>
      </div>
    </div>
  );
}

function App() {
  return (
    <Routes>
      <Route path="/" element={<SelectMerchant />} />
      <Route path="/:merchantId" element={<Dashboard />} />
    </Routes>
  );
}

export default App;

