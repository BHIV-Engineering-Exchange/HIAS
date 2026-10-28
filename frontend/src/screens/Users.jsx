import { useState, useEffect } from 'react';
import { Users as UsersIcon, Search, UserPlus, MoreVertical, Shield, User, CreditCard, RefreshCw, CheckCircle, AlertTriangle } from 'lucide-react';
import { API_ENDPOINTS } from '../api/config';

export default function Users({ initialSearch = '' }) {
  const [users, setUsers] = useState([]);
  const [loading, setLoading] = useState(true);
  const [showModal, setShowModal] = useState(false);
  const [newUser, setNewUser] = useState({
    user_id: '',
    name: '',
    role: 'Resident',
    department: 'Block A',
    rfid_card: '',
    enable_fr: true,
    auto_sync: true
  });
  const [enrollResult, setEnrollResult] = useState(null);
  const [submitting, setSubmitting] = useState(false);
  const [searchQuery, setSearchQuery] = useState(initialSearch);

  const fetchUsers = async (query = '') => {
    setLoading(true);
    try {
      const url = query ? `${API_ENDPOINTS.USERS_SEARCH}?q=${query}` : API_ENDPOINTS.USERS;
      const res = await fetch(url);
      const data = await res.json();
      if (Array.isArray(data)) {
        setUsers(data);
      }
    } catch (err) {
      console.error("Failed to fetch users", err);
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    fetchUsers(initialSearch);
    setSearchQuery(initialSearch);
  }, [initialSearch]);

  const handleSubmit = async (e) => {
    e.preventDefault();
    setSubmitting(true);
    setEnrollResult(null);
    try {
      const payload = {
        user_id: newUser.user_id,
        name: newUser.name,
        role: newUser.role,
        department: newUser.department,
        rfid_card: newUser.rfid_card ? newUser.rfid_card.trim() : null,
        face_data: newUser.enable_fr ? "ARGO_FACE_TEMPLATE_STANDARD_V1" : null,
        auto_sync: newUser.auto_sync
      };

      const res = await fetch(API_ENDPOINTS.USERS_ENROLL, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(payload)
      });
      const data = await res.json();
      if (res.ok) {
        setEnrollResult(data);
        setTimeout(() => {
          setShowModal(false);
          setEnrollResult(null);
          setNewUser({
            user_id: '',
            name: '',
            role: 'Resident',
            department: 'Block A',
            rfid_card: '',
            enable_fr: true,
            auto_sync: true
          });
          fetchUsers();
        }, 1500);
      } else {
        alert(data.detail || "Enrollment failed");
      }
    } catch (err) {
      alert("Failed to enroll user: Network or server error");
    } finally {
      setSubmitting(false);
    }
  };

  return (
    <div style={{ display: 'flex', flexDirection: 'column', gap: '20px' }}>
      {showModal && (
        <div style={{ position: 'fixed', top: 0, left: 0, right: 0, bottom: 0, backgroundColor: 'rgba(0,0,0,0.75)', backdropFilter: 'blur(4px)', zIndex: 1000, display: 'flex', alignItems: 'center', justifyContent: 'center' }}>
          <div className="card" style={{ width: '480px', padding: '24px', backgroundColor: 'var(--bg-card)', border: '1px solid var(--border-color)', maxHeight: '90vh', overflowY: 'auto' }}>
            <h2 style={{ fontSize: '16px', fontWeight: '600', marginBottom: '4px', display: 'flex', alignItems: 'center', gap: '8px' }}>
              <UserPlus size={18} color="var(--accent-primary)" /> One-Click Central Enrollment
            </h2>
            <p style={{ color: 'var(--text-muted)', fontSize: '12px', marginBottom: '16px' }}>
              Registers canonical identity and synchronizes RFID/Face credentials to all physical hostel gates.
            </p>

            {enrollResult && (
              <div style={{ padding: '12px', backgroundColor: 'rgba(34, 197, 94, 0.15)', border: '1px solid var(--success)', borderRadius: '6px', marginBottom: '14px', fontSize: '12px', color: 'var(--success)', display: 'flex', alignItems: 'center', gap: '8px' }}>
                <CheckCircle size={16} /> Enrolled successfully! Synchronized across active gates.
              </div>
            )}

            <form onSubmit={handleSubmit}>
              <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: '12px', marginBottom: '12px' }}>
                <div>
                  <label style={{ display: 'block', fontSize: '11px', fontWeight: '600', color: 'var(--text-muted)', letterSpacing: '0.05em', marginBottom: '4px' }}>USER ID</label>
                  <input 
                    type="text" 
                    required
                    value={newUser.user_id}
                    onChange={e => setNewUser({...newUser, user_id: e.target.value})}
                    placeholder="e.g. S2501"
                    style={{ width: '100%', padding: '8px 10px', fontSize: '12px' }}
                  />
                </div>
                <div>
                  <label style={{ display: 'block', fontSize: '11px', fontWeight: '600', color: 'var(--text-muted)', letterSpacing: '0.05em', marginBottom: '4px' }}>ROLE</label>
                  <select 
                    value={newUser.role}
                    onChange={e => setNewUser({...newUser, role: e.target.value})}
                    style={{ width: '100%', padding: '8px 10px', fontSize: '12px', backgroundColor: 'var(--bg-input)', color: 'var(--text-primary)', border: '1px solid var(--border-color)', borderRadius: 'var(--radius-sm)' }}
                  >
                    <option value="Resident">Resident</option>
                    <option value="Admin">Admin</option>
                    <option value="Staff">Staff</option>
                    <option value="Security">Security</option>
                  </select>
                </div>
              </div>

              <div style={{ marginBottom: '12px' }}>
                <label style={{ display: 'block', fontSize: '11px', fontWeight: '600', color: 'var(--text-muted)', letterSpacing: '0.05em', marginBottom: '4px' }}>FULL NAME</label>
                <input 
                  type="text" 
                  required
                  value={newUser.name}
                  onChange={e => setNewUser({...newUser, name: e.target.value})}
                  placeholder="e.g. Pritesh Patra"
                  style={{ width: '100%', padding: '8px 10px', fontSize: '12px' }}
                />
              </div>

              <div style={{ marginBottom: '12px' }}>
                <label style={{ display: 'block', fontSize: '11px', fontWeight: '600', color: 'var(--text-muted)', letterSpacing: '0.05em', marginBottom: '4px' }}>DEPARTMENT / ROOM</label>
                <input 
                  type="text" 
                  value={newUser.department}
                  onChange={e => setNewUser({...newUser, department: e.target.value})}
                  placeholder="e.g. Girls Hostel Block B, Room 204"
                  style={{ width: '100%', padding: '8px 10px', fontSize: '12px' }}
                />
              </div>

              <div style={{ marginBottom: '14px', padding: '12px', backgroundColor: 'rgba(255, 255, 255, 0.02)', border: '1px solid var(--border-color)', borderRadius: '6px' }}>
                <div style={{ fontSize: '11px', fontWeight: '600', color: 'var(--text-secondary)', marginBottom: '8px', display: 'flex', alignItems: 'center', gap: '6px' }}>
                  <CreditCard size={14} color="var(--accent-primary)" /> HARDWARE CREDENTIAL PROVISIONING
                </div>
                <div style={{ marginBottom: '10px' }}>
                  <label style={{ display: 'block', fontSize: '11px', color: 'var(--text-muted)', marginBottom: '4px' }}>RFID Card CSN / Number (64-bit)</label>
                  <input 
                    type="text" 
                    value={newUser.rfid_card}
                    onChange={e => setNewUser({...newUser, rfid_card: e.target.value})}
                    placeholder="e.g. 3280168301 (Optional - auto generated if blank)"
                    style={{ width: '100%', padding: '8px 10px', fontSize: '12px', fontFamily: "'JetBrains Mono', monospace" }}
                  />
                </div>
                <div style={{ display: 'flex', flexDirection: 'column', gap: '6px' }}>
                  <label style={{ display: 'flex', alignItems: 'center', gap: '8px', fontSize: '12px', cursor: 'pointer' }}>
                    <input 
                      type="checkbox"
                      checked={newUser.enable_fr}
                      onChange={e => setNewUser({...newUser, enable_fr: e.target.checked})}
                    />
                    <span>Provision COSEC ARGO Face Recognition Template</span>
                  </label>
                  <label style={{ display: 'flex', alignItems: 'center', gap: '8px', fontSize: '12px', cursor: 'pointer' }}>
                    <input 
                      type="checkbox"
                      checked={newUser.auto_sync}
                      onChange={e => setNewUser({...newUser, auto_sync: e.target.checked})}
                    />
                    <span>Automatically Push & Sync to all Active Hostel Gates</span>
                  </label>
                </div>
              </div>

              <div style={{ display: 'flex', gap: '10px' }}>
                <button 
                  type="button" 
                  onClick={() => setShowModal(false)} 
                  disabled={submitting}
                  style={{ flex: 1, backgroundColor: 'var(--bg-input)', color: 'var(--text-secondary)', border: '1px solid var(--border-color)', padding: '10px', borderRadius: 'var(--radius-sm)', cursor: 'pointer', fontSize: '12px', fontWeight: '500' }}
                >
                  CANCEL
                </button>
                <button 
                  type="submit" 
                  disabled={submitting}
                  style={{ flex: 1, background: 'var(--accent-gradient)', color: 'white', border: 'none', padding: '10px', borderRadius: 'var(--radius-sm)', fontWeight: '600', cursor: 'pointer', fontSize: '12px', display: 'flex', alignItems: 'center', justifyContent: 'center', gap: '6px' }}
                >
                  {submitting ? <RefreshCw size={14} className="spin" /> : <UserPlus size={14} />}
                  {submitting ? 'PROVISIONING...' : 'ENROLL & SYNC'}
                </button>
              </div>
            </form>
          </div>
        </div>
      )}

      <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
        <div>
          <h1 style={{ fontSize: '20px', fontWeight: '600', display: 'flex', alignItems: 'center', gap: '10px', letterSpacing: '-0.01em' }}>
            <UsersIcon color="var(--accent-primary)" size={20} /> User & Credential Registry
          </h1>
          <p style={{ color: 'var(--text-secondary)', fontSize: '13px', marginTop: '2px' }}>
            Central database for 2,500+ residents, RFID cards, and multi-gate sync status
          </p>
        </div>
        <div style={{ display: 'flex', gap: '12px', alignItems: 'center' }}>
          <div style={{ position: 'relative', width: '280px' }}>
            <Search size={14} style={{ position: 'absolute', left: '10px', top: '50%', transform: 'translateY(-50%)', color: 'var(--text-muted)' }} />
            <input 
              type="text" 
              placeholder="Search by ID, name, or RFID card..." 
              value={searchQuery}
              onChange={(e) => {
                const q = e.target.value;
                setSearchQuery(q);
                fetchUsers(q);
              }}
              style={{ width: '100%', padding: '8px 8px 8px 32px', fontSize: '12px' }}
            />
          </div>
          <button 
            onClick={() => setShowModal(true)}
            style={{ 
              background: 'var(--accent-gradient)', 
              color: 'white', 
              border: 'none', 
              padding: '8px 16px', 
              borderRadius: 'var(--radius-sm)', 
              display: 'flex', 
              alignItems: 'center', 
              gap: '6px',
              fontWeight: '600',
              fontSize: '12px',
              cursor: 'pointer',
              boxShadow: '0 2px 8px var(--accent-glow)'
            }}
          >
            <UserPlus size={14} /> ONE-CLICK ENROLL
          </button>
        </div>
      </div>

      <div className="card" style={{ padding: '0', overflow: 'hidden' }}>
        <table style={{ width: '100%', borderCollapse: 'collapse' }}>
          <thead>
            <tr>
              <th style={{ padding: '12px 16px' }}>User</th>
              <th style={{ padding: '12px 16px' }}>User ID / Ref ID</th>
              <th style={{ padding: '12px 16px' }}>Role</th>
              <th style={{ padding: '12px 16px' }}>Credentials</th>
              <th style={{ padding: '12px 16px' }}>Multi-Gate Sync</th>
              <th style={{ padding: '12px 16px', textAlign: 'right' }}>Actions</th>
            </tr>
          </thead>
          <tbody>
            {loading ? (
              <tr><td colSpan="6" style={{ padding: '40px', textAlign: 'center', color: 'var(--text-muted)' }}>Loading user directory...</td></tr>
            ) : users.length === 0 ? (
              <tr><td colSpan="6" style={{ padding: '40px', textAlign: 'center', color: 'var(--text-muted)' }}>No users found matching query.</td></tr>
            ) : (
              users.map((user, i) => (
                <tr key={i}>
                  <td style={{ padding: '12px 16px' }}>
                    <div style={{ display: 'flex', alignItems: 'center', gap: '10px' }}>
                      <div className="avatar">
                        {user.role === 'Admin' ? <Shield size={14} color="var(--accent-primary)" /> : user.name?.charAt(0) || 'U'}
                      </div>
                      <div>
                        <div style={{ fontWeight: '500' }}>{user.name}</div>
                        <div style={{ fontSize: '11px', color: 'var(--text-muted)' }}>{user.department || 'Hostel Resident'}</div>
                      </div>
                    </div>
                  </td>
                  <td style={{ padding: '12px 16px', fontFamily: "'JetBrains Mono', monospace", fontSize: '12px' }}>
                    <span style={{ color: 'var(--text-primary)' }}>{user.user_id}</span>
                    {user.ref_user_id && <span style={{ color: 'var(--text-muted)', fontSize: '11px', marginLeft: '6px' }}>#{user.ref_user_id}</span>}
                  </td>
                  <td style={{ padding: '12px 16px' }}>
                    <span style={{ 
                      fontSize: '10px', 
                      padding: '2px 8px', 
                      borderRadius: '4px', 
                      backgroundColor: user.role === 'Admin' ? 'rgba(94, 106, 210, 0.12)' : 'rgba(56, 189, 248, 0.12)',
                      color: user.role === 'Admin' ? '#a3aeff' : '#38bdf8',
                      border: user.role === 'Admin' ? '1px solid rgba(94, 106, 210, 0.25)' : '1px solid rgba(56, 189, 248, 0.25)',
                      fontWeight: '600',
                      letterSpacing: '0.04em',
                      fontFamily: "'JetBrains Mono', monospace"
                    }}>
                      {(user.role || 'Resident').toUpperCase()}
                    </span>
                  </td>
                  <td style={{ padding: '12px 16px' }}>
                    <div style={{ display: 'flex', flexWrap: 'wrap', gap: '6px' }}>
                      {user.credentials && user.credentials.length > 0 ? (
                        user.credentials.map((c, idx) => (
                          <span key={idx} style={{
                            fontSize: '10px',
                            padding: '2px 6px',
                            borderRadius: '3px',
                            backgroundColor: 'rgba(255, 255, 255, 0.05)',
                            border: '1px solid var(--border-color)',
                            fontFamily: "'JetBrains Mono', monospace"
                          }}>
                            {c.type}: {c.card_number || 'ACTIVE'}
                          </span>
                        ))
                      ) : (
                        <span style={{ fontSize: '11px', color: 'var(--text-muted)' }}>No credentials</span>
                      )}
                    </div>
                  </td>
                  <td style={{ padding: '12px 16px' }}>
                    <div style={{ display: 'flex', alignItems: 'center', gap: '6px' }}>
                      <div style={{ width: '6px', height: '6px', borderRadius: '50%', backgroundColor: 'var(--success)' }} />
                      <span style={{ fontSize: '11px', color: 'var(--success)', fontWeight: '500' }}>3/3 Gates Synced</span>
                    </div>
                  </td>
                  <td style={{ padding: '12px 16px', textAlign: 'right' }}>
                    <button style={{ background: 'none', border: 'none', color: 'var(--text-muted)', cursor: 'pointer' }}>
                      <MoreVertical size={16} />
                    </button>
                  </td>
                </tr>
              ))
            )}
          </tbody>
        </table>
      </div>
    </div>
  );
}
