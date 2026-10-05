import type { Metadata } from "next";
import Link from "next/link";
import { REPO_URL } from "@/lib/site";

export const metadata: Metadata = {
  title: "Privacy: AnswerTrail",
  description: "What AnswerTrail stores, who can see it, and how to delete it.",
};

export default function PrivacyPage() {
  return (
    <main className="legal">
      <h1>Privacy</h1>
      <p className="legal-lead">
        AnswerTrail is a portfolio demo, not a commercial service. This page says plainly what it stores, who can
        see it and how to remove it.
      </p>

      <h2>What is stored</h2>
      <ul>
        <li>
          <strong>Your questions and the answers</strong>, with the help-article passages used, how long the answer
          took, and any thumbs up or down and comment you leave. They are saved so the assistant can be improved.
        </li>
        <li>
          <strong>If you create an account:</strong> your name, your email address and a password (stored by
          Supabase, our sign-in provider, in scrambled form; we never see it).
        </li>
        <li>
          <strong>In your browser:</strong> without an account, a list of your chat links so &ldquo;Recent
          chats&rdquo; works, and, when signed in, your sign-in session.
        </li>
      </ul>
      <p>
        We do <strong>not</strong> save your IP address with your questions. The server holds it in memory only, to
        limit how many questions one visitor can ask per minute and per day, and it is forgotten when the server
        restarts. Our hosting providers may keep ordinary server logs of their own.
      </p>

      <h2>Who can see your chats</h2>
      <ul>
        <li>
          <strong>With an account:</strong> only you. Nobody else, including other signed-in users and administrators,
          can open your conversations through the app.
        </li>
        <li>
          <strong>Without an account:</strong> anyone who has the link to that chat can read it. The link is long and
          random, but treat it like a secret, or sign in to keep your chats private.
        </li>
        <li>
          <strong>Administrators</strong> see the text of questions in a usage report so they can find missing help
          articles, but not who asked them.
        </li>
        <li>The person who runs this project can read the database directly, as with any service.</li>
      </ul>

      <h2>AI service</h2>
      <p>
        To answer, your question and the matching help-article passages are sent to Google&apos;s Gemini API, which
        writes the answer. How Google handles data sent to its API is described in Google&apos;s own terms. Please
        don&apos;t type personal, financial or other sensitive details into the chat.
      </p>

      <h2>Deleting your data</h2>
      <ul>
        <li>
          <strong>One chat:</strong> open it and choose &ldquo;Delete this chat&rdquo;. It is removed permanently, with
          its feedback.
        </li>
        <li>
          <strong>All your chats:</strong> when signed in, choose &ldquo;Delete all my chats&rdquo; in the sidebar.
        </li>
        <li>
          <strong>Your account:</strong> to have the account itself removed, get in touch with the project owner through the{" "}
          <a href={REPO_URL} target="_blank" rel="noopener noreferrer">
            project&apos;s GitHub page
          </a>
          .
        </li>
      </ul>

      <p className="legal-foot">
        <Link href="/chat">Back to the demo</Link>
      </p>
    </main>
  );
}
