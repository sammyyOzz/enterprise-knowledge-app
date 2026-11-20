"use client";

import Link from "next/link";
import { useState } from "react";
import { AuthLayout, Field } from "@/components/AuthLayout";
import { errorMessage } from "@/lib/api";
import { useAuth } from "@/lib/auth";

export default function SignupPage() {
  const { signUp } = useAuth();
  const [organization, setOrganization] = useState("");
  const [name, setName] = useState("");
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  async function submit(event: React.FormEvent) {
    event.preventDefault();
    setBusy(true);
    setError(null);
    try {
      await signUp({
        organization_name: organization,
        full_name: name || undefined,
        email,
        password,
      });
    } catch (e) {
      setError(errorMessage(e));
      setBusy(false);
    }
  }

  return (
    <AuthLayout
      title="Create your account"
      intro="This sets up your organization and a first workspace for its documents."
      footer={
        <>
          Already have an account?{" "}
          <Link href="/login" className="underline underline-offset-2 hover:text-ink">
            Sign in
          </Link>
        </>
      }
    >
      <form onSubmit={submit}>
        <Field
          id="organization"
          label="Organization name"
          autoComplete="organization"
          required
          minLength={2}
          value={organization}
          onChange={(e) => setOrganization(e.target.value)}
        />
        <Field
          id="name"
          label="Your name"
          autoComplete="name"
          value={name}
          onChange={(e) => setName(e.target.value)}
        />
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
          autoComplete="new-password"
          required
          minLength={10}
          hint="At least 10 characters."
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
          {busy ? "Creating account" : "Create account"}
        </button>
      </form>
    </AuthLayout>
  );
}