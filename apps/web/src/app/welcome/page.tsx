import Link from "next/link";

const steps = [
  ["01", "Say it your way", "Talk or type a quick, messy note about everything on your mind."],
  ["02", "Get it sorted", "Sift finds the tasks, calendar events, and messages in your note."],
  ["03", "Move on with your day", "Review the results, make edits, and keep everything in one place."],
];

export default function Welcome() {
  return (
    <main className="welcome">
      <section className="welcome-hero">
        <p className="eyebrow">A little less in your head</p>
        <h1>Say it messy.<br />Get your day sorted.</h1>
        <p className="welcome-copy">
          Sift turns a quick voice note or brain dump into clear tasks, calendar events, and draft messages.
          No organizing first. Just say what’s on your mind.
        </p>
        <div className="welcome-actions">
          <Link className="btn solid" href="/signup">Get started</Link>
          <Link className="welcome-login" href="/login">I already have an account</Link>
        </div>
      </section>
      <section className="welcome-steps" aria-label="How Sift works">
        {steps.map(([number, title, description]) => (
          <article className="welcome-step" key={number}>
            <span className="welcome-number">{number}</span>
            <h2>{title}</h2>
            <p>{description}</p>
          </article>
        ))}
      </section>
    </main>
  );
}
