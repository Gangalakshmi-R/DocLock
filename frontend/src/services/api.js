import axios from 'axios';

const API_BASE_URL = import.meta.env.VITE_API_BASE_URL || '/api';

const api = axios.create({
  baseURL: API_BASE_URL,
  headers: {},
});

api.interceptors.request.use(
  (config) => {
    const token = localStorage.getItem('doclock_jwt');
    if (token) {
      config.headers.Authorization = `Bearer ${token}`;
    }
    return config;
  },
  (error) => Promise.reject(error)
);

api.interceptors.response.use(
  (response) => response,
  (error) => {
    // A 401 from the login form just means "wrong password": let the form show the message instead of reloading the page.
    const isLoginRequest = String(error.config?.url || '').includes('/auth/login');
    if (error.response && error.response.status === 401 && !isLoginRequest) {
      localStorage.removeItem('doclock_jwt');
      window.location.href = '/login';
    }
    return Promise.reject(error);
  }
);

export default api;
