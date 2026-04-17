// When served from GCS (or any static host), the deploy script sets this to your Cloud Run / API URL.
// Example: window.__DOMINION_API_BASE__ = "https://my-service-xxxxx.run.app/api/v1/dominion";
// null = same origin as this page (local uvicorn or reverse proxy).
window.__DOMINION_API_BASE__ = null;
