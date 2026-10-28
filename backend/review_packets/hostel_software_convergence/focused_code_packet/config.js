// Centralized API Configuration
// Vite uses 'import.meta.env' for environment variables.
// On LAN (e.g. Girls Hostel onsite 192.168.x.x), dynamic hostname resolution ensures
// that frontend connects to backend on the same host machine even when accessed via LAN IP.

const getApiBaseUrl = () => {
    if (import.meta.env.VITE_API_URL) {
        return import.meta.env.VITE_API_URL.replace(/\/$/, "");
    }
    if (typeof window !== "undefined" && window.location && window.location.hostname) {
        const host = window.location.hostname;
        return `http://${host}:8000`;
    }
    return "http://localhost:8000";
};

export const API_BASE_URL = getApiBaseUrl();

export const API_ENDPOINTS = {
    ACCESS_EVENT: `${API_BASE_URL}/access/event`,
    EVENTS: `${API_BASE_URL}/events`,
    STREAM: `${API_BASE_URL}/events/stream`,
    SETTINGS: `${API_BASE_URL}/settings`,
    SYSTEM_DEVICES: `${API_BASE_URL}/system/devices`,
    REVIEW_QUEUE: `${API_BASE_URL}/review/queue`,
    REVIEW_ACTION: `${API_BASE_URL}/review/action`,
    REPORTS_STATS: `${API_BASE_URL}/reports/stats`,
    REPORTS_EXPORT: `${API_BASE_URL}/reports/export`,
    ALERTS: `${API_BASE_URL}/alerts`,
    USERS: `${API_BASE_URL}/users`,
    USERS_ENROLL: `${API_BASE_URL}/users/enroll`,
    USERS_SEARCH: `${API_BASE_URL}/users/search`,
    STATS_SUMMARY: `${API_BASE_URL}/stats/summary`,
    SIMULATE_REVIEW: `${API_BASE_URL}/simulate/review`,
    MANUAL_OVERRIDE: `${API_BASE_URL}/manual/override`,
    GATES: `${API_BASE_URL}/gates`,
    SYNC_STATUS: `${API_BASE_URL}/sync/status`,
    SYNC_RETRY: `${API_BASE_URL}/sync/retry`,
};
