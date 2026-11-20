"use client";

import Link from "next/link";
import { useState } from "react";
import { AuthLayout, Field } from "@/components/AuthLayout";
import { errorMessage } from "@/lib/api";
import { useAuth } from "@/lib/auth";

export default function LoginPage() {
  const { signIn } = useAuth();
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  async function submit(event: React.FormEvent) {
    event.preventDefault();
    setBusy(true);
    setError(null);
    try {
      await signIn(email, password); // the shell then moves us on to /ask
    } catch (e) {
      setError(errorMessage(e));
      setBusy(false);
    }
  }

  return (
    <AuthLayout
      title="Sign in"
      footer={
        <>
          New here?{" "}
          <Link href="/signup" className="underline underline-offset-2 hover:text-ink">
            Create an account
          </Link>
        </>
      }
    >
      <form onSubmit={submit}>
        <Field
          id="email"
          label="Email"
          type="email"
          autoComplete="email"
          required
          value={email}
          onChange={(e) => setEmail(e.target.value)}
        />
        <Field
          id="password"
          label="Password"
          type="password"
          autoComplete="current-password"
          required
          value={password}
          onChange={(e) => setPassword(e.target.value)}
        />
        {error && (
          <p role="alert" className="mt-4 border-l-2 border-bad pl-3 text-bad">
            {error}
          </p>
        )}
        <button
          type="submit"
          disabled={busy}
          className="mt-6 rounded-md bg-accent px-5 py-2 font-medium text-accent-ink hover:opacity-90 disabled:opacity-50"
        >
          {busy ? "Signing in" : "Sign in"}
        </button>
      </form>
    </AuthLayout>
  );
}