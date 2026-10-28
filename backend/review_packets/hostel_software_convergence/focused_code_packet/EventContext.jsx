import { createContext, useContext, useState, useEffect } from 'react';
import { API_ENDPOINTS } from '../api/config';

const EventContext = createContext();

export function EventProvider({ children }) {
  const [events, setEvents] = useState([]);
  const [reviewItems, setReviewItems] = useState([]);
  const [connected, setConnected] = useState(false);

  useEffect(() => {
    // Initial Fetch from Python Backend
    const fetchEvents = async () => {
      try {
        const res = await fetch(`${API_ENDPOINTS.EVENTS}?limit=50`);
        const data = await res.json();
        if (Array.isArray(data)) {
          setEvents(data.reverse()); // Newest first
        }
      } catch (err) {
        console.warn("Initial fetch failed", err);
      }
    };
    
    const fetchQueue = async () => {
      try {
        const res = await fetch(API_ENDPOINTS.REVIEW_QUEUE);
        const data = await res.json();
        if (Array.isArray(data)) {
          setReviewItems(data);
        }
      } catch (err) {
        console.warn("Initial review queue fetch failed", err);
      }
    };

    fetchEvents();
    fetchQueue();

    // Resilient SSE Connection to Python Backend with auto-reconnect
    let reconnectTimeout = null;
    let evtSource = null;

    const connectSSE = () => {
      try {
        evtSource = new EventSource(API_ENDPOINTS.STREAM);
        
        evtSource.onopen = () => {
          setConnected(true);
          console.log("[SSE] Connected to backend events stream at", API_ENDPOINTS.STREAM);
        };

        evtSource.onmessage = (e) => {
          try {
            if (!e.data || e.data.trim() === '{"status":"connected"}') return;
            const data = JSON.parse(e.data);
            setEvents((prev) => [data, ...prev.slice(0, 49)]);
            
            // Queue Control Logic - Handle queue via SSE
            if (data.decision === 'REVIEW') {
              setReviewItems((prev) => {
                if (!prev.find(item => item.trace_id === data.trace_id)) {
                  return [...prev, data];
                }
                return prev;
              });
            } else {
              setReviewItems((prev) => prev.filter(item => item.trace_id !== data.trace_id));
            }
          } catch (err) {
            console.error("Failed to parse SSE data", err);
          }
        };

        evtSource.onerror = (err) => {
          setConnected(false);
          if (evtSource) {
            evtSource.close();
          }
          clearTimeout(reconnectTimeout);
          reconnectTimeout = setTimeout(connectSSE, 3000);
        };
      } catch (e) {
        setConnected(false);
        clearTimeout(reconnectTimeout);
        reconnectTimeout = setTimeout(connectSSE, 3000);
      }
    };

    connectSSE();

    return () => {
      if (evtSource) evtSource.close();
      if (reconnectTimeout) clearTimeout(reconnectTimeout);
    };
  }, []);

  const triggerOverride = async (reason) => {
    try {
      const res = await fetch(API_ENDPOINTS.MANUAL_OVERRIDE, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ reason })
      });
      if (!res.ok) throw new Error(`HTTP error! status: ${res.status}`);
      const text = await res.text();
      return text ? JSON.parse(text) : {};
    } catch (err) {
      console.error("Override failed", err);
      throw err;
    }
  };

  const triggerSimulation = async () => {
    const users = [
      { user_id: "S001", method: "FACE" },
      { user_id: "S999", method: "RFID" }
    ];
    const user = users[Math.floor(Math.random() * users.length)];
    try {
      await fetch(API_ENDPOINTS.ACCESS_EVENT, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ ...user, device_id: "booth_1_in" })
      });
    } catch (err) {
      console.error("Simulation failed", err);
    }
  };

  const triggerReviewSimulation = async () => {
    try {
      await fetch(API_ENDPOINTS.SIMULATE_REVIEW, { method: 'POST' });
    } catch (err) {
      console.error("Simulation failed", err);
    }
  };

  const handleReviewAction = async (trace_id, action) => {
    try {
      await fetch(API_ENDPOINTS.REVIEW_ACTION, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ trace_id, action })
      });
      setReviewItems((prev) => prev.filter(item => item.trace_id !== trace_id));
    } catch (err) {
      console.error("Failed to process review action", err);
    }
  };

  return (
    <EventContext.Provider value={{
      events,
      reviewItems,
      connected,
      triggerOverride,
      triggerSimulation,
      triggerReviewSimulation,
      handleReviewAction
    }}>
      {children}
    </EventContext.Provider>
  );
}

export function useEvents() {
  return useContext(EventContext);
}
