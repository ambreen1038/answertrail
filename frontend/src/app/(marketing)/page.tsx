import Link from "next/link";
import { ArrowIcon, BanIcon, ChartIcon, FilesIcon, GaugeIcon, LockIcon, QuoteIcon, SearchIcon, ShieldIcon, UploadIcon } from "@/components/Icons";
import LiveStats from "@/components/LiveStats";
import ScrollReveal from "@/components/ScrollReveal";
import type { CSSProperties } from "react";

const d = (ms: number) => ({ "--d": `${ms}ms` }) as CSSProperties;

const PROBLEMS = [
  { title: "They invent policies", text: "A made-up refund policy or feature claim does more damage than no answer at all." },
  { title: "You can't check them", text: "With no sources attached, every answer needs a person to verify it before anyone can trust it." },
  { title: "Nobody measures them", text: "A demo that works once says nothing about the next question a customer asks." },
];

const STEPS = [
  { icon: UploadIcon, title: "Add your documents", text: "Upload PDFs, Markdown or text files. They are split into small passages and indexed by meaning." },
  { icon: SearchIcon, title: "Find the right passages", text: "A customer's question is matched against your documents, and the five closest passages are pulled up." },
  { icon: ShieldIcon, title: "Answer only from them", text: "The model must say whether those passages actually answer the question. No cited source, no answer." },
  { icon: QuoteIcon, title: "Show the trail", text: "Every answer comes with its article, section and exact passage. If the documents don't cover it, it says so." },
];

const FEATURES = [
  { icon: QuoteIcon, title: "Cited answers", text: "The exact passage behind every answer is one click away, so customers and your team can verify it." },
  { icon: BanIcon, title: "Refuses instead of guessing", text: "Two independent checks stop an answer going out unless the documents support it." },
  { icon: FilesIcon, title: "Bring your own documents", text: "PDF, Markdown or text up to 10 MB. Re-upload a file and the old version is replaced." },
  { icon: LockIcon, title: "Secure admin", text: "Document management sits behind a real login, and the database is locked against the public API." },
  { icon: GaugeIcon, title: "Protected from abuse", text: "Per-visitor and daily limits keep a public demo from burning through the AI quota." },
  { icon: ChartIcon, title: "Measured, not assumed", text: "A public test set with dev, test and hard questions, including ones it should refuse." },
];

export default function Landing() {
  return (
    <main>
      <ScrollReveal />
      {/* ---------------------------------------------------------------- hero */}
      <section className="hero">
        <div className="wrap hero-grid">
          <div>
            <span className="eyebrow hero-in" style={d(0)}>AI customer support assistant</span>
            <h1 className="hero-in" style={d(90)}>
              Support answers you can <em>trace to the source.</em>
            </h1>
            <p className="lead hero-in" style={d(190)}>
              AnswerTrail answers customer questions only from your own help documents, shows the exact passage it
              used, and says &ldquo;I don&rsquo;t know&rdquo; instead of guessing.
            </p>
            <div className="cta-row hero-in" style={d(290)}>
              <Link href="/chat" className="btn btn-primary btn-lg">
                Try the demo <ArrowIcon size={18} />
              </Link>
              <Link href="/evaluation" className="btn btn-ghost btn-lg">
                See how it&apos;s measured
              </Link>
            </div>
            <p className="fineprint hero-in" style={d(390)}>Demo knowledge base: the InvoiceFlow help center.</p>
          </div>

          {/* A static illustration of real behaviour (both exchanges are real outputs from the demo). */}
          <div className="mock hero-in" style={d(200)} aria-label="Example conversation">
            <div className="mock-bar">
              <span /> <span /> <span />
              <b>AnswerTrail</b>
            </div>
            <div className="mock-body">
              <div className="m-user chat-in" style={d(900)}>How big can an uploaded file be?</div>
              <div className="m-bot chat-in" style={d(1500)}>
                Each file can be up to 10 MB.
                <div className="m-src">
                  <span>Sources</span>
                  <i>Uploading files · File size limit</i>
                </div>
              </div>
              <div className="m-user chat-in" style={d(2400)}>Does InvoiceFlow integrate with QuickBooks?</div>
              <div className="m-declined chat-in" style={d(3000)}>
                <strong>Not in the help articles</strong>
                I couldn&apos;t find that in the help articles, so I don&apos;t want to guess.
              </div>
            </div>
          </div>
        </div>
      </section>

      {/* ---------------------------------------------------------------- problem */}
      <section className="section tint" id="problem">
        <div className="wrap">
          <h2 className="reveal">Most chatbots answer whether or not they know.</h2>
          <p className="section-sub reveal" style={d(80)}>For customer support, that is the failure that matters.</p>
          <div className="grid3">
            {PROBLEMS.map((p, i) => (
              <div key={p.title} className="card reveal" style={d(i * 100)}>
                <h3>{p.title}</h3>
                <p>{p.text}</p>
              </div>
            ))}
          </div>
        </div>
      </section>

      {/* ---------------------------------------------------------------- how it works */}
      <section className="section" id="how">
        <div className="wrap">
          <h2 className="reveal">How it works</h2>
          <p className="section-sub reveal" style={d(80)}>Four steps between a question and a trustworthy answer.</p>
          <ol className="steps">
            {STEPS.map((s, i) => (
              <li key={s.title} className="step reveal" style={d(i * 110)}>
                <div className="step-top">
                  <span className="step-n">{i + 1}</span>
                  <s.icon size={22} className="step-icon" />
                </div>
                <h3>{s.title}</h3>
                <p>{s.text}</p>
              </li>
            ))}
          </ol>
        </div>
      </section>

      {/* ---------------------------------------------------------------- features */}
      <section className="section tint" id="features">
        <div className="wrap">
          <h2 className="reveal">Built to be trusted</h2>
          <p className="section-sub reveal" style={d(80)}>The unglamorous parts that decide whether you can put it in front of customers.</p>
          <div className="grid3">
            {FEATURES.map((f, i) => (
              <div key={f.title} className="card feature reveal" style={d((i % 3) * 100)}>
                <span className="feature-icon">
                  <f.icon size={22} />
                </span>
                <h3>{f.title}</h3>
                <p>{f.text}</p>
              </div>
            ))}
          </div>
        </div>
      </section>

      {/* ---------------------------------------------------------------- proof */}
      <section className="proof" id="proof">
        <div className="wrap">
          <h2 className="reveal">Measured on a test set, not a hunch</h2>
          <p className="section-sub reveal" style={d(80)}>
            60 hand-written questions, split so that tuning and reporting never use the same ones. These numbers are
            read live from the latest evaluation run.
          </p>
          <LiveStats />
          <p className="proof-note">
            A small, same-author test set: read it as &ldquo;no failures found here&rdquo;, not as a general accuracy
            figure. The limits are listed on the evaluation page.
          </p>
          <Link href="/evaluation" className="btn btn-light">
            Read the full evaluation <ArrowIcon size={18} />
          </Link>
        </div>
      </section>

      {/* ---------------------------------------------------------------- final CTA */}
      <section className="section cta-band">
        <div className="wrap">
          <h2 className="reveal">See it answer, and decline, for yourself.</h2>
          <p className="section-sub reveal" style={d(80)}>Ask it something the help center covers, then something it doesn&apos;t.</p>
          <Link href="/chat" className="btn btn-primary btn-lg reveal" style={d(160)}>
            Try the demo <ArrowIcon size={18} />
          </Link>
        </div>
      </section>
    </main>
  );
}
