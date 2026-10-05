"use client";

import { useEffect, useRef, useState } from "react";

/** Counts from 0 up to `value` the first time it scrolls into view. With reduced motion it simply
 *  shows the final number. The real value is always what ends up on screen. */
export default function CountUp({
  value,
  duration = 900,
  decimals = 0,
  suffix = "",
}: {
  value: number;
  duration?: number;
  decimals?: number;
  suffix?: string;
}) {
  const scale = 10 ** decimals;
  const target = Math.round(value * scale); // count in whole steps of the last decimal place
  const [n, setN] = useState(0);
  const ref = useRef<HTMLSpanElement>(null);

  useEffect(() => {
    const el = ref.current;
    if (!el) return;
    let raf = 0;
    const reduce = window.matchMedia("(prefers-reduced-motion: reduce)").matches;

    const run = () => {
      if (reduce || target === 0) {
        setN(target);
        return;
      }
      const start = performance.now();
      const tick = (now: number) => {
        const p = Math.min(1, (now - start) / duration);
        setN(Math.round(target * (1 - Math.pow(1 - p, 3)))); // ease-out
        if (p < 1) raf = requestAnimationFrame(tick);
      };
      raf = requestAnimationFrame(tick);
    };

    const io = new IntersectionObserver(([entry]) => {
      if (entry.isIntersecting) {
        io.disconnect();
        run();
      }
    });
    io.observe(el);
    return () => {
      io.disconnect();
      cancelAnimationFrame(raf);
    };
  }, [target, duration]);

  return (
    <span ref={ref}>
      {(n / scale).toFixed(decimals)}
      {suffix}
    </span>
  );
}
