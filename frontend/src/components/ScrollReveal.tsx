"use client";

import { useEffect } from "react";

/** Mount once on a page. Any element marked with the `reveal` class fades up the first time it
 *  scrolls into view (and stays). One shared observer, no per-element state, and the animation is
 *  pure CSS, so it costs almost nothing. With reduced motion the CSS shows everything immediately. */
export default function ScrollReveal() {
  useEffect(() => {
    const els = Array.from(document.querySelectorAll<HTMLElement>(".reveal"));
    if (typeof IntersectionObserver === "undefined") {
      els.forEach((el) => el.classList.add("in"));
      return;
    }
    const io = new IntersectionObserver(
      (entries) => {
        for (const e of entries) {
          if (e.isIntersecting) {
            e.target.classList.add("in");
            io.unobserve(e.target);
          }
        }
      },
      { threshold: 0.12, rootMargin: "0px 0px -40px 0px" },
    );
    els.forEach((el) => io.observe(el));
    return () => io.disconnect();
  }, []);
  return null;
}
