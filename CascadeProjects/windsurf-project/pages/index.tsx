import { useState } from 'react';
import QuickCashSystem from '../components/quick-cash/QuickCashSystem';
import HighTicketDashboard from '../components/highticket/HighTicketDashboard';

export default function Home() {
  const [activeApp, setActiveApp] = useState<'quickcash' | 'highticket'>('quickcash');

  return (
    <div style={{ minHeight: '100vh', background: '#0a0a0a' }}>
      <nav style={{ 
        background: 'linear-gradient(135deg, #0a0a0a 0%, #1a1208 50%, #0a0a0a 100%)', 
        borderBottom: '1px solid #2a2010', 
        padding: '16px 32px',
        display: 'flex',
        justifyContent: 'center',
        gap: '16px'
      }}>
        <button
          onClick={() => setActiveApp('quickcash')}
          style={{
            padding: '12px 24px',
            background: activeApp === 'quickcash' ? 'linear-gradient(135deg, #c9a84c, #8b6914)' : 'transparent',
            border: `1px solid ${activeApp === 'quickcash' ? '#c9a84c' : '#2a2010'}`,
            borderRadius: '8px',
            color: activeApp === 'quickcash' ? '#0a0a0a' : '#8b7a5a',
            cursor: 'pointer',
            fontSize: '14px',
            fontWeight: 'bold',
            fontFamily: 'Georgia, serif',
            letterSpacing: '0.1em'
          }}
        >
          ⚡ Quick Cash System
        </button>
        <button
          onClick={() => setActiveApp('highticket')}
          style={{
            padding: '12px 24px',
            background: activeApp === 'highticket' ? 'linear-gradient(135deg, #c9a84c, #8b6914)' : 'transparent',
            border: `1px solid ${activeApp === 'highticket' ? '#c9a84c' : '#2a2010'}`,
            borderRadius: '8px',
            color: activeApp === 'highticket' ? '#0a0a0a' : '#8b7a5a',
            cursor: 'pointer',
            fontSize: '14px',
            fontWeight: 'bold',
            fontFamily: 'Georgia, serif',
            letterSpacing: '0.1em'
          }}
        >
          ◆ High-Ticket Dashboard
        </button>
      </nav>

      <main>
        {activeApp === 'quickcash' && <QuickCashSystem />}
        {activeApp === 'highticket' && <HighTicketDashboard />}
      </main>
    </div>
  );
}
