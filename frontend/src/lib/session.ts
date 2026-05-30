// Sign the user out: clear the server-side HttpOnly auth cookie, then drop the
// client-side token/user so AuthGuard redirects to /login.
export async function logout(): Promise<void> {
  try {
    await fetch("/api/auth/logout", { method: "POST" });
  } catch {
    // Even if the network call fails, still clear local state below.
  }
  localStorage.removeItem("token");
  localStorage.removeItem("user");
}
