import axios from "axios";

const BACKEND_URL = process.env.REACT_APP_BACKEND_URL;
export const API = `${BACKEND_URL}/api`;

const client = axios.create({ baseURL: API, timeout: 10000 });

export const api = {
  // profiles
  listProfiles: () => client.get("/profiles").then(r => r.data),
  createProfile: (name) => client.post("/profiles", { name }).then(r => r.data),
  activateProfile: (id) => client.post(`/profiles/${id}/activate`).then(r => r.data),
  deleteProfile: (id) => client.delete(`/profiles/${id}`).then(r => r.data),

  // mappings
  listMappings: (profileId) => client.get(`/profiles/${profileId}/mappings`).then(r => r.data),
  upsertMapping: (profileId, controlId, body) =>
    client.put(`/profiles/${profileId}/mappings/${controlId}`, body).then(r => r.data),
  deleteMapping: (profileId, controlId) =>
    client.delete(`/profiles/${profileId}/mappings/${controlId}`).then(r => r.data),

  // helper telemetry
  helperStatus: () => client.get("/helper/status").then(r => r.data),
  helperSessions: () => client.get("/helper/sessions").then(r => r.data),
  helperEvents: (since) =>
    client.get("/helper/midi-events", { params: since ? { since } : {} }).then(r => r.data),
};

export default api;
