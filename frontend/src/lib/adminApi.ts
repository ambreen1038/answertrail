// The admin pages use the same authenticated fetch as everything else; the server decides who is an admin.
export { apiFetch as adminFetch, errorDetail } from "./api";
