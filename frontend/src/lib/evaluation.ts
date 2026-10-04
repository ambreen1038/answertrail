import { API } from "./site";

export type SplitStats = {
  n_answerable: number;
  n_unanswerable: number;
  correct_answers: number;
  correct_refusals: number;
  hallucinated_answers: number;
  retrieval_hit_at_k: number;
  retrieval_hit_at_1: number;
  citation_ok: number;
  answered: number;
};

export type Outcome = "correct" | "wrong_answer" | "false_refusal" | "correct_refusal" | "invented_answer";

export type EvalQuestion = {
  id: string;
  split: "dev" | "test" | "hard";
  question: string;
  answerable: boolean;
  outcome: Outcome;
  passed: boolean;
  answer: string | null;
  top_score: number;
  gold_docs: string[];
  cited_docs: string[];
};

export type EvalReport = {
  gen_model: string;
  embed_model: string;
  top_k: number;
  threshold: number;
  splits: Record<"dev" | "test" | "hard", SplitStats>;
  totals: { questions: number; passed: number; out_of_scope: number; invented_answers: number };
  questions: EvalQuestion[];
};

export async function fetchEvaluation(): Promise<EvalReport | null> {
  try {
    const res = await fetch(`${API}/api/evaluation`);
    return res.ok ? await res.json() : null;
  } catch {
    return null;
  }
}
